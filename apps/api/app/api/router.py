"""汇总接口。"""

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.modules import router as modules_router
from app.api.settings import router as settings_router
from app.portal.router import router as portal_router
from app.resume.router import router as resume_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["健康检查"])
api_router.include_router(settings_router, tags=["设置"])
api_router.include_router(modules_router, tags=["模块"])
api_router.include_router(portal_router, tags=["网站入口"])
api_router.include_router(resume_router, tags=["简历"])
