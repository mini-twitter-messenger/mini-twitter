import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TimelineTweet(BaseModel):
    """Schema for a tweet in a timeline response."""
    id: str
    content: str
    user_id: str
    username: str = ""
    created_at: str


class TimelineResponse(BaseModel):
    """Paginated timeline response."""
    tweets: list[TimelineTweet]
    limit: int
    offset: int
