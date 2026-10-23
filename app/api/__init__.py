from app.api.auth import router as auth_router
from app.api.trades import router as trades_router
from app.api.portfolio import router as portfolio_router
from app.api.risk import router as risk_router
from app.api.ml import router as ml_router
from app.api.system import router as system_router

__all__ = [
    "auth_router",
    "trades_router",
    "portfolio_router",
    "risk_router",
    "ml_router",
    "system_router"
]
