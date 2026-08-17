import asyncio
import time
import uuid
import hmac
import hashlib
import json
import pytest
import httpx
from typing import List, Dict, Any

from fastapi.testclient import TestClient
from sqlalchemy import select, func, delete

from backend.config import settings
from backend.database import init_db, async_session_factory
from backend.models import Rule, WebhookEvent, UserRuleDelivery, DMTask, DeletedComment, RateLimitTick
from backend.main import app, recent_events_cache, reload_rules_cache
from backend.mock_api_client import MockAPIClient, MockAPIResponse
from backend.worker import BackgroundWorker
from backend.rate_limiter import DatabaseRateLimiter

# Initialize database schema before tests
@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    recent_events_cache.clear()
    async with async_session_factory() as session:
        await session.execute(delete(DMTask))
        await session.execute(delete(UserRuleDelivery))
        await session.execute(delete(WebhookEvent))
        await session.execute(delete(Rule))
        await session.execute(delete(DeletedComment))
        await session.execute(delete(RateLimitTick))
        await session.commit()
    await reload_rules_cache()
    yield

class FakeMockAPIClient(MockAPIClient):
    """
    In-memory mock of PseudoGram host API for deterministic testing.
    """
    def __init__(self):
        super().__init__(base_url="http://mock.internal", api_key="test_key")
        self.send_history: List[Dict[str, Any]] = []
        self.dm_store: Dict[str, Dict[str, Any]] = {}
        self.fail_next_sends_code: int = 0
        self.fail_retry_after: int = 2
        self.dm_counter = 0

    async def send_dm(self, recipient_user_id: str, message: str, comment_id: str, idempotency_key: str = None) -> MockAPIResponse:
        now = time.time()
        self.send_history.append({
            "timestamp": now,
            "recipient_user_id": recipient_user_id,
            "comment_id": comment_id,
            "idempotency_key": idempotency_key
        })

        if self.fail_next_sends_code == 429:
            return MockAPIResponse(429, {"error": "rate_limited"}, {"Retry-After": str(self.fail_retry_after)})
        elif self.fail_next_sends_code == 500:
            return MockAPIResponse(500, {"error": "internal_error"})
        elif self.fail_next_sends_code == 400:
            return MockAPIResponse(400, {"error": "invalid_request", "detail": "Invalid recipient"})

        self.dm_counter += 1
        dm_id = f"dm_mock_{self.dm_counter}_{uuid.uuid4().hex[:6]}"
        self.dm_store[dm_id] = {
            "dm_id": dm_id,
            "status": "queued",
            "recipient_user_id": recipient_user_id
        }
        return MockAPIResponse(202, {"dm_id": dm_id, "status": "queued"})

    async def get_dm_status(self, dm_id: str) -> MockAPIResponse:
        dm_info = self.dm_store.get(dm_id, {"status": "queued"})
        return MockAPIResponse(200, dm_info)

@pytest.mark.asyncio
async def test_webhook_ack_speed_and_duplicate_events():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        payload = {
            "event_id": "evt_duplicate_test_001",
            "event_type": "comment.created",
            "sent_at": "2026-08-17T10:00:00Z",
            "data": {
                "comment_id": "cmt_001",
                "text": "PRICE list please",
                "from": {"user_id": "usr_test1", "username": "user1"}
            }
        }

        # 1. Measure ACK latency (MUST be < 5 seconds)
        t0 = time.time()
        res1 = await client.post("/webhook", json=payload)
        latency = time.time() - t0
        
        assert res1.status_code == 200
        assert latency < 5.0, f"Webhook ACK too slow: {latency:.3f}s"

        # 2. Re-send exact same event_id
        res2 = await client.post("/webhook", json=payload)
        assert res2.status_code == 200
        assert res2.json().get("message") == "Duplicate event_id ignored"

        # Allow async background task to complete write
        await asyncio.sleep(0.1)

        # Verify only 1 webhook event recorded in DB
        async with async_session_factory() as session:
            res = await session.execute(select(func.count(WebhookEvent.id)))
            assert res.scalar() == 1

@pytest.mark.asyncio
async def test_rules_creation_and_stats():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Create rule POST /rules
        rule_payload = {"keyword": "PRICE", "dm_message": "Here is the price list!"}
        res_rule = await client.post("/rules", json=rule_payload)
        assert res_rule.status_code == 201
        data = res_rule.json()
        assert "rule_id" in data
        assert data["keyword"] == "PRICE"
        assert data["dm_message"] == "Here is the price list!"

        # Check GET /stats response structure
        res_stats = await client.get("/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert set(stats.keys()) == {"sent", "failed", "queued", "duplicates_blocked"}

@pytest.mark.asyncio
async def test_single_dm_per_user_per_rule():
    # Setup Rule
    async with async_session_factory() as session:
        rule = Rule(id="rule_p1", keyword="PRICE", dm_message="Price details")
        session.add(rule)
        await session.commit()

    await reload_rules_cache()

    fake_api = FakeMockAPIClient()
    worker = BackgroundWorker(mock_client=fake_api)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Same user user_sam comments 5 times
        for i in range(5):
            payload = {
                "event_id": f"evt_sam_{i}",
                "event_type": "comment.created",
                "data": {
                    "comment_id": f"cmt_sam_{i}",
                    "text": "What is the PRICE?",
                    "from": {"user_id": "usr_sam", "username": "sam"}
                }
            }
            res = await client.post("/webhook", json=payload)
            assert res.status_code == 200

        # Allow background tasks to execute
        await asyncio.sleep(0.1)

        # Process queued tasks
        await worker.process_pending_tasks()

        # Query tasks status
        async with async_session_factory() as session:
            tasks_res = await session.execute(select(DMTask))
            tasks = tasks_res.scalars().all()
            
            # Exactly 1 task queued/sent, 4 blocked_duplicate!
            queued_or_sent = [t for t in tasks if t.status in ("queued", "sending", "sent_awaiting_reconciliation", "delivered")]
            duplicates = [t for t in tasks if t.status == "blocked_duplicate"]

            assert len(queued_or_sent) == 1, f"Expected 1 DM task sent, found {len(queued_or_sent)}"
            assert len(duplicates) == 4, f"Expected 4 blocked duplicates, found {len(duplicates)}"

            stats_res = await client.get("/stats")
            stats = stats_res.json()
            assert stats["duplicates_blocked"] == 4

@pytest.mark.asyncio
async def test_rate_limit_compliance_10_per_60s():
    """
    Verifies that worker NEVER exceeds 10 calls to send_dm within any 60 second window.
    """
    fake_api = FakeMockAPIClient()
    worker = BackgroundWorker(mock_client=fake_api)

    # Seed 15 tasks for DIFFERENT users to avoid user-level deduplication
    async with async_session_factory() as session:
        for i in range(15):
            task = DMTask(
                event_id=f"evt_rl_{i}",
                comment_id=f"cmt_rl_{i}",
                user_id=f"usr_rl_{i}",
                rule_id="rule_rl",
                keyword="PRICE",
                dm_message="Price details",
                status="queued",
                idempotency_key=f"rule_rl:usr_rl_{i}"
            )
            session.add(task)
        await session.commit()

    # Process batch of tasks
    for _ in range(15):
        await worker.process_pending_tasks()

    # Verify send_history call timestamps
    timestamps = [item["timestamp"] for item in fake_api.send_history]
    assert len(timestamps) <= 10, f"Rate limit violated! Sent {len(timestamps)} requests, max allowed is 10."

@pytest.mark.asyncio
async def test_400_invalid_request_no_retry():
    fake_api = FakeMockAPIClient()
    fake_api.fail_next_sends_code = 400
    worker = BackgroundWorker(mock_client=fake_api)

    async with async_session_factory() as session:
        task = DMTask(
            event_id="evt_bad_400",
            comment_id="cmt_bad_400",
            user_id="usr_bad_400",
            rule_id="rule_400",
            keyword="PRICE",
            dm_message="Price",
            status="queued",
            idempotency_key="rule_400:usr_bad_400"
        )
        session.add(task)
        await session.commit()

    await worker.process_pending_tasks()

    async with async_session_factory() as session:
        res = await session.execute(select(DMTask).where(DMTask.event_id == "evt_bad_400"))
        task_after = res.scalar()
        assert task_after.status == "failed"
        assert task_after.attempts == 1  # No further retries on 400!

@pytest.mark.asyncio
async def test_202_reconciliation_to_delivered_and_failed():
    fake_api = FakeMockAPIClient()
    worker = BackgroundWorker(mock_client=fake_api)

    async with async_session_factory() as session:
        task1 = DMTask(
            event_id="evt_rec_1", comment_id="cmt_rec_1", user_id="usr_rec_1",
            rule_id="rule_rec", keyword="PRICE", dm_message="Price", status="queued",
            idempotency_key="rule_rec:usr_rec_1"
        )
        task2 = DMTask(
            event_id="evt_rec_2", comment_id="cmt_rec_2", user_id="usr_rec_2",
            rule_id="rule_rec", keyword="PRICE", dm_message="Price", status="queued",
            idempotency_key="rule_rec:usr_rec_2"
        )
        session.add_all([task1, task2])
        await session.commit()

    # Step 1: Dispatch -> both return 202 Accepted
    await worker.process_pending_tasks()

    async with async_session_factory() as session:
        tasks = (await session.execute(select(DMTask).order_by(DMTask.id.asc()))).scalars().all()
        for t in tasks:
            assert t.status == "sent_awaiting_reconciliation"
            assert t.dm_id is not None

        # Verify /stats reports these as queued, NOT sent yet!
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            stats = (await client.get("/stats")).json()
            assert stats["sent"] == 0
            assert stats["queued"] == 2

        # Step 2: Set task 1 -> delivered, task 2 -> failed in mock API
        fake_api.dm_store[tasks[0].dm_id]["status"] = "delivered"
        fake_api.dm_store[tasks[1].dm_id]["status"] = "failed"

        # Force max_attempts on task2 so it doesn't re-queue
        t2_obj = await session.get(DMTask, tasks[1].id)
        t2_obj.attempts = 5
        await session.commit()

    # Step 3: Run reconciliation loop
    await worker.reconcile_pending_dms()

    # Verify reconciliation result
    async with async_session_factory() as session:
        t1 = await session.get(DMTask, tasks[0].id)
        t2 = await session.get(DMTask, tasks[1].id)
        assert t1.status == "delivered"
        assert t2.status == "failed"

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            stats = (await client.get("/stats")).json()
            assert stats["sent"] == 1
            assert stats["failed"] == 1
            assert stats["queued"] == 0

@pytest.mark.asyncio
async def test_comment_deleted_handling():
    fake_api = FakeMockAPIClient()
    worker = BackgroundWorker(mock_client=fake_api)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Create Rule
        await client.post("/rules", json={"keyword": "DISCOUNT", "dm_message": "10% off"})

        # Send comment.created
        payload_create = {
            "event_id": "evt_del_test_1",
            "event_type": "comment.created",
            "data": {
                "comment_id": "cmt_to_delete",
                "text": "Give me a DISCOUNT",
                "from": {"user_id": "usr_del_1", "username": "del1"}
            }
        }
        await client.post("/webhook", json=payload_create)

        # Send comment.deleted BEFORE worker processes
        payload_delete = {
            "event_id": "evt_del_test_2",
            "event_type": "comment.deleted",
            "data": {
                "comment_id": "cmt_to_delete"
            }
        }
        await client.post("/webhook", json=payload_delete)

        # Allow background tasks to execute
        await asyncio.sleep(0.1)

        # Process worker loop
        await worker.process_pending_tasks()

        # Task should be cancelled and NO DM sent to Mock API
        assert len(fake_api.send_history) == 0

        async with async_session_factory() as session:
            t = (await session.execute(select(DMTask).where(DMTask.comment_id == "cmt_to_delete"))).scalar()
            assert t.status == "cancelled"

@pytest.mark.asyncio
async def test_worker_restart_recovery():
    """
    Verifies that queued tasks in DB are safely recovered and processed after a worker restart.
    """
    fake_api_1 = FakeMockAPIClient()
    worker_1 = BackgroundWorker(mock_client=fake_api_1)

    # Add task directly to DB
    async with async_session_factory() as session:
        task = DMTask(
            event_id="evt_restart_1", comment_id="cmt_restart_1", user_id="usr_restart_1",
            rule_id="rule_rst", keyword="TEST", dm_message="Restart test", status="queued",
            idempotency_key="rule_rst:usr_restart_1"
        )
        session.add(task)
        await session.commit()

    # Kill worker 1
    await worker_1.stop()

    # Create worker 2 (simulating process restart)
    fake_api_2 = FakeMockAPIClient()
    worker_2 = BackgroundWorker(mock_client=fake_api_2)

    await worker_2.process_pending_tasks()

    # Task processed successfully by worker 2
    assert len(fake_api_2.send_history) == 1
    async with async_session_factory() as session:
        t = (await session.execute(select(DMTask).where(DMTask.event_id == "evt_restart_1"))).scalar()
        assert t.status == "sent_awaiting_reconciliation"

@pytest.mark.asyncio
async def test_hmac_signature_verification():
    secret = "my_super_secret_api_key_123"
    settings.WEBHOOK_SECRET = secret

    raw_body = b'{"event_id":"evt_hmac_1","event_type":"comment.created","data":{"comment_id":"cmt_h1"}}'
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    valid_header = f"sha256={sig}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # Valid signature -> 200 OK
        res1 = await client.post("/webhook", content=raw_body, headers={"X-PseudoGram-Signature": valid_header, "Content-Type": "application/json"})
        assert res1.status_code == 200

        # Invalid signature -> 401 Unauthorized
        res2 = await client.post("/webhook", content=raw_body, headers={"X-PseudoGram-Signature": "sha256=invalidhex123", "Content-Type": "application/json"})
        assert res2.status_code == 401

    # Reset secret
    settings.WEBHOOK_SECRET = ""
