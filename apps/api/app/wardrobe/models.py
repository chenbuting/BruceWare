"""衣橱：单件衣服和搭配图。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.session import Base


class WardrobeItem(Base):
    """一件衣服。"""

    __tablename__ = "wardrobe_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, default="")
    part = Column(String(40), nullable=False, default="upperbody")
    color = Column(String(20), nullable=False, default="")
    secondary_color = Column(String(20), nullable=False, default="")
    tags = Column(Text, nullable=False, default="[]")
    source_name = Column(String(300), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class WardrobeLook(Base):
    """一套搭配效果图。"""

    __tablename__ = "wardrobe_looks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, default="")
    item_ids = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
