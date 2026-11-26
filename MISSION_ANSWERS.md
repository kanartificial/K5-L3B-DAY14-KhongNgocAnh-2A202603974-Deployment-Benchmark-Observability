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

### Exercise 2.1: Phân tích Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**
   - `python:3.11` (full Python distribution, gồm hệ điều hành Debian + Python 3.11 runtime + đầy đủ build tools, dung lượng ~1 GB).
2. **Working directory là gì?**
   - `/app` (`WORKDIR /app`) — thư mục làm việc mặc định bên trong container, nơi chứa mã nguồn và chạy các lệnh `COPY`, `RUN`, `CMD` phía sau.
3. **Tại sao `COPY requirements.txt` trước rồi mới `COPY app.py`?**
   - Để tận dụng **Docker layer cache**. Docker cache từng layer theo thứ tự lệnh; khi chỉ sửa code (`app.py`) mà không đổi `requirements.txt`, Docker tái sử dụng lại layer `pip install` đã cache thay vì tải và cài lại toàn bộ thư viện từ đầu, giúp build nhanh hơn rất nhiều.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh (hoặc tham số) mặc định khi container khởi chạy và **có thể bị ghi đè dễ dàng** bằng tham số truyền thêm ở cuối lệnh `docker run <image> <cmd>`.
   - `ENTRYPOINT` cố định chương trình chính mà container luôn chạy (chỉ ghi đè được khi dùng cờ `--entrypoint`); các tham số ở `docker run` hoặc `CMD` sẽ được truyền làm đối số cho `ENTRYPOINT`.

---

### Exercise 2.2: Build và chạy container `my-agent:develop`

Lệnh build từ thư mục gốc repo:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
```

Kết quả gọi container `my-agent:develop` (cổng `8000`):

```bash
docker run -d --name agent-dev -p 8000:8000 my-agent:develop
curl -i http://localhost:8000/health
curl -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
```

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:28:37 GMT
server: uvicorn
content-type: application/json

{"status":"ok","uptime_seconds":14.8,"container":true}
```

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:28:47 GMT
server: uvicorn
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`) và so sánh kích thước image

- **Stage 1 (`builder` — `FROM python:3.11-slim AS builder`):** Cài đặt các công cụ biên dịch (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` để build & cài đặt toàn bộ Python dependencies vào `/root/.local`. Image của stage này không dùng để deploy.
- **Stage 2 (`runtime` — `FROM python:3.11-slim AS runtime`):** Bắt đầu từ base image slim sạch, tạo non-root user `appuser`, chỉ copy các package đã cài từ stage 1 (`COPY --from=builder /root/.local /home/appuser/.local`) cùng mã nguồn (`main.py`, `utils/mock_llm.py`), cấu hình `HEALTHCHECK` và chạy bằng `uvicorn` với non-root user.
- **Tại sao image nhỏ hơn?**
  - Dùng base image `python:3.11-slim` thay vì `python:3.11` full.
  - Không mang theo `gcc`, `libpq-dev`, apt cache hay các file trung gian lúc biên dịch vào final image — chỉ giữ đúng runtime Python và `site-packages` cần thiết để chạy app.

**So sánh kích thước thực tế đo bằng `docker images | grep my-agent`:**

```text
my-agent      advanced   808dc7b9bd85   About a minute ago   163MB
my-agent      develop    9f12bf939c41   22 minutes ago       1.15GB
```

- **Develop (`my-agent:develop`):** `1.15 GB` (~`1150 MB`)
- **Production (`my-agent:advanced`):** `163 MB`
- **Chênh lệch:** giảm **`987 MB` (~`85.8%`)**

---

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

#### Sơ đồ kiến trúc các service

```text
Client (HTTP :80 / HTTPS :443)
        │
        ▼
  ┌───────────┐   proxy_pass + rate limit (10r/s) + security headers
  │   nginx   │ ────────────────────────────────────────────────────┐
  └───────────┘                                                     │
                                         Docker network: internal   ▼
                                                            ┌──────────────┐
                                                            │    agent     │ (port 8000, không expose ra ngoài)
                                                            └──────┬───────┘
                                                      ┌────────────┴────────────┐
                                                      ▼                         ▼
                                               ┌─────────────┐          ┌──────────────┐
                                               │    redis    │          │    qdrant    │
                                               │ (port 6379) │          │ (port 6333)  │
                                               └──────┬──────┘          └──────┬───────┘
                                                      ▼                         ▼
                                               [redis_data vol]         [qdrant_data vol]
```

**Các service và cách giao tiếp:**
- `nginx` (`nginx:alpine`): Reverse proxy & load balancer duy nhất mở cổng ra host (`80`, `443`), gắn security headers, rate limit 10 req/s và chuyển tiếp request sang `agent:8000`.
- `agent` (`02-docker/production/Dockerfile`, target `runtime`): Chạy FastAPI trên cổng nội bộ `8000`, chỉ khởi chạy sau khi `redis` và `qdrant` đều ở trạng thái `healthy`, kết nối qua DNS nội bộ của bridge network `internal` (`redis://redis:6379/0`, `http://qdrant:6333`).
- `redis` (`redis:7-alpine`): Cache session & rate limiting, lưu dữ liệu bền vững vào volume `redis_data`.
- `qdrant` (`qdrant/qdrant:v1.9.0`): Vector database cho RAG, lưu dữ liệu bền vững vào volume `qdrant_data`.

#### Kết quả `docker compose ps`

```text
NAME                       IMAGE                   SERVICE   STATUS                        PORTS
k5-day14-docker-agent-1    k5-day14-docker-agent   agent     Up About a minute (healthy)   8000/tcp
k5-day14-docker-nginx-1    nginx:alpine            nginx     Up About a minute             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   qdrant/qdrant:v1.9.0    qdrant    Up About a minute (healthy)   6333-6334/tcp
k5-day14-docker-redis-1    redis:7-alpine          redis     Up About a minute (healthy)   6379/tcp
```

#### Kết quả test qua Nginx

```bash
curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "microservices"}'
```

```http
HTTP/1.1 200 OK
Server: nginx
Date: Thu, 26 Nov 2026 08:20:50 GMT
Content-Type: application/json
Content-Length: 95
Connection: keep-alive
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy Agent Part 6 lên Railway

- **Public URL:** `https://kana-test.up.railway.app`
- **Thư mục deploy:** `06-lab-complete/` (sử dụng `06-lab-complete/Dockerfile` và `06-lab-complete/railway.toml`, kết nối tới Redis service trên cùng Railway project qua `REDIS_URL=${{Redis.REDIS_URL}}`).
- **Biến môi trường đã cấu hình trên Railway (không hardcode trong code):** `AGENT_API_KEY`, `REDIS_URL`, `ENVIRONMENT=production`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD` (còn `PORT` do Railway tự cấp phát).
- **Kết quả tự kiểm 4 lệnh CP6 (không lộ API key):**
  - `GET /health` → **`200`**
  - `GET /ready` → **`200`** (xác nhận kết nối Redis trên cloud thành công)
  - `POST /ask` (không có `X-API-Key`) → **`401`**
  - `POST /ask` (có `X-API-Key` hợp lệ) → **`200`**
- **Chi tiết & ảnh chụp:** xem [DEPLOYMENT.md](DEPLOYMENT.md), [screenshots/dashboard.png](screenshots/dashboard.png), [screenshots/running.png](screenshots/running.png), [screenshots/test.png](screenshots/test.png).

---

### Exercise 3.2: So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) | Tại sao khác nhau? |
|---|---|---|---|
| **Định dạng & phạm vi** | TOML (`[build]`, `[deploy]`), cấu hình cho **1 service** cụ thể trong project. | YAML (`services: [...]`), khai báo **Infrastructure as Code (Blueprint)** cho cả nhiều service (web, worker, Redis/DB) trong 1 file. | Railway thiên về cấu hình nhanh từng service qua UI/CLI và chỉ dùng `railway.toml` để override build/deploy; Render dùng Blueprint để dựng toàn bộ stack từ Git. |
| **Cách khai báo Build** | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"`. | `type: web`, `runtime: docker`, `dockerfilePath: ./Dockerfile`. | Render phân biệt rõ loại workload (`web`, `worker`, `cron`) ngay trong file Blueprint, còn Railway tự nhận diện HTTP service qua port lắng nghe. |
| **Health Check** | `healthcheckPath = "/health"`, `healthcheckTimeout = 30`. | `healthCheckPath: /health`. | Cả hai đều dùng `GET /health` để kiểm tra container sẵn sàng trước khi chuyển traffic (zero-downtime deploy), chỉ khác tên key theo schema từng nền tảng. |
| **Quản lý Biến môi trường & Secret** | Không khai báo secret trong `railway.toml`; đặt trực tiếp trên Railway Variables / CLI (`railway variables set`) và tham chiếu liên service bằng `${{Redis.REDIS_URL}}`. | Khai báo trực tiếp mục `envVars:` ngay trong `render.yaml`, hỗ trợ `generateValue: true` (tự sinh secret ngẫu nhiên) hoặc `sync: false` (nhập tay trên dashboard, không commit vào Git). | Blueprint của Render cần định nghĩa đầy đủ schema biến môi trường để tái tạo môi trường giống nhau giữa các lần deploy mà vẫn tránh lộ secret trong mã nguồn. |
| **Chính sách Restart** | Hỗ trợ khai báo rõ `restartPolicyType = "ON_FAILURE"` và `restartPolicyMaxRetries = 5`. | Render tự quản lý restart mặc định cho web service khi crash/unhealthy, không cần khai báo trong `render.yaml`. | Railway cho phép tinh chỉnh hành vi restart ngay trong `railway.toml`. |

---

### Exercise 3.3: Mô tả Pipeline CI/CD trên Google Cloud Run (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên nhánh `main` đi qua 4 bước tuần tự (`waitFor`):
1. **Test (`id: test`):** Chạy container `python:3.11-slim`, cài `requirements.txt` và chạy `pytest tests/`; nếu test fail sẽ dừng pipeline ngay.
2. **Build (`id: build`):** Build Docker image có tận dụng layer cache (`--cache-from ...:latest`) và gắn đồng thời 2 tag `$COMMIT_SHA` và `latest`.
3. **Push (`id: push`):** Đẩy tất cả các tag image vừa build lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`id: deploy` + `service.yaml`):** Deploy image theo `$COMMIT_SHA` lên **Cloud Run** (`asia-southeast1`) với cấu hình autoscale (`min-instances=1` tránh cold start, `max-instances=10`, `containerConcurrency=80`), giới hạn tài nguyên (`1 CPU`, `512Mi RAM`), inject secret an toàn từ **Secret Manager** (`--set-secrets` / `secretKeyRef`) và cấu hình `livenessProbe` (`/health`) cùng `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

**Phân tích mã nguồn:**
- **API key được kiểm tra ở đâu?**
  - Khai báo `API_KEY = os.getenv("AGENT_API_KEY", "demo-key-change-in-production")` và `api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)` (`develop/app.py:35-36`).
  - Hàm dependency `verify_api_key` (`develop/app.py:39-54`) kiểm tra header `X-API-Key` và được inject vào endpoint `POST /ask` thông qua `_key: str = Depends(verify_api_key)` (`develop/app.py:70`). Các endpoint `/` và `/health` được giữ public.
- **Điều gì xảy ra nếu thiếu hoặc sai key?**
  - Thiếu header `X-API-Key` → trả về **`401 Unauthorized`** (`Missing API key. Include header: X-API-Key: <your-key>`).
  - Header có giá trị nhưng không khớp `API_KEY` → trả về **`403 Forbidden`** (`Invalid API key.`).
- **Làm sao rotate key an toàn (không downtime)?**
  - Không thay đột ngột 1 key duy nhất mà hỗ trợ đồng thời danh sách key hợp lệ (ví dụ `AGENT_API_KEYS=old_key,new_key` từ biến môi trường / Secret Manager).
  - Các bước: (1) Tạo key mới và thêm vào danh sách key hợp lệ trên server (deploy), (2) Cập nhật client sang dùng key mới và theo dõi log cho đến khi không còn request dùng key cũ, (3) Xóa/thu hồi (revoke) key cũ khỏi cấu hình server.

**Kết quả test thực tế (`AGENT_API_KEY=secret-key-123`):**

1. Không có API key → `401 Unauthorized`:
```http
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:41:03 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. Sai API key (`X-API-Key: wrong-key`) → `403 Forbidden`:
```http
HTTP/1.1 403 Forbidden
date: Thu, 26 Nov 2026 08:41:03 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}
```

3. Có API key hợp lệ (`X-API-Key: secret-key-123`) → `200 OK`:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:41:03 GMT
server: uvicorn
content-length: 145
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

---

### Exercise 4.2: JWT Authentication (`04-api-gateway/production/auth.py` & `app.py`)

**JWT Flow trong `auth.py`:**
1. Client gửi `username` và `password` tới `POST /auth/token` (`production/app.py:105-118`).
2. `authenticate_user()` (`auth.py:70-75`) xác thực thông tin đăng nhập; sai sẽ trả về `401 Invalid credentials`.
3. `create_token()` (`auth.py:35-43`) tạo JWT với payload gồm `sub` (username), `role` (`user`/`admin`), `iat` (thời điểm cấp), `exp` (hết hạn sau 60 phút) và ký bằng thuật toán `HS256` với `JWT_SECRET`.
4. Client gửi token qua header `Authorization: Bearer <token>` ở các request tiếp theo tới `POST /ask`.
5. Dependency `verify_token()` (`auth.py:46-67`) giải mã và xác minh chữ ký/hạn dùng của token (stateless, không cần query DB mỗi request):
   - Thiếu header hoặc token hết hạn (`ExpiredSignatureError`) → `401 Unauthorized`.
   - Token sai chữ ký hoặc bị chỉnh sửa (`InvalidTokenError`) → `403 Forbidden`.
   - Hợp lệ → trả về `{"username": payload["sub"], "role": payload["role"]}` để áp dụng rate limit và cost guard theo từng user/role.

**Kết quả test thực tế (đã che JWT token):**

1. Gọi `POST /ask` không có token → `401 Unauthorized`:
```http
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:43:20 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

2. Lấy token từ `POST /auth/token` với tài khoản `student` / `demo123` → `200 OK`:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:43:20 GMT
server: uvicorn
content-length: 307
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"access_token":"<REDACTED_JWT_TOKEN>","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer <REDACTED_PREFIX>..."}
```

3. Gọi `POST /ask` kèm `Authorization: Bearer <REDACTED_JWT_TOKEN>` → `200 OK`:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:43:20 GMT
server: uvicorn
content-length: 184
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

---

### Exercise 4.3: Rate Limiting (`04-api-gateway/production/rate_limiter.py`)

**Phân tích mã nguồn:**
- **Algorithm được dùng:** **Sliding Window Counter** (cửa sổ trượt, `rate_limiter.py:17-71`). Mỗi `user_id` có một `deque` lưu timestamp của các request. Khi có request mới đến tại thời điểm `now`, hệ thống loại bỏ các timestamp cũ hơn `now - window_seconds` (`popleft()`). Nếu số phần tử còn lại `>= max_requests`, trả về `429 Too Many Requests` kèm các header `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, `Retry-After`; ngược lại ghi nhận `now` vào `deque`.
- **Giới hạn requests/minute:**
  - User thường (`rate_limiter_user`, `rate_limiter.py:86`): **`10` requests / 60 giây**.
  - Admin (`rate_limiter_admin`, `rate_limiter.py:87`): **`100` requests / 60 giây**.
- **Làm sao nâng/bypass limit cho admin?**
  - Trong `production/app.py:141`, dựa vào `role` giải mã từ JWT để chọn limiter riêng: `limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`. Nếu muốn bypass hoàn toàn cho admin, có thể kiểm tra `if role != "admin": rate_limiter_user.check(username)`. Tuy nhiên, thực tế vẫn nên đặt ngưỡng cao cho admin (như 100 req/phút) thay vì vô hạn để tránh vòng lặp lỗi từ client admin làm quá tải hệ thống.

**Kết quả test vòng lặp curl với tài khoản `student` (10 req/phút):**

```text
Request  1: HTTP 200 (requests_remaining: 9)
Request  2: HTTP 200 (requests_remaining: 8)
...
Request  9: HTTP 200 (requests_remaining: 1)
Request 10: HTTP 200 (requests_remaining: 0)
Request 11: HTTP 429 -> {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
Request 12: HTTP 429 -> {"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

Output đầy đủ `curl -i` khi chạm rate limit (`429 Too Many Requests`):
```http
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 08:43:21 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795682662
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

---

### Exercise 4.4: Cost Guard (`04-api-gateway/production/cost_guard.py`)

**Cách hoạt động của Cost Guard:**
1. **Trong bản demo `production/cost_guard.py`:**
   - Theo dõi số `input_tokens`, `output_tokens` và `request_count` theo từng user và từng ngày (`YYYY-MM-DD`), quy đổi ra chi phí USD dựa trên đơn giá model (`PRICE_PER_1K_INPUT_TOKENS`, `PRICE_PER_1K_OUTPUT_TOKENS`).
   - Trước khi gọi LLM, `check_budget(username)` kiểm tra hai tầng:
     - **Ngân sách toàn hệ thống** (`global_daily_budget_usd = $10/ngày`): vượt ngưỡng → log `CRITICAL` và trả `503 Service Unavailable`.
     - **Ngân sách từng user** (`daily_budget_usd = $1/ngày`): vượt ngưỡng → trả `402 Payment Required`; chạm `80%` (`warn_at_pct = 0.8`) → ghi log `WARNING`.
   - Sau khi LLM trả lời, `record_usage()` cộng dồn token/chi phí vào bản ghi của user và tổng chi phí hệ thống.

   Kết quả kiểm tra `GET /me/usage` sau 10 request của `student`:
   ```http
   HTTP/1.1 200 OK
   date: Thu, 26 Nov 2026 08:43:21 GMT
   server: uvicorn
   content-length: 184
   content-type: application/json
   x-content-type-options: nosniff
   x-frame-options: DENY
   x-xss-protection: 1; mode=block
   referrer-policy: strict-origin-when-cross-origin

   {"user_id":"student","date":"2026-11-26","requests":10,"input_tokens":40,"output_tokens":280,"cost_usd":0.000174,"budget_usd":1.0,"budget_remaining_usd":0.999826,"budget_used_pct":0.0}
   ```

2. **Cách triển khai Cost Guard trên production với Redis (stateless, theo bài 4.4):**
   - Lưu chi phí trong RAM sẽ mất khi restart và không đồng bộ khi chạy nhiều instance. Trên production, dùng **Redis** với key theo chu kỳ (theo tháng `budget:{user_id}:{YYYY-MM}` hoặc theo ngày `budget:{user_id}:{YYYY-MM-DD}`):
     - Đọc chi phí hiện tại: `current = float(r.get(key) or 0)`.
     - Nếu `current + estimated_cost > budget_limit` (ví dụ `$10/tháng`) → trả `False` (endpoint raise `402 Payment Required`).
     - Nếu còn ngân sách → cộng chi phí bằng `r.incrbyfloat(key, cost)` và đặt TTL tự hết hạn bằng `r.expire(key, 32 * 24 * 3600)` (32 ngày cho chu kỳ tháng, hoặc 86400s cho chu kỳ ngày) để tự reset sang kỳ mới mà không cần cron job dọn tay.

3. **Tại sao phải có cả Rate Limit lẫn Cost Guard?**
   - **Rate Limit bảo vệ tốc độ và hạ tầng:** Giới hạn số request/phút giúp chống spam, brute-force, DDoS và tránh quá tải CPU/worker/API upstream. Tuy nhiên, rate limit chỉ đếm *số lượng request*, không biết mỗi request tốn bao nhiêu token — một user gửi ít request nhưng mỗi request có prompt cực dài và output lớn vẫn có thể đốt rất nhiều tiền.
   - **Cost Guard bảo vệ ngân sách (tiền):** Đặt trần chi tiêu cứng theo USD/token cho từng user và toàn hệ thống để tránh hóa đơn LLM tăng đột biến. Ngược lại, chỉ có cost guard mà không có rate limit thì kẻ tấn công vẫn có thể spam hàng nghìn request nhỏ/lỗi làm nghẽn server.
   - Kết hợp cả hai (cùng Authentication) tạo thành phòng thủ nhiều lớp: **Auth (ai được gọi) → Rate Limit (gọi nhanh tới đâu) → Cost Guard (tiêu tối đa bao nhiêu tiền)**.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health Checks — Liveness (`/health`) vs Readiness (`/ready`)

**Phân tích mã nguồn (`05-scaling-reliability/develop/app.py` & `production/app.py`):**

| Tiêu chí | Liveness Probe (`GET /health`) | Readiness Probe (`GET /ready`) |
|---|---|---|
| **Câu hỏi kiểm tra** | Process/container có còn sống không? | Instance đã sẵn sàng nhận traffic từ người dùng chưa? |
| **Cách implement** | Trả về `200 OK` kèm `status`, `uptime_seconds`, `version`, `timestamp` và thông tin kiểm tra bộ nhớ (`develop/app.py:104-144`). Không nên trả lỗi chỉ vì dependency tạm mất kết nối nếu bản thân process vẫn khỏe. | Kiểm tra cờ `_is_ready` (`develop/app.py:147-168`) và kiểm tra kết nối Redis bằng `_redis.ping()` (`production/app.py:208-215`). Trả về `200 OK` nếu sẵn sàng, hoặc **`503 Service Unavailable`** khi đang khởi động, đang shutdown, hoặc mất kết nối Redis. |
| **Hành động của Platform / Load Balancer** | Nếu fail liên tiếp hoặc timeout → orchestrator (K8s, Docker, Railway/Render) **restart container**. | Nếu trả `503` → load balancer (Nginx/K8s Service) **tạm ngừng route traffic mới** vào instance đó mà **không restart** container. |

**Kết quả test thực tế trên `05-scaling-reliability/develop/app.py`:**

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:57:05 GMT
server: uvicorn
content-length: 195
content-type: application/json

{"status":"ok","uptime_seconds":1.8,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T08:57:06.350153+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}
```

```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:57:05 GMT
server: uvicorn
content-length: 37
content-type: application/json

{"ready":true,"in_flight_requests":1}
```

---

### Exercise 5.2: Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

**Cơ chế xử lý `SIGTERM` không cắt ngang request:**
1. **Theo dõi request đang chạy:** Middleware `track_requests` (`develop/app.py:72-81`) tăng `_in_flight_requests` khi có request mới và giảm trong khối `finally` khi xử lý xong.
2. **Bắt tín hiệu `SIGTERM` / `SIGINT`:** Đăng ký `handle_sigterm` (`develop/app.py:175-187`) và cấu hình `timeout_graceful_shutdown=30` ở `uvicorn.run()` (`develop/app.py:198`).
3. **Lifespan shutdown (`develop/app.py:54-66`):** Khi nhận `SIGTERM` (lúc deploy hoặc scale down):
   - Đặt `_is_ready = False` → `/ready` trả về `503` để load balancer ngừng gửi traffic mới vào instance này.
   - Vòng lặp chờ `_in_flight_requests == 0` (tối đa 30 giây) để các request đang chạy kịp hoàn tất.
   - Đóng tài nguyên và thoát tiến trình sạch sẽ (exit code `0`).

**Kết quả test thực tế (gửi 2 request `POST /ask` song song rồi gửi `kill -SIGTERM` ngay sau 0.5s):**

Cả 2 request đang chạy đều hoàn thành trọn vẹn với `200 OK`, không bị ngắt kết nối giữa chừng:

```http
# Request 1
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}

# Request 2
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

Log phía container khi dừng `k5-day14-scaling-agent-1` bằng `docker stop` (gửi `SIGTERM`):
```text
agent-1  | INFO:     Shutting down
agent-1  | INFO:     Waiting for application shutdown.
agent-1  | INFO:app:Instance instance-bd8965 shutting down
agent-1  | INFO:     Application shutdown complete.
agent-1  | INFO:     Finished server process [1]
```

---

### Exercise 5.3: Stateless Design (`05-scaling-reliability/production/app.py`)

**Tại sao lưu state trong RAM (in-memory) bị hỏng khi chạy nhiều instance?**
- Mỗi container/instance có vùng nhớ RAM độc lập. Khi có Load Balancer (Nginx) phân tán request theo kiểu round-robin:
  - Request 1 của User A đi vào `Instance 1` → session/lịch sử hội thoại chỉ được lưu trong RAM của `Instance 1`.
  - Request 2 của User A đi vào `Instance 2` → `Instance 2` không thấy session trong RAM của nó → **mất ngữ cảnh hội thoại / báo lỗi 404**.
  - Ngoài ra, khi 1 instance crash, restart hoặc deploy mới, toàn bộ state trong RAM đều bị mất sạch.

**Cách `production/app.py` refactor thành Stateless với Redis:**
- Không lưu `conversation_history` trong biến dictionary cục bộ trên production; thay vào đó dùng **Redis dùng chung** qua biến môi trường `REDIS_URL=redis://redis:6379/0` (`production/app.py:36-41`).
- Các hàm `save_session()` và `load_session()` (`production/app.py:59-73`) đọc/ghi lịch sử hội thoại theo key `session:{session_id}` với `_redis.setex(..., ttl_seconds=3600, ...)` (tự động hết hạn sau 1 giờ để tránh đầy bộ nhớ) và giới hạn tối đa 20 messages/session (`append_to_history`, dòng 76–90).
- Mỗi instance sinh định danh riêng `INSTANCE_ID` (`production/app.py:52`) và trả về trong trường `served_by` của `POST /chat` để kiểm chứng bất kỳ instance nào cũng phục vụ được cùng một session.

---

### Exercise 5.4: Load Balancing với Nginx + 3 Agent Instances (`05-scaling-reliability/production/`)

**Kiến trúc stack (`docker-compose.yml` + `nginx.conf`):**
```text
Client (:8080) ──▶ Nginx (round-robin + proxy_next_upstream)
                       ├──▶ agent-1 (instance-bd8965) ──┐
                       ├──▶ agent-2 (instance-9ff677) ──┼──▶ Redis (:6379)
                       └──▶ agent-3 (instance-737266) ──┘
```
- `nginx.conf` dùng Docker DNS (`resolver 127.0.0.11 valid=10s`) trỏ tới `upstream agent_cluster { server agent:8000; }`, gắn header `X-Served-By $upstream_addr` và cấu hình failover tự động `proxy_next_upstream error timeout http_503; proxy_next_upstream_tries 3;`.

**Lệnh khởi chạy và kiểm tra trạng thái stack:**
```bash
docker compose -p k5-day14-scaling up -d --build --scale agent=3
docker compose -p k5-day14-scaling ps
```

```text
NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     37 seconds ago   Up 25 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     37 seconds ago   Up 25 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     37 seconds ago   Up 26 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     37 seconds ago   Up 25 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     37 seconds ago   Up 36 seconds (healthy)   6379/tcp
```

---

### Exercise 5.5: Kiểm chứng Stateless & Failover (`test_stateless.py`)

**1. Kết quả chạy `python test_stateless.py` (gửi 5 câu hỏi liên tiếp trong cùng 1 `session_id` qua Nginx `:8080`):**

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: d6a2f97b-be08-421b-8930-2995a20c9f87

Request 1: [instance-bd8965]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-9ff677]
  Q: Why do we need containers?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 3: [instance-737266]
  Q: What is Kubernetes?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 4: [instance-bd8965]
  Q: How does load balancing work?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 5: [instance-9ff677]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-bd8965', 'instance-9ff677', 'instance-737266'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Kubernetes?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: How does load balancing work?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Redis used for?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...

✅ Session history preserved across all instances via Redis!
```

**2. Kiểm chứng failover khi dừng 1 instance (`docker stop k5-day14-scaling-agent-1`) và gọi tiếp với cùng `session_id`:**

```http
HTTP/1.1 200 OK
Server: nginx/1.31.10
Date: Thu, 26 Nov 2026 09:01:42 GMT
Content-Type: application/json
X-Served-By: 172.18.0.4:8000, 172.18.0.5:8000

{"session_id":"d6a2f97b-be08-421b-8930-2995a20c9f87","question":"Is my session still alive after killing instance 1?","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","turn":7,"served_by":"instance-9ff677","storage":"redis"}
```

Kiểm tra `GET /chat/d6a2f97b-be08-421b-8930-2995a20c9f87/history`:
```text
session_id: d6a2f97b-be08-421b-8930-2995a20c9f87 count: 12
```

**Giải thích kết quả:**
- 5 request liên tiếp được Nginx phân tán đều qua **cả 3 instance** (`instance-bd8965`, `instance-9ff677`, `instance-737266`), nhưng lịch sử hội thoại vẫn giữ nguyên đủ 10 message (5 cặp user–assistant) vì toàn bộ session lưu tập trung trên Redis.
- Khi dừng `agent-1` (`172.18.0.4:8000`), Nginx phát hiện lỗi kết nối và tự động chuyển tiếp sang `agent-2` (`172.18.0.5:8000`, thấy rõ ở header `X-Served-By: 172.18.0.4:8000, 172.18.0.5:8000`) nhờ `proxy_next_upstream`. Request vẫn trả về `200 OK` và lịch sử hội thoại tăng lên 12 message không mất dữ liệu.
- Sau khi kiểm thử xong đã dọn sạch stack bằng `docker compose -p k5-day14-scaling down`.

---

## Part 6: Final Project (`check_production_ready.py`)

Đã hoàn thiện toàn bộ các module trong `06-lab-complete/` (`app/config.py`, `app/auth.py`, `app/redis_client.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) mà không chỉnh sửa `check_production_ready.py`.

**Kết quả chạy `python check_production_ready.py` (đầy đủ với Docker):**
- Kích thước Docker image (multi-stage `python:3.11-slim`, non-root `appuser`): **`160 MB`** (< 500 MB), thời gian build `19s`.
- `docker stop` graceful shutdown: **`exit code 0` trong `0.9s`** (< 10s).
- Stateless rate limit & cost guard lưu trên Redis; `/health` luôn trả `200` còn `/ready` trả `503` khi Redis mất kết nối.

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI Log

| Checkpoint | Câu hỏi / Prompt | Kết quả AI hỗ trợ | Tự kiểm tra / Chỉnh sửa |
|---|---|---|---|
| CP1 | Soạn mục CP1 trong `MISSION_ANSWERS.md`. | Trình bày câu trả lời Exercise 1.1–1.3 bằng tiếng Việt. | Đối chiếu lại từng số dòng với `develop/app.py`, `production/app.py`, `production/config.py` và kiểm chứng toàn bộ HTTP response cũng như log shutdown từ kết quả chạy thực tế. |
| CP2 | Hướng dẫn sửa lỗi build Docker và điền mục CP2 trong `MISSION_ANSWERS.md`. | Soạn câu trả lời Dockerfile, multi-stage, sơ đồ kiến trúc và tính % chênh lệch kích thước image. | Tự build 2 image (`1.15GB` vs `163MB`), bật stack Compose và kiểm chứng response `200 OK` qua Nginx. |
| CP3 | Soạn mục CP3 trong `MISSION_ANSWERS.md`. | Tổng hợp giải thích API Key, JWT, Rate Limiting, Cost Guard và định dạng output `curl -i`. | Tự chạy kiểm chứng đủ các mã HTTP `401`, `403`, `200`, `429` và `/me/usage`, đối chiếu số dòng code và che toàn bộ JWT token trước khi lưu. |
| CP4 | Soạn mục CP4 trong `MISSION_ANSWERS.md`  | Trình bày phân tích `/health` vs `/ready`, graceful shutdown, stateless với Redis và kết quả test load balancing/failover. | Chạy thực tế bản `develop` (`/health`, `/ready`, `SIGTERM` với 2 request song song), bật stack `k5-day14-scaling` với 3 instance `agent`, chạy `test_stateless.py`, thử `docker stop agent-1` kiểm chứng failover và dọn stack bằng `down`. |
| CP5 | Cập nhật mục CP5 trong `MISSION_ANSWERS.md`. | Trình bày kết quả chạy CP5 | Chạy đầy đủ `python check_production_ready.py` có Docker xác nhận `PASS 12/12` (`43/43 checks passed`, image `160 MB`, `docker stop` `0.9s`), đảm bảo không sửa `check_production_ready.py` và không commit `.env`. |
| CP6 | Hướng dẫn deploy lên Railway và hoàn thiện report  CP6 (`DEPLOYMENT.md`, Part 3). | Trình bày `DEPLOYMENT.md`, bảng so sánh `railway.toml` vs `render.yaml` và mô tả pipeline Cloud Run từ `cloudbuild.yaml`/`service.yaml`. | Tự deploy `06-lab-complete/` lên Railway (`https://kana-test.up.railway.app`), cấu hình Redis và biến môi trường trên nền tảng, tự chạy kiểm chứng 4 lệnh `curl` (`200`, `200`, `401`, `200`) và chụp ảnh bằng chứng lưu vào `screenshots/`. |
| CP7 | Chạy benchmark local (Exercise 7.1–7.3), sửa `KNOWLEDGE_BASE` và điền `BENCHMARK_REPORT.md`. | Chạy đủ 4 mức concurrency, 3 mức `MOCK_SLOW_RATE`, eval `v1`/`v2`/`v2_fixed`, bổ sung 2 entry (`jwt`, `hpa`) và tổng hợp số liệu vào `BENCHMARK_REPORT.md` + mẫu CI Quality Gate. | Đối chiếu từng con số trong `BENCHMARK_REPORT.md` khớp 100% với 10 file JSON trong `reports/`, xác nhận `eval_v2_fixed.json` đạt `23/23` (`100%`, 0 regression, `✅ PASS`). |
| CP8 | Dựng stack Observability (`k5-day14-observability`), chạy Locust headless `scale_1`/`scale_3`, kích hoạt alert và hoàn thiện `BENCHMARK_REPORT.md`. | Phát hiện & sửa lỗi `PYTHONUSERBASE` trong `production/Dockerfile`, chạy Locust 100 users/2 phút cho 1 và 3 instance, lấy trace chậm/lỗi kèm log JSON, kích hoạt 3 alert firing và chụp đủ 4 ảnh Part 7. | Kiểm tra trực quan cả 4 ảnh (`grafana-dashboard.png`, `jaeger-slow-trace.png`, `jaeger-error-trace.png`, `prometheus-alert-firing.png`), đối chiếu bảng mục 5 khớp 100% với `scale_1_stats.csv` và `scale_3_stats.csv`, và dọn sạch stack bằng `down -v`. |
