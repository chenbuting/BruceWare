"""健康检查。"""

from fastapi import APIRouter

from app.core.config import describe_database, get_settings
from app.core.response import ok
from app.db.session import get_database_url, ping_database

router = APIRouter()


@router.get("/health")
def health():
    """后端是否活着、数据库是否通。"""

    connected, error = ping_database()
    db = describe_database(get_database_url())
    return ok(
        {
            "app": get_settings().app_name,
            "database": {
                **db,
                "connected": connected,
                "error": error,
            },
        }
    )
