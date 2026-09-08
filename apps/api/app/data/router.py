"""数据模块接口：列出表，对行做增删改查。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.response import fail, ok
from app.data.tables import (
    coerce_pk,
    describe_table,
    fetch_rows,
    get_row,
    list_table_names,
    load_table,
    primary_column,
    row_dict,
    writable_values,
)
from app.db.session import get_db, get_engine

router = APIRouter()


class RowIn(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


def _table_or_fail(name: str):
    table = load_table(get_engine(), name)
    if table is None:
        return None, fail("没有这张表", 404)
    return table, None


@router.get("/data/tables")
def list_tables():
    """扫当前库里的表和列。"""

    engine = get_engine()
    items = []
    for name in list_table_names(engine):
        table = load_table(engine, name)
        if table is None:
            continue
        items.append(describe_table(table))
    return ok({"items": items})


@router.get("/data/tables/{table_name}/rows")
def list_rows(table_name: str, page: int = 1, page_size: int = 30, q: str = "", db: Session = Depends(get_db)):
    table, err = _table_or_fail(table_name)
    if err is not None:
        return err
    rows, total = fetch_rows(db, table, page=page, page_size=page_size, q=q)
    return ok(
        {
            "items": [row_dict(table, row, preview=True) for row in rows],
            "total": total,
            "page": max(1, page),
            "page_size": min(100, max(1, page_size)),
        }
    )


@router.get("/data/tables/{table_name}/rows/{row_id}")
def read_row(table_name: str, row_id: str, db: Session = Depends(get_db)):
    table, err = _table_or_fail(table_name)
    if err is not None:
        return err
    try:
        pk_value = coerce_pk(table, row_id)
    except ValueError:
        return fail("编号不对")
    row = get_row(db, table, pk_value)
    if row is None:
        return fail("这条记录不存在", 404)
    return ok(row_dict(table, row, preview=False))


@router.post("/data/tables/{table_name}/rows")
def create_row(table_name: str, body: RowIn, db: Session = Depends(get_db)):
    table, err = _table_or_fail(table_name)
    if err is not None:
        return err
    try:
        values = writable_values(table, body.values, creating=True)
        result = db.execute(insert(table).values(**values))
        db.commit()
    except (TypeError, ValueError):
        return fail("有字段格式不对")
    except IntegrityError:
        db.rollback()
        return fail("缺了必填项，或和其他记录冲突")
    pk = primary_column(table)
    new_id = result.inserted_primary_key[0] if result.inserted_primary_key else None
    if pk is None or new_id is None:
        return ok(values)
    row = get_row(db, table, new_id)
    return ok(row_dict(table, row, preview=False) if row else values)


@router.put("/data/tables/{table_name}/rows/{row_id}")
def update_row(table_name: str, row_id: str, body: RowIn, db: Session = Depends(get_db)):
    table, err = _table_or_fail(table_name)
    if err is not None:
        return err
    pk = primary_column(table)
    if pk is None:
        return fail("这张表没有主键，不能改")
    try:
        pk_value = coerce_pk(table, row_id)
        values = writable_values(table, body.values, creating=False)
    except (TypeError, ValueError):
        return fail("有字段格式不对")
    row = get_row(db, table, pk_value)
    if row is None:
        return fail("这条记录不存在", 404)
    if values:
        try:
            db.execute(update(table).where(pk == pk_value).values(**values))
            db.commit()
        except IntegrityError:
            db.rollback()
            return fail("缺了必填项，或和其他记录冲突")
    fresh = get_row(db, table, pk_value)
    return ok(row_dict(table, fresh, preview=False) if fresh else values)


@router.delete("/data/tables/{table_name}/rows/{row_id}")
def delete_row(table_name: str, row_id: str, db: Session = Depends(get_db)):
    """只删表里的行，不删磁盘文件。"""

    table, err = _table_or_fail(table_name)
    if err is not None:
        return err
    pk = primary_column(table)
    if pk is None:
        return fail("这张表没有主键，不能删")
    try:
        pk_value = coerce_pk(table, row_id)
    except ValueError:
        return fail("编号不对")
    row = get_row(db, table, pk_value)
    if row is None:
        return fail("这条记录不存在", 404)
    db.execute(delete(table).where(pk == pk_value))
    db.commit()
    return ok(True)
