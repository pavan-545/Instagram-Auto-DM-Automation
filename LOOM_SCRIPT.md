# LinkPlease - 3-Minute Loom Demo & Walkthrough Script

---

## 🎬 Video Overview & Guidelines
- **Duration**: ~3 Minutes (180 Seconds)
- **Format**: Screen Recording (Browser SaaS Dashboard + Codebase in Editor)
- **Tone**: Conversational, Technical, and Production-Oriented

---

## 🎙️ Timestamped Script

### [0:00 - 0:35] Part 1: Project & Architecture Overview
> *"Hi everyone! Today I’m presenting **LinkPlease**, an enterprise-grade Instagram Direct Message automation engine built with **FastAPI**, **PostgreSQL**, and a **React TypeScript** SaaS dashboard.*
>
> *When creators post content on Instagram, followers comment keywords like 'PRICE' or 'LINK'. LinkPlease ingests these webhook comment events asynchronously, evaluates automation rules, and automatically sends direct messages to those users via the PseudoGram host API while maintaining strict reliability guarantees.*
>
> *Architecturally, the application uses FastAPI for sub-300ms webhook ACKs, PostgreSQL for multi-layered idempotency and queue persistence, a sliding-window rate limiter enforcing a strict limit of 10 requests per 60 seconds, and a background worker loop that handles status reconciliation for 202 Accepted responses."*

---

### [0:35 - 1:40] Part 2: Live SaaS Dashboard Demo
> *(Switch screen to live React SaaS Dashboard at `http://localhost:3000`)*
>
> *"Here is the LinkPlease SaaS Dashboard. Notice our live counters for Delivered DMs, Pending Queue, Duplicates Blocked, and Failed DMs, alongside our live rate limit gauge.*
>
> *Let's navigate to **Automation Rules**. I’ll create a rule for the keyword `PRICE` with the message `'Thanks! Here is the price list: https://example.com/pricing'`.*
>
> *Now let's switch to the **Test Console** to trigger a synthetic webhook event for user `usr_sam` commenting `'Can I get the PRICE please?'`.*
>
> *As soon as I hit 'Post Webhook', `/webhook` responds HTTP 200 within 2 milliseconds! In the background, the task is persistent in PostgreSQL. The background worker picks up the job, checks the 10/60s rate limiter, dispatches `POST /v1/dm/send`, receives a `202 Accepted` response, and polls `GET /v1/dm/{dm_id}` until delivery is confirmed as `delivered`!*
>
> *If `usr_sam` comments 5 more times with `'PRICE'`, our DB-level unique constraint `(rule_id, user_id)` suppresses duplicate DMs and increments `duplicates_blocked` to 4, guaranteeing a user never receives spam DMs."*

---

### [1:40 - 2:25] Part 3: Engineering Tradeoffs & Reliability Deep-Dive
> *(Switch screen to Code Editor showing `backend/models.py` and `backend/rate_limiter.py`)*
>
> *"Let's talk about key engineering tradeoffs. One critical choice was balancing **low-latency webhook acknowledgments** against **database transaction safety** under 500-event burst traffic.*
>
> *Instead of processing rules synchronously inside the HTTP request loop, `/webhook` checks a sub-millisecond in-memory LRU cache and delegates event persistence to non-blocking background routines. Idempotency is enforced at the database layer via PostgreSQL `UNIQUE` indexes on `event_id` and `(rule_id, user_id)`.*
>
> *For rate limiting, we built a database-backed sliding-window token bucket using a `rate_limit_ticks` table. This ensures that even if multiple worker containers scale horizontally, the 10 request / 60 second rate limit is strictly enforced across all processes."*

---

### [2:25 - 3:00] Part 4: Future Improvements & Wrap-Up
> *"If I had one more week to expand LinkPlease, I would implement two key enhancements:*
> 1. *Transition our job queue from database polling to a dedicated **Redis/BullMQ cluster** with PgBouncer connection pooling to support millions of events per hour.*
> 2. *Implement **multi-API-key rotation** to scale throughput beyond 10 DMs/minute by balancing across multiple PseudoGram developer accounts.*
>
> *All 10 reliability and stress tests pass cleanly, and the production Docker configuration is fully prepared. Thank you for watching!"*
