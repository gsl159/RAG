"""
Re-export all route routers for easy inclusion in ``main.py``.
"""

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.documents import router as documents_router
from app.api.routes.admin import router as admin_router
from app.api.routes.feedback import router as feedback_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.tags import router as tags_router
from app.api.routes.ws import router as ws_router

__all__ = [
    "auth_router",
    "chat_router",
    "documents_router",
    "admin_router",
    "feedback_router",
    "metrics_router",
    "tags_router",
    "ws_router",
]
