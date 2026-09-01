"""网站入口：收藏的链接。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.db.session import Base


class PortalLink(Base):
    """一条网站收藏。"""

    __tablename__ = "portal_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    url = Column(String(1000), nullable=False)
    remark = Column(String(500), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
