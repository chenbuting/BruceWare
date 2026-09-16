"""网盘货品和订单。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.session import Base


class DriveProduct(Base):
    """一件货：对应网盘里的一个文件夹。"""

    __tablename__ = "drive_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(32), nullable=False, default="")
    title = Column(String(200), nullable=False, default="")
    price_cent = Column(Integer, nullable=False, default=0)
    path = Column(String(1000), nullable=False, default="")
    fsid = Column(Integer, nullable=False, default=0)
    period_days = Column(Integer, nullable=False, default=7)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DriveOrder(Base):
    """一笔订单：先测试付款，以后再接微信支付宝。"""

    __tablename__ = "drive_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, nullable=False, default=0)
    token = Column(String(40), nullable=False, unique=True, default="")
    status = Column(String(20), nullable=False, default="unpaid")
    pay_channel = Column(String(20), nullable=False, default="")
    share_url = Column(String(500), nullable=False, default="")
    share_pwd = Column(String(16), nullable=False, default="")
    note = Column(Text, nullable=False, default="")
    paid_at = Column(DateTime, nullable=True)
    period_days = Column(Integer, nullable=False, default=7)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
