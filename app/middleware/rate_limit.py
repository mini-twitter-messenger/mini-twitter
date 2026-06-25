import logging

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import settings

logger = logging.getLogger(__name__)


def _get_key_func(request: Request) -> str:
    """Rate limit key: use authenticated user ID if available, else IP."""
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "get"):
        return user.get("sub", get_remote_address(request))
    return get_remote_address(request)


limiter = Limiter(key_func=_get_key_func)


def get_rate_limit_string() -> str:
    """Return the rate limit string based on config."""
    return f"{settings.RATE_LIMIT_PER_MINUTE}/minute"
