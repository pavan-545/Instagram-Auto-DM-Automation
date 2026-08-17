import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Boolean, UniqueConstraint, Index
)
from backend.database import Base

class Rule(Base):
    __tablename__ = "rules"

    id = Column(String, primary_key=True, index=True)
    keyword = Column(String, index=True, nullable=False)
    dm_message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, unique=True, index=True, nullable=False)
    event_type = Column(String, index=True, nullable=False)
    comment_id = Column(String, index=True, nullable=False)
    post_id = Column(String, nullable=True)
    user_id = Column(String, nullable=True, index=True)
    username = Column(String, nullable=True)
    text = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    signature_valid = Column(Boolean, nullable=True)

class UserRuleDelivery(Base):
    __tablename__ = "user_rule_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    first_comment_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("rule_id", "user_id", name="uq_user_rule_delivery"),
    )

class DMTask(Base):
    __tablename__ = "dm_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, index=True, nullable=False)
    comment_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    rule_id = Column(String, index=True, nullable=False)
    keyword = Column(String, nullable=False)
    dm_message = Column(Text, nullable=False)
    
    # Statuses: 'queued', 'sending', 'sent_awaiting_reconciliation', 'delivered', 'failed', 'cancelled', 'blocked_duplicate'
    status = Column(String, index=True, nullable=False, default="queued")
    idempotency_key = Column(String, unique=True, index=True, nullable=False)
    dm_id = Column(String, index=True, nullable=True)
    
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)
    last_error = Column(Text, nullable=True)
    
    next_attempt_at = Column(DateTime, default=datetime.datetime.utcnow, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False)

class DeletedComment(Base):
    __tablename__ = "deleted_comments"

    comment_id = Column(String, primary_key=True, index=True)
    deleted_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

class RateLimitTick(Base):
    __tablename__ = "rate_limit_ticks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Float, index=True, nullable=False)
