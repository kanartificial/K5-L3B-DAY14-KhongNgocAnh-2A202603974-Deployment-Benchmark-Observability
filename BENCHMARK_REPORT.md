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

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [screenshots/grafana-dashboard.png](screenshots/grafana-dashboard.png)
  - Đọc từ dashboard lúc có tải: Traffic `/ask` đạt ~`60 req/s` (phân bổ đều ~`30 req/s` mỗi instance ở panel *Requests/s theo instance*), `p95` bình thường `~550–650 ms` và tăng vọt lên `1.67 s` khi có tail latency, `LLM cost (1h)` đạt `$0.5120`, *Cost burn rate* vượt ngưỡng `$2/giờ`.
- [x] Một trace chậm trong Jaeger (thấy span `chat mock-llm-small` chiếm 98.5% tổng thời gian): [screenshots/jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (HTTP `503`, biểu tượng lỗi đỏ ở `chat mock-llm-small` → `agent.run` → `POST /ask`): [screenshots/jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với **3 alert cùng đang firing**: [screenshots/prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời câu hỏi Exercise 7.4 (Observability stack):**
1. **Khoảng cách giữa `avg` và `p95` trên Grafana:** Trong biểu đồ *Latency /ask*, đường `avg` nằm gần `p50` (~`250 ms`), trong khi `p95` cao hơn nhiều (`~600 ms` và nhảy lên `1.67 s` khi có slow spike) vì 3–30% request chậm bị 90%+ request nhanh kéo trung bình xuống.
2. **Tại sao `input tokens/s` lớn hơn `output tokens/s` trên panel *Tokens/s*?** Vì mỗi request của agent v2 đều ghép thêm `SYSTEM_PROMPT` + đoạn tài liệu retrieve từ `KNOWLEDGE_BASE` + câu hỏi người dùng vào prompt đầu vào (~`74–95` input tokens), trong khi câu trả lời đầu ra ngắn gọn hơn (~`37–55` output tokens).
3. **Tại sao endpoint `/metrics` bị chặn (`return 404;`) ở Nginx (`nginx/nginx.conf:22-24`)?** Vì `/metrics` lộ thông tin nội bộ của hệ thống (tên route, lưu lượng, phiên bản, chi phí, tỉ lệ lỗi...) và có thể bị lợi dụng để thu thập thông tin hoặc DDoS scrape. Prometheus scrape trực tiếp container `agent:8000/metrics` qua Docker internal network `obs_net`, không cần expose ra Internet qua Nginx.

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`for: 1m`, ngưỡng `> 5%`) | **89 giây** (~1m29s) | *Error rate*, *Requests/s theo status code* (`503`), *LLM calls theo kết quả* |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`for: 2m`, ngưỡng `> 1s`) | **139 giây** (~2m19s) | *Latency p95*, *Latency /ask — p50 / p95 / p99*, *LLM latency p95 theo model* |
| C | `LLM_MODEL=mock-llm-large` (hoặc tải cao kéo dài) | `LLMCostBurnRateHigh` (`for: 2m`, ngưỡng `> $2/giờ`) | **~2 phút** (đã quan sát firing sau tải Locust liên tục ở `$6+/giờ`) | *Cost burn rate (USD/giờ)*, *LLM cost (1h)* |
| D | `docker pause` 1 instance (`agent-3`) | `AgentInstanceDown` (`for: 30s`, `up == 0`) | **59 giây** (~52s sau lệnh `pause`) | *Instances up*, *Requests/s theo instance* |
| E | `AGENT_VERSION=v1` | **Không có alert nào firing** | N/A | Chỉ thấy `Retrieval hit ratio` giảm (nếu có theo dõi), các Golden Signals hạ tầng đều xanh bình thường |

**Phân tích thí nghiệm E (`AGENT_VERSION=v1`) và lỗi 504 ở Nginx:**
- **Vì sao thí nghiệm E không làm alert nào firing & cách phát hiện trên production:** Khi đổi sang `v1`, agent vẫn trả `HTTP 200 OK` nhanh hơn (`~190 ms`) và rẻ hơn (`~56 tokens/câu`), nên toàn bộ alert hạ tầng (error rate, latency, availability, cost) đều **im lặng hoàn toàn** dù accuracy rơi từ `100%` xuống `4.3%`. Trên production, để phát hiện sự cố suy giảm chất lượng ("silent failure") này cần kết hợp:
  1. **CI/CD Eval Quality Gate** chạy `eval/run_eval.py` trên golden dataset trước mỗi lần deploy (như mục 3).
  2. **Online evaluation / LLM-as-a-judge** lấy mẫu ngẫu nhiên (vd 5% traffic) chấm điểm tự động và xuất metric chất lượng (hoặc user feedback thumbs-up/down) lên Prometheus để gắn alert khi điểm tụt.
  3. Theo dõi các proxy metric đặc thù của RAG như `retrieval_hit_ratio` (tỉ lệ tìm thấy context bị tụt về 0% ở `v1`).
- **Vì sao lỗi `504 Gateway Timeout` ở Nginx không hiện trên metric của agent?** Khi agent bị treo/quá chậm vượt `proxy_read_timeout 10s`, chính **Nginx** ngắt kết nối và trả `504` cho client trước khi request kịp hoàn tất ở middleware của FastAPI. Do đó counter `http_requests_total` bên trong agent không ghi nhận mã `504` — trên production cần giám sát thêm metrics ở tầng Reverse Proxy / Load Balancer (Nginx/Envoy) hoặc synthetic probe từ bên ngoài.

### 4.3 Debug bằng trace

Chọn 1 trace chậm thực tế từ Jaeger (`screenshots/jaeger-slow-trace.png`):

- `trace_id`: `a43e4cbaa51cce787c733457ec93416f`
- Tổng thời gian: **`1702.2 ms`** (`1.7 s` trên Jaeger UI)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1676.3 ms`**, chiếm **`98.5%`** tổng thời gian; trong khi `agent.retrieve_context` chỉ tốn `22.1 ms` ≈ `1.3%`)
- Dòng log JSON tương ứng (grep từ `docker compose -p k5-day14-observability logs agent | grep a43e4cbaa51cce787c733457ec93416f`):

```json
{"ts": "2026-11-26T10:49:17.383484+00:00", "level": "INFO", "service": "observable-agent", "instance": "12b7ab8c5bdc", "event": "llm_call", "trace_id": "a43e4cbaa51cce787c733457ec93416f", "span_id": "f0df5f259d127269", "request_id": "2950a5798eec", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1676.3}
{"ts": "2026-11-26T10:49:17.383895+00:00", "level": "INFO", "service": "observable-agent", "instance": "12b7ab8c5bdc", "event": "http_request", "trace_id": "a43e4cbaa51cce787c733457ec93416f", "span_id": "f0df5f259d127269", "request_id": "2950a5798eec", "method": "POST", "route": "/ask", "status": 200, "ms": 1702.2}
```

*(Trace lỗi `c2b4e7bfc1eb719af2a5896520dc4128` trong `screenshots/jaeger-error-trace.png`: `POST /ask` trả `HTTP 503` sau `115.0 ms` với lỗi xuất phát từ span `chat mock-llm-small` `91.3 ms`.)*

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated` và `POST /ask`):

| Số instance | RPS (`Aggregated` / `/ask`) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 64.34 / 58.35 | 200 / 210 | 570 / 590 | 1700 / 1700 | 77 / 7678 (1.00%) |
| 3 | 64.38 / 58.62 | 200 / 210 | 610 / 660 | 1700 / 1700 | 66 / 7683 (0.86%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không cải thiện rõ rệt p95/p99 hay RPS** trong bài test này vì hai nguyên nhân:
1. **Nút thắt latency nằm ở I/O gọi upstream LLM** (`MOCK_LATENCY_MS=120` + `MOCK_SLOW_RATE=0.03` cộng `1500 ms`), không phải CPU của container agent. Thêm replica chỉ giúp tăng sức chứa đồng thời và khả năng chịu lỗi (HA), không thể làm một cuộc gọi LLM chậm chạy nhanh hơn.
2. **Tải đầu vào bị giới hạn bởi `wait_time` của Locust** (`between(0.5, 2)` giây): 100 user ảo chỉ tạo tối đa ~`64–66 req/s`, mức này 1 instance `async` vẫn gánh được chưa bị bão hòa CPU. Để giảm `p95`/`p99` thực sự khi nút thắt ở LLM, cần tối ưu ở tầng ứng dụng/model như **semantic cache trên Redis**, **streaming response (giảm TTFT)**, **chọn model nhanh hơn** hoặc **timeout + fallback model**.

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Đo bằng percentile (`p95`/`p99`), không đo bằng trung bình (`avg`):** Average che giấu hoàn toàn tail latency; chỉ cần 3–10% request chậm là trải nghiệm người dùng đã tệ đi rõ rệt dù `avg` trông vẫn đẹp.
  2. **Đo cả hiệu năng lẫn chất lượng (Eval Quality Gate):** Hệ thống có thể xanh toàn bộ Golden Signals (`200 OK`, latency thấp, cost rẻ) nhưng vẫn trả lời sai hoàn toàn (như thí nghiệm `AGENT_VERSION=v1`). Cần chạy golden dataset eval trong CI và theo dõi `cost / câu đúng`.
  3. **Liên kết 3 trụ cột Metrics – Logs – Traces:** Prometheus/Grafana báo *có vấn đề gì* và *khi nào* (alert firing), Jaeger chỉ ra *chậm/lỗi ở span nào* (`chat mock-llm-small` chiếm 98.5%), và JSON log gắn `trace_id` cung cấp ngữ cảnh chi tiết để debug nhanh trong vài giây.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - **TTFT (Time To First Token)** và **tokens/giây** nếu dùng streaming để đo cảm nhận tốc độ thực của người dùng.
  - **Nginx / API Gateway metrics** (tỉ lệ `401`, `429`, `402`, `502`/`504`) để bắt lỗi xảy ra trước khi tới agent.
  - **Redis health & latency metrics** (hit rate của cache, số lượng rate-limit block, thời gian phản hồi Redis).
  - **Online Quality / Hallucination score** (chấm mẫu tự động hoặc tỉ lệ user thumbs-down) kèm alert khi chất lượng giảm dưới ngưỡng SLO.
