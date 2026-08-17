# LinkPlease

## Overview
**LinkPlease** is an enterprise-grade Instagram Direct Message (DM) automation engine and SaaS dashboard designed to handle high-concurrency webhook streams from Instagram/PseudoGram. It processes incoming post comment webhooks, evaluates customizable keyword automation rules, and dispatches automated DMs via the PseudoGram Host API while maintaining strict operational guarantees for idempotency, rate limiting, retry handling, status reconciliation, and worker recovery.

---

## Architecture
```
                                  ┌───────────────────────────┐
                                  │   Instagram Webhook Host  │
                                  └─────────────┬─────────────┘
                                                │ POST /webhook (HMAC-SHA256)
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ FastAPI Application Server                                                              │
│                                                                                         │
│  ┌───────────────────────┐   Fast In-Memory ACK    ┌─────────────────────────────────┐  │
│  │ Recent Event LRU Cache│ <─────────────────────> │ POST /webhook (HTTP 200 <0.3s)  │  │
│  └───────────────────────┘                         └────────────────┬────────────────┘  │
│                                                                     │ Async Task        │
│                                                                     ▼                   │
│                                                    ┌─────────────────────────────────┐  │
│                                                    │ Webhook Event Ingestion Routine │  │
│                                                    └────────────────┬────────────────┘  │
└─────────────────────────────────────────────────────────────────────┼───────────────────┘
                                                                      │
                                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL Database (Persistent Storage)                                                │
│                                                                                         │
│  ┌──────────────────────┐  ┌─────────────────────────────┐  ┌────────────────────────┐ │
│  │ WebhookEvents        │  │ UserRuleDeliveries          │  │ DMTask Persistent      │ │
│  │ (unique: event_id)   │  │ (unique: rule_id, user_id)  │  │ Queue                  │ │
│  └──────────────────────┘  └─────────────────────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────▲───────────────────┘
                                                                      │ Poll / State Sync
                                                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Persistent Background Worker & Reconciliation Engine                                    │
│                                                                                         │
│  ┌───────────────────────────────┐   Check Limit   ┌─────────────────────────────────┐  │
│  │ RateLimitTick Sliding Window  │ <─────────────> │ PseudoGram Host API Client      │  │
│  │ (Max 10 calls / 60s)          │                 │ - POST /v1/dm/send (202 / 500) │  │
│  └───────────────────────────────┘                 │ - GET /v1/dm/{dm_id} (Status)   │  │
│                                                    └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                                                      │
                                                                      ▼
                                                     ┌─────────────────────────────────┐
                                                     │ React SaaS Dashboard            │
                                                     └─────────────────────────────────┘
```

The system flow operates as follows:
1. **Webhook Ingestion**: `POST /webhook` receives raw comment payloads, validates optional HMAC-SHA256 signatures (`X-PseudoGram-Signature`), filters duplicates via in-memory cache, and acknowledges HTTP 200 within sub-300ms.
2. **FastAPI Processing**: Non-blocking background routines persist events to PostgreSQL with DB-level `event_id` unique constraints and evaluate active keyword rules.
3. **Idempotency & Deduplication**: Database unique constraints `(rule_id, user_id)` guarantee that a user receives at most **one DM per rule**, regardless of comment frequency.
4. **Persistent Job Queue**: Matched DM tasks are queued in table `dm_tasks`, surviving process restarts.
5. **Background Worker & Rate Limiting**: The background worker polls `dm_tasks`, checking a database-backed sliding-window token bucket to guarantee `<= 10 POST /v1/dm/send` requests per 60 seconds across all running worker instances.
6. **PseudoGram API Execution**: `POST /v1/dm/send` returns `HTTP 202 Accepted`. Retries for 500 errors use exponential backoff (`1.5^attempts`), while 400 errors fail immediately.
7. **Delivery Reconciliation**: A background reconciliation loop polls `GET /v1/dm/{dm_id}` (without burning rate limit quota) until status updates to `delivered` or `failed`.
8. **React SaaS Dashboard**: Real-time TypeScript + Tailwind CSS interface displaying live stats, active rules, event feeds, queue statuses, rate-limit gauges, and a simulator console.

---

## Features
- **Keyword-Based DM Automation**: Case-insensitive substring keyword matching anywhere within comment text.
- **Asynchronous Webhook Processing**: Sub-300ms ACK latency meeting SLA requirements under heavy burst loads.
- **Multi-Level Idempotency**: DB-level uniqueness on `event_id` and `(rule_id, user_id)`.
- **Duplicate Event Protection**: Fast in-memory LRU cache coupled with DB transaction rollback.
- **Persistent Background Queue**: Jobs stored in PostgreSQL, fully surviving process or worker restarts.
- **Exponential Backoff Retries**: Automatic retries for transient 500 errors with backoff logic.
- **Strict Rolling Rate Limiting**: Maximum 10 `POST /v1/dm/send` calls per rolling 60s window across worker instances.
- **202 Status Reconciliation**: Async polling of `GET /v1/dm/{dm_id}` to confirm true delivery before incrementing `/stats`.
- **Webhook Signature Verification**: HMAC-SHA256 signature verification against secret.
- **Live System Statistics**: Accurate counters for `sent`, `failed`, `queued`, and `duplicates_blocked`.
- **Interactive SaaS Dashboard**: Modern dark-mode interface with live simulator, rule creation, and queue management.

---

## Tech Stack

### Backend
- **Python 3.11**: Primary runtime language.
- **FastAPI**: Modern, high-performance web framework.
- **SQLAlchemy 2.0 (AsyncIO)**: Async ORM managing database models and transactions.
- **PostgreSQL / Asyncpg / Aiosqlite**: Database storage engine with SQLite WAL mode fallback.
- **Pydantic V2**: Request validation and setting management.
- **Pytest & Pytest-Asyncio**: Async integration and stress testing framework.

### Frontend
- **React 18 & TypeScript**: Component-based UI framework with strict typing.
- **Tailwind CSS v4**: Modern CSS styling with custom glassmorphism design tokens.
- **Lucide React**: Clean SVG icon system.
- **Vite**: Ultra-fast frontend bundler.

---

## Local Setup

### 1. Prerequisites
- Python 3.10+
- Node.js 18+ & npm

### 2. Clone & Setup Repository
```bash
git clone https://github.com/pavan-545/Instagram-Auto-DM-Automation.git
cd linkplease
```

### 3. Setup Python Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt
```

### 4. Setup Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

---

## Environment Variables

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### Environment Variable Explanations:
- `DATABASE_URL`: Connection string for PostgreSQL (`postgresql+asyncpg://user:pass@localhost:5432/linkplease`) or SQLite (`sqlite+aiosqlite:///./linkplease.db`).
- `PSEUDOGRAM_BASE_URL`: Base HTTP URL for PseudoGram Host API (`https://pseudogram-api.onrender.com`).
- `PSEUDOGRAM_API_KEY`: Secret API key header used when communicating with PseudoGram.
- `WEBHOOK_SECRET`: HMAC-SHA256 secret key for validating `X-PseudoGram-Signature` headers.
- `REDIS_URL`: Optional Redis connection URL (`redis://localhost:6379/0`).
- `RATE_LIMIT_MAX_REQUESTS`: Maximum allowed POST requests to PseudoGram per window (Default: `10`).
- `RATE_LIMIT_WINDOW_SECONDS`: Rolling window duration in seconds (Default: `60`).
- `WORKER_INTERVAL_SECONDS`: Dispatch loop interval in seconds (Default: `1.0`).
- `WORKER_RECONCILE_INTERVAL_SECONDS`: Status reconciliation loop interval in seconds (Default: `2.0`).

---

## Database Setup

Initialize database tables and indexes automatically:
```bash
python -c "import asyncio; from backend.database import init_db; asyncio.run(init_db())"
```
*(Note: Database tables are also initialized automatically on application startup via FastAPI lifespan).*

---

## Running Backend

Start the FastAPI application server:
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Access API documentation at `http://localhost:8000/docs`.

---

## Running Worker

The background worker starts automatically inside the FastAPI application lifespan. To run a dedicated worker instance in a separate process:
```bash
python -c "import asyncio; from backend.worker import worker_instance; asyncio.run(worker_instance.start())"
```

---

## Running Frontend

Start the Vite development server:
```bash
cd frontend
npm run dev
```
Open `http://localhost:3000` in your web browser.

---

## Running Tests

Run the complete test suite covering reliability features and 500-event stress tests:
```bash
pytest backend/tests/test_reliability.py backend/tests/test_500_burst.py -v
```

---

## API Documentation

### 1. POST /webhook
Ingests Instagram comment events asynchronously.

- **Request Body**:
```json
{
  "event_id": "evt_123456",
  "event_type": "comment.created",
  "sent_at": "2026-08-17T10:00:00Z",
  "data": {
    "comment_id": "cmt_999",
    "text": "What is the PRICE please?",
    "from": {
      "user_id": "usr_888",
      "username": "sample_user"
    }
  }
}
```
- **Response**: `200 OK`
```json
{
  "status": "ok"
}
```

### 2. POST /rules
Creates a new automation rule with keyword and DM message.

- **Request Body**:
```json
{
  "keyword": "PRICE",
  "dm_message": "Thanks! Here is the price list: https://example.com/pricing"
}
```
- **Response**: `201 Created`
```json
{
  "rule_id": "rule_a1b2c3d4e5",
  "keyword": "PRICE",
  "dm_message": "Thanks! Here is the price list: https://example.com/pricing"
}
```

### 3. GET /stats
Returns accurate live counters reflecting system execution status.

- **Response**: `200 OK`
```json
{
  "sent": 42,
  "failed": 3,
  "queued": 5,
  "duplicates_blocked": 128
}
```

### 4. GET /health
Health check endpoint returning system operational status without exposing secrets.

- **Response**: `200 OK`
```json
{
  "status": "healthy",
  "worker_running": true,
  "timestamp": "2026-08-17T19:50:00.000Z"
}
```

---

## Reliability Design

- **`event_id` Idempotency**: Fast LRU in-memory cache plus database unique index on `webhook_events.event_id` guarantees duplicate webhooks are ignored instantly without redundant processing.
- **Rule / User Idempotency**: Database unique constraint `UniqueConstraint("rule_id", "user_id")` on table `user_rule_deliveries` ensures a user receives at most one DM for a given rule.
- **Database Transactions**: Atomic ACID transactions roll back on duplicate key conflicts, enqueuing a `blocked_duplicate` audit task.
- **Persistent Jobs**: All DM dispatch tasks are stored in table `dm_tasks`, maintaining status state across crashes or restarts.
- **Retries & 429 Handling**: Transient 500 errors trigger exponential backoff. Rate-limit 429 responses parse `Retry-After` headers and defer execution.
- **Rate Limiting**: Database-backed sliding window token bucket enforces max 10 requests / 60s across distributed worker processes.
- **202 Reconciliation**: Async polling loop checks `GET /v1/dm/{dm_id}` until status transitions to `delivered` or `failed`.
- **Worker Restart Recovery**: On startup, workers pick up uncompleted tasks (`queued`, `sending`, `sent_awaiting_reconciliation`) from DB.

---

## Deployment

The application is containerized using a multi-stage `Dockerfile` and `docker-compose.yml`.
- **Backend Service**: Served by `uvicorn` on port `8000`.
- **PostgreSQL Service**: Managed PostgreSQL 15 database on port `5432`.
- **Static Assets**: Frontend static build (`dist/`) served directly or via web proxy.
