# LinkPlease - Failure Modes & System Limitations (FAILURES.md)

This document honestly and specifically analyzes four realistic operational failure modes and technical limitations of the **LinkPlease** engine.

---

## Failure Mode 1: High Burst Queue Processing Latency Under Hostile Rate Limits

### Condition
A sudden burst of webhooks arrives (e.g., 500 comment events matching rules within 10 seconds), while PseudoGram enforces a strict rate limit of 10 requests per rolling 60 seconds.

### What Happens
All 500 webhooks acknowledge HTTP 200 within sub-300ms, and 100 unique DM tasks are queued safely in the database. However, the last queued DM task will take **~10 minutes** to complete delivery.

### Why It Happens
PseudoGram enforces a strict sliding-window rate limit of 10 requests per rolling 60 seconds. LinkPlease's `DatabaseRateLimiter` strictly respects this limit to prevent 429 rate limit errors. Consequently, throughput is mathematically capped at 10 DMs/minute (600 DMs/hour).

### How It Could Be Improved
1. **Multi-Key API Rotation**: Implement support for multiple PseudoGram API keys or OAuth access tokens to distribute rate limit quotas across multiple accounts.
2. **Priority Queueing**: Prioritize high-value users or recent comments over older queue items.

---

## Failure Mode 2: Out-of-Order Delivery Status Reconciliation Polling Lag

### Condition
A DM task is successfully accepted by `POST /v1/dm/send`, returning `HTTP 202 Accepted` with status `queued`. PseudoGram delivers the message 50ms later.

### What Happens
`GET /stats` continues to report the message in the `queued` count for up to 2 seconds before updating to `sent`.

### Why It Happens
`POST /v1/dm/send` only acknowledges queueing on PseudoGram, not delivery. To avoid consuming rate limit quota, LinkPlease relies on an asynchronous polling loop (`reconcile_pending_dms`) that queries `GET /v1/dm/{dm_id}` every 2.0 seconds.

### How It Could Be Improved
1. **Webhook Delivery Callbacks**: If PseudoGram supports outbound delivery webhooks (e.g., `dm.delivered` or `dm.failed`), LinkPlease could subscribe to delivery callbacks for instantaneous real-time reconciliation.
2. **Adaptive Polling Intervals**: Increase polling frequency for recently submitted DM tasks while backing off for older tasks.

---

## Failure Mode 3: Post-Dispatch Comment Deletion Race Condition

### Condition
A user posts a comment matching a rule. LinkPlease dispatches `POST /v1/dm/send` to PseudoGram, receiving `HTTP 202 Accepted`. 100ms later, the user deletes their comment, triggering a `comment.deleted` webhook.

### What Happens
LinkPlease receives `comment.deleted` and updates the matching `DMTask` record in the database. However, PseudoGram still delivers the DM to the user.

### Why It Happens
Once `POST /v1/dm/send` returns HTTP 202 Accepted, PseudoGram has already accepted responsibility for sending the DM. The PseudoGram API does not provide a `DELETE /v1/dm/{dm_id}` endpoint to recall or cancel an already-accepted DM.

### How It Could Be Improved
1. **Pre-Dispatch Verification**: Perform an optional lightweight check or short staging delay right before dispatching if real-time comment status API is available.
2. **API Cancellation Endpoint**: Introduce a `DELETE /v1/dm/{dm_id}` cancellation request in the upstream PseudoGram API specification.

---

## Failure Mode 4: Database Connection Pool Exhaustion Under Concurrent Multi-Worker Spikes

### Condition
Multiple worker instances (e.g., 20 parallel worker processes) attempt to query pending tasks simultaneously from PostgreSQL under heavy load.

### What Happens
Some worker processes encounter `asyncpg.exceptions.TooManyConnectionsError` or SQLite database lock contention, causing worker loop retries.

### Why It Happens
Each worker instance maintains its own database connection pool. Under high worker process scaling without a centralized connection pooler, total open connections exceed PostgreSQL's `max_connections` limit.

### How It Could Be Improved
1. **PgBouncer Connection Pooling**: Deploy PgBouncer in front of PostgreSQL to pool and manage database connections across worker processes.
2. **Centralized Redis Job Queue**: Transition background job queueing from database table polling to a dedicated Redis queue (e.g., BullMQ or Celery/Redis).
