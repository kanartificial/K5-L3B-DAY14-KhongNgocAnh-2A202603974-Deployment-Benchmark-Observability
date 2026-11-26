# Deployment Information

## Public URL
https://kana-test.up.railway.app

## Platform
Railway (deploy trực tiếp thư mục `06-lab-complete/` bằng `Dockerfile` + Redis service trên Railway)

## Test Commands

Đặt biến môi trường trước khi chạy (thay `<YOUR_AGENT_API_KEY>` bằng key đã cấu hình trên Railway):

```bash
BASE="https://kana-test.up.railway.app"
AGENT_API_KEY="<YOUR_AGENT_API_KEY>"
```

### 1. Health Check (Liveness)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Expected: 200
```

### 2. Readiness Check (Redis connected)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Expected: 200
```

### 3. API Test — Không có API Key (Authentication required)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401
```

### 4. API Test — Có API Key hợp lệ
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question": "Hello"}'
# Expected: 200
```

## Environment Variables Set (trên Railway Dashboard — không ghi vào code)
- `PORT` (do Railway tự cấp phát động)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (tham chiếu từ service Redis trên Railway: `${{Redis.REDIS_URL}}`)
- `AGENT_API_KEY` (secret đặt trực tiếp trong Railway Variables)
- `RATE_LIMIT_PER_MINUTE` (`30`)
- `DAILY_BUDGET_USD` (`1.0`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
