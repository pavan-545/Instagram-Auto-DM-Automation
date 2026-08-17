import uuid
import datetime
import logging
import asyncio
from typing import List, Optional, Set, Dict, Any
from collections import OrderedDict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, status, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, delete, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import init_db, get_db, async_session_factory
from backend.models import Rule, WebhookEvent, UserRuleDelivery, DMTask, DeletedComment, RateLimitTick
from backend.schemas import RuleCreate, RuleResponse, StatsResponse, WebhookPayload
from backend.security import verify_signature
from backend.worker import worker_instance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("linkplease.main")

class RecentEventCache:
    def __init__(self, capacity: int = 50000):
        self.capacity = capacity
        self.cache: OrderedDict = OrderedDict()

    def contains(self, key: str) -> bool:
        return key in self.cache

    def add(self, key: str):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            self.cache[key] = True
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def clear(self):
        self.cache.clear()

recent_events_cache = RecentEventCache()

# In-memory Rules Cache to eliminate redundant DB reads under load
active_rules_cache: List[Dict[str, str]] = []

async def reload_rules_cache():
    global active_rules_cache
    async with async_session_factory() as session:
        res = await session.execute(select(Rule))
        rules = res.scalars().all()
        active_rules_cache = [
            {"id": r.id, "keyword": r.keyword, "dm_message": r.dm_message}
            for r in rules
        ]

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schemas
    await init_db()
    await reload_rules_cache()
    # Start background worker
    await worker_instance.start()
    yield
    # Stop background worker
    await worker_instance.stop()

app = FastAPI(title="LinkPlease API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Required Part A / Part B / Part C Endpoints
# ---------------------------------------------------------

@app.post("/webhook", status_code=200)
async def handle_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_pseudogram_signature: Optional[str] = Header(None, alias="X-PseudoGram-Signature")
):
    raw_body = await request.body()
    
    # 1. Signature verification
    if settings.WEBHOOK_SECRET and x_pseudogram_signature:
        if not verify_signature(raw_body, x_pseudogram_signature, settings.WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        body_json = await request.json()
        payload = WebhookPayload(**body_json)
    except Exception as e:
        logger.error(f"Invalid webhook JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_id = payload.event_id
    event_type = payload.event_type
    data = payload.data
    comment_id = data.get("comment_id", "")

    # Fast in-memory duplicate filter check (<0.01ms)
    if recent_events_cache.contains(event_id):
        return {"status": "ok", "message": "Duplicate event_id ignored"}
    
    recent_events_cache.add(event_id)

    # Parse sent_at if provided
    sent_at_dt = None
    if payload.sent_at:
        try:
            sent_at_dt = datetime.datetime.fromisoformat(payload.sent_at.replace("Z", "+00:00"))
        except Exception:
            pass

    user_info = data.get("from", {}) or {}
    user_id = user_info.get("user_id")
    username = user_info.get("username")
    text = data.get("text", "")
    post_id = data.get("post_id")

    # 2. Schedule non-blocking async background processing
    background_tasks.add_task(
        process_webhook_event,
        event_id=event_id,
        event_type=event_type,
        comment_id=comment_id,
        post_id=post_id,
        user_id=user_id,
        username=username,
        text=text,
        sent_at_dt=sent_at_dt
    )

    return {"status": "ok"}

async def process_webhook_event(
    event_id: str,
    event_type: str,
    comment_id: str,
    post_id: Optional[str],
    user_id: Optional[str],
    username: Optional[str],
    text: str,
    sent_at_dt: Optional[datetime.datetime]
):
    """
    Asynchronous background processor for webhook events.
    Enforces DB unique event_id constraint, rules matching, per-user delivery limits, and comment deletions.
    """
    async with async_session_factory() as session:
        # Idempotent Event Ingestion in DB
        event_record = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            comment_id=comment_id,
            post_id=post_id,
            user_id=user_id,
            username=username,
            text=text,
            sent_at=sent_at_dt,
            signature_valid=True
        )
        try:
            session.add(event_record)
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return  # Duplicate event in DB

        if event_type == "comment.deleted":
            # Record comment deletion
            del_comment = DeletedComment(comment_id=comment_id)
            try:
                session.add(del_comment)
                await session.commit()
            except IntegrityError:
                await session.rollback()

            # Cancel any pending/sending DM tasks for this comment
            cancel_stmt = (
                select(DMTask)
                .where(
                    DMTask.comment_id == comment_id,
                    DMTask.status.in_(["queued", "sending", "sent_awaiting_reconciliation"])
                )
            )
            res = await session.execute(cancel_stmt)
            for task in res.scalars().all():
                task.status = "cancelled"
                task.last_error = "Comment deleted by author"
            await session.commit()
            return

        if event_type == "comment.created":
            if not user_id or not text:
                return

            # Check if comment was already deleted out-of-order
            del_check = await session.execute(select(DeletedComment).where(DeletedComment.comment_id == comment_id))
            if del_check.scalar():
                return

            comment_text_lower = text.lower()

            # Fast match against in-memory active_rules_cache
            for rule in active_rules_cache:
                rule_id = rule["id"]
                rule_keyword = rule["keyword"]
                rule_dm_message = rule["dm_message"]

                keyword_lower = rule_keyword.lower()
                # Case-insensitive keyword substring match anywhere in comment text
                if keyword_lower in comment_text_lower:
                    # Enforce strict 1 DM per user per rule via DB unique constraint
                    delivery = UserRuleDelivery(
                        rule_id=rule_id,
                        user_id=user_id,
                        first_comment_id=comment_id
                    )
                    try:
                        session.add(delivery)
                        await session.commit()
                        
                        # First time user matched this rule -> Enqueue DM Task
                        idempotency_key = f"{rule_id}:{user_id}"
                        task = DMTask(
                            event_id=event_id,
                            comment_id=comment_id,
                            user_id=user_id,
                            rule_id=rule_id,
                            keyword=rule_keyword,
                            dm_message=rule_dm_message,
                            status="queued",
                            idempotency_key=idempotency_key
                        )
                        session.add(task)
                        await session.commit()

                    except IntegrityError:
                        # User has ALREADY received a DM for this rule!
                        await session.rollback()
                        dup_key = f"blocked_dup_{event_id}_{rule_id}_{user_id}"
                        dup_task = DMTask(
                            event_id=event_id,
                            comment_id=comment_id,
                            user_id=user_id,
                            rule_id=rule_id,
                            keyword=rule_keyword,
                            dm_message=rule_dm_message,
                            status="blocked_duplicate",
                            idempotency_key=dup_key,
                            last_error="User already received DM for this rule"
                        )
                        try:
                            session.add(dup_task)
                            await session.commit()
                        except IntegrityError:
                            await session.rollback()

@app.post("/rules", status_code=201, response_model=RuleResponse)
async def create_rule(rule_in: RuleCreate, db: AsyncSession = Depends(get_db)):
    rule_id = f"rule_{uuid.uuid4().hex[:10]}"
    rule = Rule(
        id=rule_id,
        keyword=rule_in.keyword,
        dm_message=rule_in.dm_message
    )
    db.add(rule)
    await db.commit()
    await reload_rules_cache()
    return RuleResponse(
        rule_id=rule.id,
        keyword=rule.keyword,
        dm_message=rule.dm_message
    )

@app.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Returns accurate live counters:
      - sent: DMs confirmed delivered by Mock API
      - failed: permanently failed after retries
      - queued: waiting to send, sending, or awaiting delivery reconciliation
      - duplicates_blocked: DMs correctly suppressed (user already DMed for rule)
    """
    stmt = select(DMTask.status, func.count(DMTask.id)).group_by(DMTask.status)
    res = await db.execute(stmt)
    counts = dict(res.all())

    sent = counts.get("delivered", 0)
    failed = counts.get("failed", 0)
    queued = (
        counts.get("queued", 0) + 
        counts.get("sending", 0) + 
        counts.get("sent_awaiting_reconciliation", 0)
    )
    duplicates_blocked = counts.get("blocked_duplicate", 0)

    return StatsResponse(
        sent=sent,
        failed=failed,
        queued=queued,
        duplicates_blocked=duplicates_blocked
    )

# ---------------------------------------------------------
# SaaS Dashboard Helper APIs
# ---------------------------------------------------------

@app.get("/api/rules", response_model=List[RuleResponse])
async def list_rules(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(Rule).order_by(Rule.created_at.desc()))
    rules = res.scalars().all()
    return [RuleResponse(rule_id=r.id, keyword=r.keyword, dm_message=r.dm_message) for r in rules]

@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    rule = await db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    await reload_rules_cache()
    return {"status": "success", "message": f"Rule {rule_id} deleted"}

@app.get("/api/events")
async def list_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WebhookEvent).order_by(WebhookEvent.id.desc()).limit(limit))
    events = res.scalars().all()
    return [
        {
            "id": e.id,
            "event_id": e.event_id,
            "event_type": e.event_type,
            "comment_id": e.comment_id,
            "user_id": e.user_id,
            "username": e.username,
            "text": e.text,
            "received_at": e.received_at.isoformat() if e.received_at else None
        }
        for e in events
    ]

@app.get("/api/tasks")
async def list_tasks(limit: int = 50, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(DMTask).order_by(DMTask.id.desc()).limit(limit))
    tasks = res.scalars().all()
    return [
        {
            "id": t.id,
            "event_id": t.event_id,
            "comment_id": t.comment_id,
            "user_id": t.user_id,
            "rule_id": t.rule_id,
            "keyword": t.keyword,
            "status": t.status,
            "attempts": t.attempts,
            "dm_id": t.dm_id,
            "last_error": t.last_error,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None
        }
        for t in tasks
    ]

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    return {
        "status": "healthy",
        "worker_running": worker_instance.is_running,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

@app.get("/api/health")
async def system_health(db: AsyncSession = Depends(get_db)):
    now = datetime.datetime.utcnow()
    
    # Active rate limit ticks in last 60 seconds
    ticks_res = await db.execute(
        select(func.count(RateLimitTick.id)).where(RateLimitTick.timestamp >= (datetime.datetime.utcnow().timestamp() - 60.0))
    )
    rate_limit_count = ticks_res.scalar() or 0

    # Total events count
    events_count = (await db.execute(select(func.count(WebhookEvent.id)))).scalar() or 0
    tasks_count = (await db.execute(select(func.count(DMTask.id)))).scalar() or 0

    return {
        "status": "healthy",
        "worker_running": worker_instance.is_running,
        "rate_limit_usage": f"{rate_limit_count}/{settings.RATE_LIMIT_MAX_REQUESTS} req/60s",
        "total_webhook_events": events_count,
        "total_dm_tasks": tasks_count,
        "timestamp": now.isoformat()
    }

