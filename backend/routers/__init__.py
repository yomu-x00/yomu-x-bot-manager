"""Router package for API endpoints (Single Responsibility Principle).

Each module handles one domain's routes, keeping main.py as a thin app factory.
"""

from .accounts import router as accounts_router
from .rules import router as rules_router
from .schedule import router as schedule_router
from .monitors import router as monitors_router
from .logs import router as logs_router
from .webhooks import router as webhooks_router
from .uploads import router as uploads_router
from .search import router as search_router

__all__ = [
    "accounts_router",
    "rules_router",
    "schedule_router",
    "monitors_router",
    "logs_router",
    "webhooks_router",
    "uploads_router",
    "search_router",
]
