import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TweetCreateRequest(BaseModel):
    """Request schema for creating a tweet."""
    content: str = Field(..., min_length=1, max_length=280)


class TweetResponse(BaseModel):
    """Response schema for a single tweet."""
    id: uuid.UUID
    content: str
    user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
