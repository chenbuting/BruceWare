"""网站入口接口。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.response import fail, ok
from app.db.session import get_db
from app.portal.models import PortalLink

router = APIRouter()


class LinkIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000)
    remark: str = Field(default="", max_length=500)


def _clean_url(url: str) -> str | None:
    text = url.strip()
    if not text.startswith("http://") and not text.startswith("https://"):
        return None
    return text


def _to_dict(row: PortalLink) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "url": row.url,
        "remark": row.remark or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


@router.get("/portal/links")
def list_links(db: Session = Depends(get_db)):
    rows = db.scalars(select(PortalLink).order_by(PortalLink.id.desc())).all()
    return ok({"items": [_to_dict(row) for row in rows]})


@router.post("/portal/links")
def create_link(body: LinkIn, db: Session = Depends(get_db)):
    url = _clean_url(body.url)
    if url is None:
        return fail("网址请以 http:// 或 https:// 开头")
    title = body.title.strip()
    if not title:
        return fail("请填写名称")
    row = PortalLink(title=title, url=url, remark=body.remark.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_to_dict(row))


@router.put("/portal/links/{link_id}")
def update_link(link_id: int, body: LinkIn, db: Session = Depends(get_db)):
    row = db.get(PortalLink, link_id)
    if row is None:
        return fail("这条收藏不存在", 404)
    url = _clean_url(body.url)
    if url is None:
        return fail("网址请以 http:// 或 https:// 开头")
    title = body.title.strip()
    if not title:
        return fail("请填写名称")
    row.title = title
    row.url = url
    row.remark = body.remark.strip()
    db.commit()
    db.refresh(row)
    return ok(_to_dict(row))


@router.delete("/portal/links/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    row = db.get(PortalLink, link_id)
    if row is None:
        return fail("这条收藏不存在", 404)
    db.delete(row)
    db.commit()
    return ok(True)
