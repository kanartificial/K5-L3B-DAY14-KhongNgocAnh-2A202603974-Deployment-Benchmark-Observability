# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Các anti-pattern phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secret trực tiếp trong mã nguồn** (`develop/app.py:17-18`):
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` được ghi cứng trong code. Nếu push lên GitHub public sẽ bị lộ thông tin xác thực ngay lập tức (và vẫn còn trong lịch sử git dù sau đó xoá đi).
   - *Cách sửa ở `production/config.py:27,32`*: đọc secret từ biến môi trường (`os.getenv("OPENAI_API_KEY", "")`, `os.getenv("AGENT_API_KEY", "")`) và kiểm tra ngay lúc khởi động (`validate()`).
2. **In secret ra log dạng plain text** (`develop/app.py:34`):
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` ghi trực tiếp API key ra stdout/log ở mỗi request.
   - *Cách sửa ở `production/app.py:111-115`*: chỉ log metadata không nhạy cảm (`event`, `question_length`, `client_ip`) ở định dạng JSON.
3. **Không quản lý cấu hình tập trung / hardcode cấu hình runtime** (`develop/app.py:21-22, 52`):
   - `DEBUG = True`, `MAX_TOKENS = 500` và `port=8000` bị ghi cứng. Các nền tảng cloud (Railway, Render, Cloud Run) cấp phát `PORT` động và cần cấu hình khác nhau giữa dev/staging/prod.
   - *Cách sửa ở `production/config.py:14-35`*: dùng dataclass `Settings` đọc `HOST`, `PORT`, `DEBUG`, `ENVIRONMENT`, `MAX_TOKENS`... từ biến môi trường kèm giá trị mặc định hợp lý.
4. **Bind vào `localhost` thay vì `0.0.0.0`** (`develop/app.py:51`):
   - `host="localhost"` chỉ nhận kết nối nội bộ trong cùng máy/container; traffic từ bên ngoài Docker container hoặc load balancer trên cloud sẽ không gọi vào được.
   - *Cách sửa ở `production/config.py:17` & `production/app.py:196`*: mặc định bind vào `0.0.0.0`.
5. **Bật cứng chế độ debug auto-reload** (`develop/app.py:53`):
   - `reload=True` liên tục theo dõi thay đổi file và restart worker, gây tốn CPU/RAM và thiếu ổn định trên production.
   - *Cách sửa ở `production/app.py:198`*: dùng `reload=settings.debug`, với `DEBUG` mặc định là `false`.
6. **Dùng `print()` thay vì structured logging** (`develop/app.py:33-34, 38, 48`):
   - `print()` không có timestamp, log level hay cấu trúc chuẩn, rất khó tìm kiếm, lọc hoặc phân tích trên các hệ thống gom log (Loki, Datadog, CloudWatch).
   - *Cách sửa ở `production/app.py:28-32`*: dùng module `logging` của Python xuất log JSON có cấu trúc.
7. **Thiếu endpoint health check và readiness** (`develop/app.py`):
   - Không có `/health` hay `/ready`, nên nền tảng cloud/orchestrator không biết container đã crash để tự restart, cũng không biết instance đã sẵn sàng nhận traffic chưa.
   - *Cách sửa ở `production/app.py:135-161`*: cung cấp `GET /health` (liveness) và `GET /ready` (readiness, trả về `503` khi `is_ready` chưa là `True`).
8. **Không xử lý graceful shutdown** (`develop/app.py`):
   - Không bắt tín hiệu `SIGTERM` và không có bước dọn dẹp khi tắt, khiến các request đang xử lý bị cắt ngang và dễ rò rỉ kết nối DB/Redis khi deploy hoặc scale down.
   - *Cách sửa ở `production/app.py:39-68, 180-189`*: dùng FastAPI `lifespan` kết hợp `signal.SIGTERM` handler để chuyển `is_ready = False` và chờ request đang chạy hoàn tất trước khi tắt.

---

### Exercise 1.2: Chạy thử bản develop

Lệnh đã chạy trong `01-localhost-vs-production/develop/` (lưu ý: bản `develop/app.py` nhận `question` qua query parameter):

```bash
curl -sS -i http://localhost:8000/
curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả thực tế:

```http
HTTP/1.1 200 OK
content-type: application/json

{"message":"Hello! Agent is running on my machine :)"}
```

```http
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Log server ghi nhận (thấy rõ API key bị lộ ra stdout):

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.
```

**Nhận xét:** Ứng dụng chạy được trên localhost nhưng **chưa sẵn sàng cho production** vì làm lộ secret trong code và log, chỉ bind ở `localhost:8000`, bật cứng `reload=True`, thiếu `/health` và `/ready`, và không xử lý graceful shutdown.

---

### Exercise 1.3: So sánh bản Develop và Production

Kết quả thực tế khi chạy `01-localhost-vs-production/production/app.py`:

```bash
# GET /health -> 200 OK
{"status":"ok","uptime_seconds":1.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:27:15.346019+00:00"}

# GET /ready -> 200 OK
{"ready":true}

# POST /ask (JSON body {"question": "Hello"}) -> 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

Khi gửi tín hiệu `SIGTERM`, server log lần lượt `Shutting down` → `Waiting for application shutdown.` → `Application shutdown complete.` rồi mới dừng hẳn.

#### Bảng so sánh

| Tính năng | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config & Secrets** | Hardcode trong code (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`) | Đọc từ biến môi trường qua dataclass `Settings` + kiểm tra `validate()` lúc khởi động | Tránh lộ secret lên Git, dễ đổi cấu hình giữa dev/staging/prod mà không sửa code, và phát hiện lỗi sớm (fail fast) nếu thiếu biến bắt buộc trên prod. |
| **Host & Port** | Cố định `host="localhost"`, `port=8000` | `HOST` (mặc định `0.0.0.0`), `PORT` đọc từ env var | Container và nền tảng cloud (Railway/Render/Cloud Run) cấp `PORT` động và cần `0.0.0.0` để nhận kết nối từ bên ngoài. |
| **Debug / Reload** | `DEBUG = True`, bật cứng `reload=True` | `DEBUG` mặc định `false`; `reload=settings.debug` | Auto-reload gây tốn tài nguyên, chạy thêm process watcher và dễ khiến server restart ngoài ý muốn trên production. |
| **Health & Readiness** | Không có | `GET /health` (liveness) & `GET /ready` (readiness, trả 503 khi chưa sẵn sàng) | Platform dựa vào `/health` để tự restart container khi treo/crash, còn load balancer dựa vào `/ready` để chỉ gửi traffic vào instance đã sẵn sàng (deploy không downtime). |
| **Logging** | Dùng `print()` (làm lộ cả API key) | Structured JSON logging qua module `logging`; không log secret | Log có cấu trúc kèm timestamp và level giúp hệ thống giám sát (Loki, Datadog, CloudWatch) dễ parse, tìm kiếm và tạo cảnh báo mà không rò rỉ thông tin nhạy cảm. |
| **Shutdown** | Tắt đột ngột | `lifespan` shutdown hook + `SIGTERM` handler đặt `is_ready = False` và chờ request hoàn tất | Không cắt ngang request của người dùng, tránh mất dữ liệu dở dang và đóng kết nối DB/Redis an toàn khi deploy hoặc scale down. |
| **CORS & Input Validation** | Không có CORS; nhận `question` qua query param | `CORSMiddleware` cấu hình qua `ALLOWED_ORIGINS`; nhận JSON body kèm kiểm tra trả lỗi `422` | Giới hạn domain được phép gọi API từ trình duyệt và trả mã lỗi rõ ràng khi client gửi thiếu/sai dữ liệu. |

---

## Part 2: Docker

*(Chưa làm — CP2)*

---

## Part 3: Cloud Deployment

*(Chưa làm — CP6)*

---

## Part 4: API Security

*(Chưa làm — CP3)*

---

## Part 5: Scaling & Reliability

*(Chưa làm — CP4)*

---

## Part 6: Final Project (`check_production_ready.py`)

*(Chưa làm — CP5)*

---

## AI Log

| Checkpoint | Câu hỏi / Prompt | Kết quả AI hỗ trợ | Tự kiểm tra / Chỉnh sửa |
|---|---|---|---|
| CP1 | Soạn mục Part 1 trong `MISSION_ANSWERS.md`. | Trình bày câu trả lời Exercise 1.1–1.3 bằng tiếng Việt. | Đối chiếu lại từng số dòng với `develop/app.py`, `production/app.py`, `production/config.py` và kiểm chứng toàn bộ HTTP response cũng như log shutdown từ kết quả chạy thực tế. |
