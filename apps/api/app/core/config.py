"""从环境变量和 .env 读取配置。"""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[2]
_REPO_ROOT = _API_DIR.parent.parent
_ENV_FILES = (
    str(_API_DIR / ".env"),
    str(_REPO_ROOT / ".env"),
)


class Settings(BaseSettings):
    """应用配置。改数据源请改 .env 后重启后端。"""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="BruceWare", description="应用名称")
    app_debug: bool = Field(default=True, description="是否开启调试")
    api_host: str = Field(default="127.0.0.1", description="后端监听地址")
    api_port: int = Field(default=8000, description="后端端口")
    api_prefix: str = Field(default="/api/v1", description="接口前缀")
    database_url: str = Field(
        default="sqlite:///./data/bruceware.db",
        description="数据库连接串，本地 SQLite 或远程 MySQL/PostgreSQL",
    )
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="允许跨域的前端地址，逗号分隔",
    )

    @property
    def repo_root(self) -> Path:
        return _REPO_ROOT

    @property
    def modules_dir(self) -> Path:
        return _REPO_ROOT / "modules"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


def resolve_database_url(raw: str, repo_root: Path) -> str:
    """相对路径的 SQLite 落到项目 data 目录，避免启动目录不同连错库。"""

    if not raw.startswith("sqlite:///"):
        return raw
    rest = raw[len("sqlite:///") :]
    path = Path(rest)
    if not path.is_absolute():
        path = (repo_root / rest).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"


def describe_database(url: str) -> dict:
    """给设置页用的数据源说明，不带密码。"""

    if url.startswith("sqlite"):
        path = url.replace("sqlite:///", "", 1)
        return {
            "mode": "local",
            "engine": "SQLite",
            "label": "本地 SQLite",
            "target": path,
        }

    parsed = urlparse(url.replace("mysql+pymysql://", "mysql://", 1).replace("postgresql+psycopg://", "postgresql://", 1))
    engine = "MySQL" if parsed.scheme.startswith("mysql") else "PostgreSQL" if parsed.scheme.startswith("postgres") else parsed.scheme
    host = parsed.hostname or ""
    port = parsed.port or ""
    name = (parsed.path or "").lstrip("/")
    target = f"{host}:{port}/{name}" if port else f"{host}/{name}"
    return {
        "mode": "remote",
        "engine": engine,
        "label": f"远程 {engine}",
        "target": target,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
