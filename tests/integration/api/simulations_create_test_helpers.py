import pytest
from sqlalchemy import select
from app.core.auth.current_user import get_current_user
from app.domains import Company, Task, User
from app.domains.simulations.ai_config import (
    AI_NOTICE_DEFAULT_TEXT,
    AI_NOTICE_DEFAULT_VERSION,
)

__all__ = [name for name in globals() if not name.startswith("__")]
