"""BruceWare 后端入口。"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.core.response import ok
from app.db.session import init_database

settings = get_settings()

app = FastAPI(title=settings.app_name, docs_url="/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def on_startup():
    """启动时连接数据源并建表。"""

    init_database()


@app.get("/health")
def root_health():
    """给探活用的短地址。"""

    from app.api.health import health

    return health()


@app.get("/")
def root():
    return ok({"name": settings.app_name, "docs": "/docs"})


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception):
    """未处理异常也走统一格式。HTTP 异常交给框架。"""

    if isinstance(exc, HTTPException):
        raise exc
    return JSONResponse(
        status_code=500,
        content={"ok": False, "data": None, "message": str(exc)},
    )
