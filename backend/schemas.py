from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class RuleCreate(BaseModel):
    keyword: str
    dm_message: str

class RuleResponse(BaseModel):
    rule_id: str
    keyword: str
    dm_message: str

class StatsResponse(BaseModel):
    sent: int
    failed: int
    queued: int
    duplicates_blocked: int

class WebhookUserData(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None

class WebhookEventData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    comment_id: str
    post_id: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None
    from_user: Optional[WebhookUserData] = Field(default=None, alias="from")

class WebhookPayload(BaseModel):
    event_id: str
    event_type: str
    sent_at: Optional[str] = None
    data: Dict[str, Any]

class DMSendRequest(BaseModel):
    recipient_user_id: str
    message: str
    comment_id: str

class DMSendResponse(BaseModel):
    dm_id: str
    status: str

class DMStatusResponse(BaseModel):
    dm_id: str
    status: str
    recipient_user_id: Optional[str] = None
    updated_at: Optional[str] = None
