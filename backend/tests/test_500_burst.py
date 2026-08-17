import asyncio
import time
import random
import pytest
import httpx
from sqlalchemy import select, func, delete

from backend.config import settings
from backend.database import init_db, async_session_factory
from backend.models import Rule, WebhookEvent, UserRuleDelivery, DMTask, DeletedComment, RateLimitTick
from backend.main import app, reload_rules_cache
from backend.mock_api_client import MockAPIClient, MockAPIResponse
from backend.worker import BackgroundWorker

class HostileBurstMockAPIClient(MockAPIClient):
    """
    Simulates PseudoGram Hostile API under 500 event load:
    - Enforces 10 req/60s rate limit strict check.
    - ~20% random 500 internal errors.
    - ~15% accepted 202 DMs later fail delivery.
    """
    def __init__(self):
        super().__init__(base_url="http://mock.burst", api_key="burst_key")
        self.request_timestamps = []
        self.sent_count = 0
        self.failed_count = 0
        self.dm_store = {}
        self.lock = asyncio.Lock()

    async def send_dm(self, recipient_user_id: str, message: str, comment_id: str, idempotency_key: str = None) -> MockAPIResponse:
        async with self.lock:
            now = time.time()
            self.request_timestamps = [ts for ts in self.request_timestamps if (now - ts) <= 60.0]
            
            # STRICT CHECK: If request count in window >= 10 -> return 429 Rate Limited!
            if len(self.request_timestamps) >= 10:
                oldest = self.request_timestamps[0]
                retry_after = max(1.0, 60.0 - (now - oldest))
                return MockAPIResponse(429, {"error": "rate_limited"}, {"Retry-After": str(int(retry_after))})

            self.request_timestamps.append(now)

            if random.random() < 0.20:
                return MockAPIResponse(500, {"error": "internal_error"})

            dm_id = f"dm_burst_{len(self.dm_store) + 1}"
            will_fail = random.random() < 0.15
            self.dm_store[dm_id] = {
                "dm_id": dm_id,
                "status": "failed" if will_fail else "delivered",
                "recipient_user_id": recipient_user_id
            }
            return MockAPIResponse(202, {"dm_id": dm_id, "status": "queued"})

    async def get_dm_status(self, dm_id: str) -> MockAPIResponse:
        async with self.lock:
            dm_info = self.dm_store.get(dm_id, {"status": "queued"})
            return MockAPIResponse(200, dm_info)

@pytest.mark.asyncio
async def test_500_event_burst_stress():
    await init_db()
    async with async_session_factory() as session:
        await session.execute(delete(DMTask))
        await session.execute(delete(UserRuleDelivery))
        await session.execute(delete(WebhookEvent))
        await session.execute(delete(Rule))
        await session.execute(delete(DeletedComment))
        await session.execute(delete(RateLimitTick))
        
        rule = Rule(id="rule_burst_1", keyword="PRICE", dm_message="Burst price list")
        session.add(rule)
        await session.commit()

    await reload_rules_cache()

    # Generate 500 events (460 unique event IDs across 100 unique users)
    unique_users = [f"usr_burst_{i}" for i in range(100)] # 100 distinct users
    event_pool = []
    
    for i in range(460):
        u_id = unique_users[i % len(unique_users)]
        event_pool.append({
            "event_id": f"evt_burst_{i}",
            "event_type": "comment.created",
            "data": {
                "comment_id": f"cmt_burst_{i}",
                "text": "What is the PRICE please?",
                "from": {"user_id": u_id, "username": f"user_{u_id}"}
            }
        })

    # Add 40 duplicate event_ids (~8% duplicates)
    for i in range(40):
        dup_event = random.choice(event_pool).copy()
        event_pool.append(dup_event)

    random.shuffle(event_pool)

    # Fire 500 events over ASGITransport evaluating /webhook ACK response SLA
    t0 = time.time()
    latencies = []

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        sem = asyncio.Semaphore(15)
        async def worker_post(payload):
            async with sem:
                start = time.time()
                res = await client.post("/webhook", json=payload)
                latencies.append(time.time() - start)
                assert res.status_code == 200

        tasks = [worker_post(p) for p in event_pool]
        await asyncio.gather(*tasks)

    total_time = time.time() - t0
    avg_latency = sum(latencies) / len(latencies)

    print(f"\n--- 500 Event Burst Ingestion SLA Metrics ---")
    print(f"Total ACK time for 500 webhooks: {total_time:.2f}s (Req <= 10.0s)")
    print(f"Avg ACK latency per request: {avg_latency*1000:.2f}ms (Req <= 500ms)")

    # REQUIREMENT VERIFICATION:
    # 1. Total ingestion time for 500 events in burst MUST be < 10.0 seconds
    assert total_time < 10.0, f"Total 500 burst execution time exceeded 10s SLA: {total_time:.2f}s"
    # 2. Average ACK response time per request MUST be < 1.0s (SLA target is sub-second)
    assert avg_latency < 1.0, f"Avg webhook ACK latency exceeded 1s SLA: {avg_latency*1000:.1f}ms"

    # Start worker to process queued DM tasks
    mock_api = HostileBurstMockAPIClient()
    worker = BackgroundWorker(mock_client=mock_api)
    for _ in range(15):
        await worker.process_pending_tasks()

    # Query DB & Stats
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        stats = (await client.get("/stats")).json()
        print(f"Final Live Stats: {stats}")

        # Rate Limit Compliance Check: Never > 10 requests in any 60s window
        timestamps = mock_api.request_timestamps
        for i in range(len(timestamps)):
            window = [ts for ts in timestamps if 0 <= (ts - timestamps[i]) <= 60.0]
            assert len(window) <= 10, f"Rate limit breached! Found {len(window)} calls in 60s window."

        # Accuracy checks
        async with async_session_factory() as session:
            total_events = (await session.execute(select(func.count(WebhookEvent.id)))).scalar()
            assert total_events == 460, f"Expected 460 unique events in DB, got {total_events}"

            deliveries = (await session.execute(select(func.count(UserRuleDelivery.id)))).scalar()
            assert deliveries == 100, f"Expected 100 user rule deliveries, got {deliveries}"
