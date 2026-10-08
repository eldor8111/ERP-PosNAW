"""E-code Mobile — kuryer va savdo agenti ilovasi API'si (/api/mobile/*)."""
from app.routers.mobile.base import router as base_router
from app.routers.mobile.cash import router as cash_router
from app.routers.mobile.courier import router as courier_router
from app.routers.mobile.agent import router as agent_router

from app.routers.mobile.marketplace_agent import router as marketplace_agent_router

routers = [base_router, cash_router, courier_router, agent_router, marketplace_agent_router]
