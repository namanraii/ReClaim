"""
FastAPI API Routes for Reclaim
"""

from .mandates import router as mandates_router
from .recovery import router as recovery_router
from .classification import router as classification_router
from .compliance import router as compliance_router
from .dashboard import router as dashboard_router

__all__ = [
    "mandates_router",
    "recovery_router",
    "classification_router",
    "compliance_router",
    "dashboard_router",
]
