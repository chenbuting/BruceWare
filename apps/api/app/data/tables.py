"""扫数据库里的表，做通用增删改查。只动记录，不动磁盘文件。"""

# 表名必须能当标识符，避免拼进 SQL

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import MetaData, Table, func, inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import Date, DateTime, Integer, Numeric

# 向量和文件路径只展示，不让改
_READONLY_NAMES = {
    "id",
    "embedding",
    "vector_stamp",
    "embedding_profile",
    "profile",
    "rel_path",
    "files_ref",
    "source_name",
}

# 系统表不列出
_SKIP_TABLES = {"sqlite_sequence", "alembic_version"}

_TABLE_LABELS = {
    "portal_links": "网站入口",
    "resume_docs": "简历",
    "resume_interviews": "模拟面试",
    "resume_interview_messages": "面试对话",
    "wardrobe_items": "衣服",
    "wardrobe_looks": "搭配",
    "wardrobe_styles": "风格",
    "kb_libraries": "知识库",
    "kb_folders": "文件夹",
    "kb_documents": "资料",
    "kb_chunks": "切片",
    "kb_assets": "抽出的图",
    "kb_sessions": "对话",
    "kb_session_turns": "问答",
}


def _safe_name(name: str) -> bool:
    return bool(name) and name.isidentifier() and not name.startswith("_")


def list_table_names(engine: Engine) -> list[str]:
    """当前库里能管的表名。"""

    names = []
    for name in inspect(engine).get_table_names():
        if name in _SKIP_TABLES or not _safe_name(name):
            continue
        names.append(name)
    return names


def load_table(engine: Engine, name: str) -> Table | None:
    """按表名反射。名字不合法或没有这张表则空。"""

    if not _safe_name(name) or name in _SKIP_TABLES:
        return None
    if name not in inspect(engine).get_table_names():
        return None
    return Table(name, MetaData(), autoload_with=engine)


def column_readonly(name: str) -> bool:
    return name.lower() in _READONLY_NAMES


def _type_name(col) -> str:
    raw = type(col.type).__name__.lower()
    if "int" in raw:
        return "integer"
    if "date" in raw:
        return "datetime"
    if "num" in raw or "float" in raw or "real" in raw:
        return "number"
    return "text"


def describe_table(table: Table) -> dict:
    """一张表的列说明，给前端画表单。"""

    pk = {col.name for col in table.primary_key.columns}
    columns = []
    for col in table.columns:
        columns.append(
            {
                "name": col.name,
                "type": _type_name(col),
                "readonly": column_readonly(col.name) or col.name in pk,
                "primary": col.name in pk,
                "nullable": bool(col.nullable),
            }
        )
    return {
        "name": table.name,
        "label": _TABLE_LABELS.get(table.name, table.name),
        "columns": columns,
    }


def _cell(value: Any, *, preview: bool) -> Any:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
    if preview and isinstance(text, str) and len(text) > 80:
        return text[:80] + "…"
    if isinstance(text, (str, int, float, bool)):
        return text
    return str(text)


def row_dict(table: Table, row, *, preview: bool) -> dict:
    data = {}
    mapping = row._mapping if hasattr(row, "_mapping") else row
    for col in table.columns:
        data[col.name] = _cell(mapping[col.name], preview=preview)
    return data


def primary_column(table: Table):
    cols = list(table.primary_key.columns)
    return cols[0] if cols else None


def coerce_pk(table: Table, raw: str):
    col = primary_column(table)
    if col is None:
        return raw
    if isinstance(col.type, Integer):
        return int(raw)
    return raw


def coerce_value(col, value: Any):
    """把前端送来的值收成列能存的类型。空串在可空列上当空。"""

    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        if isinstance(col.type, (DateTime, Date)):
            return None
        return None if col.nullable else ""
    if isinstance(col.type, Integer):
        return int(value)
    if isinstance(col.type, Numeric):
        return float(value)
    if isinstance(col.type, DateTime):
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text)
    if isinstance(col.type, Date):
        return date.fromisoformat(str(value).strip()[:10])
    return value


def writable_values(table: Table, values: dict, *, creating: bool) -> dict:
    """去掉只读列。新增时编号也去掉，让数据库自己加。"""

    cleaned = {}
    pk = {col.name for col in table.primary_key.columns}
    for col in table.columns:
        if col.name not in values:
            continue
        if column_readonly(col.name) or (creating and col.name in pk):
            continue
        cleaned[col.name] = coerce_value(col, values[col.name])
    if creating:
        for col in table.columns:
            if col.name in pk or column_readonly(col.name):
                continue
            if cleaned.get(col.name) is not None:
                continue
            time_col = col.name in {"created_at", "updated_at"} or isinstance(col.type, DateTime)
            if time_col and not col.nullable:
                cleaned[col.name] = datetime.utcnow()
    return cleaned


def search_filter(table: Table, q: str):
    """在文本列里模糊找。"""

    text = (q or "").strip()
    if not text:
        return None
    needle = f"%{text}%"
    parts = []
    for col in table.columns:
        if _type_name(col) != "text":
            continue
        parts.append(col.ilike(needle) if hasattr(col, "ilike") else col.like(needle))
    if not parts:
        return None
    return or_(*parts)


def fetch_rows(db: Session, table: Table, *, page: int, page_size: int, q: str) -> tuple[list, int]:
    """分页列出，按主键倒序。"""

    pk = primary_column(table)
    cond = search_filter(table, q)
    count_stmt = select(func.count()).select_from(table)
    stmt = select(table)
    if cond is not None:
        count_stmt = count_stmt.where(cond)
        stmt = stmt.where(cond)
    total = int(db.execute(count_stmt).scalar() or 0)
    if pk is not None:
        stmt = stmt.order_by(pk.desc())
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(stmt).all()
    return rows, total


def get_row(db: Session, table: Table, pk_value):
    pk = primary_column(table)
    if pk is None:
        return None
    return db.execute(select(table).where(pk == pk_value)).first()
