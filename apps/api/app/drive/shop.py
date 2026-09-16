"""网盘货品：指定文件夹，测试付款后生成百度分享链接。"""

from __future__ import annotations

import re
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import fail, ok
from app.db.session import get_db
from app.drive.adapters import get_adapter
from app.drive.models import DriveOrder, DriveProduct
from app.drive.store import get_raw, public_account, save_raw

router = APIRouter()


class ProductIn(BaseModel):
    account_id: str = ""
    title: str = Field(default="", max_length=200)
    price: str = Field(default="1", max_length=20)
    path: str = ""
    fsid: int = 0
    period_days: int = 7


def _yuan(cent: int) -> str:
    return f"{max(cent, 0) / 100:.2f}"


def _cent(raw: str) -> int | None:
    text = (raw or "").strip().replace("￥", "").replace(",", "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?", text):
        return None
    yuan, _, fen = text.partition(".")
    return int(yuan) * 100 + int((fen + "00")[:2])


def _product_dict(row: DriveProduct, account_name: str = "") -> dict:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "account_name": account_name,
        "title": row.title,
        "price": _yuan(row.price_cent),
        "price_cent": row.price_cent,
        "path": row.path,
        "fsid": row.fsid,
        "period_days": row.period_days,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _order_dict(row: DriveOrder, product: DriveProduct | None = None) -> dict:
    title = product.title if product is not None else ""
    price = _yuan(product.price_cent) if product is not None else "0.00"
    return {
        "id": row.id,
        "product_id": row.product_id,
        "title": title,
        "price": price,
        "token": row.token,
        "status": row.status,
        "pay_channel": row.pay_channel,
        "share_url": row.share_url if row.status == "paid" else "",
        "share_pwd": row.share_pwd if row.status == "paid" else "",
        "buyer_path": f"/buy/{row.token}",
        "paid_at": row.paid_at.isoformat() if row.paid_at else "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


def _account_name(account_id: str) -> str:
    row = get_raw(account_id)
    if row is None:
        return ""
    return str(public_account(row).get("name") or "")


def _save_tokens(row: dict) -> None:
    save_raw(row)


def _deliver(order: DriveOrder, product: DriveProduct) -> None:
    """付款成功后向百度要分享链接。"""

    if order.share_url:
        return
    account = get_raw(product.account_id)
    if account is None:
        raise ValueError("货品对应的网盘账号不在了")
    adapter = get_adapter(str(account.get("kind") or ""))
    if not hasattr(adapter, "share"):
        raise ValueError("这种网盘还不能生成分享链接")
    share = adapter.share(account, product.fsid, product.period_days)
    _save_tokens(account)
    order.share_url = str(share.get("link") or "")
    order.share_pwd = str(share.get("pwd") or "")
    if not order.share_url:
        raise ValueError("百度没返回分享链接")


@router.get("/drive/products")
def list_products(db: Session = Depends(get_db)):
    rows = db.scalars(select(DriveProduct).order_by(DriveProduct.id.desc())).all()
    return ok({"items": [_product_dict(item, _account_name(item.account_id)) for item in rows]})


@router.post("/drive/products")
def create_product(body: ProductIn, db: Session = Depends(get_db)):
    account = get_raw(body.account_id)
    if account is None:
        return fail("请先选网盘账号")
    if not body.fsid:
        return fail("请选一个文件夹")
    title = body.title.strip() or body.path.rsplit("/", 1)[-1] or "未命名"
    cent = _cent(body.price)
    if cent is None:
        return fail("价格请写成数字，比如 9.9")
    exists = db.scalars(
        select(DriveProduct).where(DriveProduct.account_id == body.account_id, DriveProduct.path == body.path)
    ).first()
    if exists is not None:
        return fail("这个文件夹已经是货品了")
    row = DriveProduct(
        account_id=body.account_id,
        title=title[:200],
        price_cent=cent,
        path=body.path,
        fsid=int(body.fsid),
        period_days=7 if body.period_days not in {1, 7, 30} else body.period_days,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_product_dict(row, _account_name(row.account_id)))


@router.put("/drive/products/{product_id}")
def update_product(product_id: int, body: ProductIn, db: Session = Depends(get_db)):
    row = db.get(DriveProduct, product_id)
    if row is None:
        return fail("这个货品不存在", 404)
    title = body.title.strip()
    if title:
        row.title = title[:200]
    if body.price.strip():
        cent = _cent(body.price)
        if cent is None:
            return fail("价格请写成数字，比如 9.9")
        row.price_cent = cent
    if body.period_days in {1, 7, 30}:
        row.period_days = body.period_days
    db.commit()
    db.refresh(row)
    return ok(_product_dict(row, _account_name(row.account_id)))


@router.delete("/drive/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    row = db.get(DriveProduct, product_id)
    if row is None:
        return fail("这个货品不存在", 404)
    for order in db.scalars(select(DriveOrder).where(DriveOrder.product_id == product_id)).all():
        db.delete(order)
    db.delete(row)
    db.commit()
    return ok(True)


@router.get("/drive/orders")
def list_orders(db: Session = Depends(get_db)):
    rows = db.scalars(select(DriveOrder).order_by(DriveOrder.id.desc())).all()
    products = {item.id: item for item in db.scalars(select(DriveProduct)).all()}
    return ok({"items": [_order_dict(item, products.get(item.product_id)) for item in rows]})


@router.post("/drive/products/{product_id}/orders")
def create_order(product_id: int, db: Session = Depends(get_db)):
    product = db.get(DriveProduct, product_id)
    if product is None:
        return fail("这个货品不存在", 404)
    row = DriveOrder(product_id=product.id, token=secrets.token_urlsafe(12), status="unpaid")
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_order_dict(row, product))


@router.post("/drive/orders/{order_id}/test-pay")
def test_pay_order(order_id: int, db: Session = Depends(get_db)):
    """本机测试：假装已经收到钱，然后生成分享链接。"""

    order = db.get(DriveOrder, order_id)
    if order is None:
        return fail("这笔订单不存在", 404)
    product = db.get(DriveProduct, order.product_id)
    if product is None:
        return fail("货品不在了")
    try:
        _deliver(order, product)
    except ValueError as exc:
        return fail(str(exc))
    order.status = "paid"
    order.pay_channel = "test"
    order.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return ok(_order_dict(order, product))


@router.get("/drive/buy/{token}")
def buy_page(token: str, db: Session = Depends(get_db)):
    order = db.scalars(select(DriveOrder).where(DriveOrder.token == token)).first()
    if order is None:
        return fail("这个链接无效", 404)
    product = db.get(DriveProduct, order.product_id)
    if product is None:
        return fail("货品不在了", 404)
    return ok(_order_dict(order, product))


@router.post("/drive/buy/{token}/test-pay")
def buy_test_pay(token: str, db: Session = Depends(get_db)):
    order = db.scalars(select(DriveOrder).where(DriveOrder.token == token)).first()
    if order is None:
        return fail("这个链接无效", 404)
    product = db.get(DriveProduct, order.product_id)
    if product is None:
        return fail("货品不在了")
    if order.status == "paid" and order.share_url:
        return ok(_order_dict(order, product))
    try:
        _deliver(order, product)
    except ValueError as exc:
        return fail(str(exc))
    order.status = "paid"
    order.pay_channel = "test"
    order.paid_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return ok(_order_dict(order, product))
