# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây được lấy trực tiếp từ các file JSON trong `reports/` (và CSV/screenshot ở CP8), không ước lượng.

**Họ tên:** Khổng Ngọc Anh (MSSV: `2A202603974`)  
**Ngày chạy:** 2026-11-26  
**Môi trường:** Linux (Python 3.12 virtualenv, Docker 28.5.2)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Đảm bảo 95% request phản hồi mượt mà trong nửa giây; phản ánh đúng trải nghiệm người dùng tốt hơn trung bình (vốn che giấu tail latency). |
| Error rate `/ask` | < 2.0 % | Chấp nhận một tỉ lệ lỗi nhỏ tạm thời từ upstream LLM (~1% mặc định) trong error budget, đồng thời phát hiện sớm sự cố khi lỗi tăng đột biến. |
| Accuracy trên golden dataset | ≥ 80 % (mục tiêu sau sửa KB: 100%) | Đảm bảo chất lượng câu trả lời không bị suy giảm (regression) trước mỗi lần merge/deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2 — 300 requests / mức)

Nguồn: `reports/load_v2_c1.json`, `load_v2_c10.json`, `load_v2_c50.json`, `load_v2_c100.json`.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.72 | 189.9 | 224.0 | 1666.1 | 0.33% | ✅ PASS |
| 10 | 35.43 | 195.1 | 230.0 | 1691.2 | 0.33% | ✅ PASS |
| 50 | 107.07 | 203.1 | 292.5 | 1713.8 | 0.67% | ✅ PASS |
| 100 | 56.71 | 648.3 | 3906.6 | 4357.2 | 1.00% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không tăng tuyến tính** theo concurrency.
- Từ `c=1` → `c=10` → `c=50`, RPS tăng mạnh (`4.72` → `35.43` → `107.07 req/s`) vì agent dùng `async/await` nên nhiều request chờ I/O đồng thời được trên cùng event loop.
- Tuy nhiên, tại `c=100`, hệ thống vượt ngưỡng bão hòa (saturation) của 1 process uvicorn + giới hạn kết nối/event loop: **hàng đợi (queueing) phình to**, khiến `p50` vọt lên `648.3 ms`, `p95` nhảy vọt lên `3906.6 ms` (gần gấp 13 lần `c=50`) và **RPS thực tế giảm ngược xuống `56.71 req/s`** (vi phạm SLO p95 ≤ 500ms). Điều này cho thấy 1 instance có điểm giới hạn và cần scale ngang nhiều instance + load balancer.

### 2.2 Tail latency (agent v2 — 300 requests, `concurrency=20`)

Nguồn: `reports/load_v2_slow_0.json`, `load_v2_slow_0.03.json`, `load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 195.5 | 231.6 | 251.6 |
| 0.03 (mặc định) | 223.0 | 231.6 | 1681.8 |
| 0.1 | 383.7 | 1693.6 | 1728.4 |

**Nhận xét:**
- **p99** (và tiếp theo là **p95** khi tỉ lệ chậm vượt 5%) nhạy nhất với request chậm:
  - Khi `MOCK_SLOW_RATE=0.03` (3% request chậm), `avg` chỉ nhích nhẹ `+27.5 ms` (`195.5 → 223.0 ms`), `p95` giữ nguyên `231.6 ms`, nhưng **`p99` nhảy vọt lên `1681.8 ms`** (gấp 6.7 lần).
  - Khi `MOCK_SLOW_RATE=0.1` (10% > 5% request chậm), `avg` mới là `383.7 ms` (trông vẫn "dưới 500 ms"), nhưng **`p95` đã vọt lên `1693.6 ms`**, vi phạm nặng SLO.
- **Vì sao không đặt SLO theo average?** Giá trị trung bình bị 90–97% request nhanh kéo xuống nên **che giấu nhóm người dùng bị chậm (tail latency)**. Đặt SLO theo `p95`/`p99` bảo vệ trực tiếp trải nghiệm thực tế của người dùng ở đuôi phân phối.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.5 | 108.8 | 114.6 |
| Tổng cost (USD) | $0.000396 | $0.000758 | $0.000799 |
| Cost / câu đúng (USD) | $0.00039555 | $0.00003607 | $0.00003472 |
| Latency p50 / p95 (ms) | 159.4 / 191.6 | 195.5 / 215.2 | 187.2 / 214.0 |
| Quality gate | ❌ FAIL | ✅ PASS (≥ 80%) | ✅ PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách đã sửa (`develop/utils/mock_llm.py` & `production/utils/mock_llm.py`):**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry vào `KNOWLEDGE_BASE` với từ khóa `["jwt", "json web token"]` giải thích JWT là token tự chứa claims có chữ ký số và thời gian hết hạn (`exp`), khác API key tĩnh. |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry vào `KNOWLEDGE_BASE` với từ khóa `["hpa", "kubernetes"]` giải thích Kubernetes HPA tự động scale pod dựa trên CPU, memory và custom metrics. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- **Chất lượng:** v2 (có bước retrieve từ `KNOWLEDGE_BASE`) tăng accuracy từ `4.3%` lên `91.3%` và đạt **`100.0%` (23/23, 0 regression)** sau khi bổ sung 2 entry còn thiếu.
- **Chi phí:** v2 tốn gần **gấp đôi token/câu** (`108.8–114.6` vs `56.5`) và tổng cost gấp ~2 lần (`$0.000799` vs `$0.000396`) do phải đưa context vào prompt. Tuy nhiên, xét theo chỉ số **Cost / câu đúng**, v2 (`$0.00003472`) **rẻ hơn v1 (`$0.00039555`) hơn 11 lần** vì v1 tốn tiền cho 22/23 câu trả lời sai vô ích. Do đó "cost / câu đúng" phản ánh đúng hiệu quả kinh tế hơn "cost / câu".
- **Latency:** v2 chỉ chậm hơn v1 khoảng `~22–28 ms` ở `p95` (`214.0` vs `191.6 ms`) do thêm bước retrieval (~20ms) — một đánh đổi rất xứng đáng cho mức tăng gần +96 điểm % accuracy.

### Quality Gate trong CI/CD (Exercise 7.3)

Script `eval/run_eval.py` trả về **`exit code 0`** khi đạt `accuracy >= --min-accuracy` **và** không có câu nào bị regression so với `--baseline`, ngược lại trả về **`exit code 1`**. Trong GitHub Actions, bất kỳ step nào có exit code khác 0 sẽ làm job fail và **chặn merge PR**:

```yaml
# .github/workflows/eval-quality-gate.yml
name: Agent Eval Quality Gate
on: [pull_request]
jobs:
  eval-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r 06-lab-complete/benchmark-observability/develop/requirements.txt
      - name: Start agent v2 and run eval quality gate
        working-directory: 06-lab-complete/benchmark-observability/develop
        run: |
          AGENT_VERSION=v2 MOCK_ERROR_RATE=0 PORT=8002 python app.py &
          sleep 2
          python eval/run_eval.py \
            --url http://localhost:8002 \
            --min-accuracy 0.95 \
            --baseline ../../../reports/eval_v2_fixed.json
```

---

## 4. Observability stack (production)

*(Sẽ điền ở CP8)*

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

*(Sẽ điền ở CP8)*

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

*(Sẽ điền ở CP8)*

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. *(Sẽ điền ở CP8)*
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

*(Sẽ điền ở CP8)*
