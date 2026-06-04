import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, SmallInteger
from backend.database import Base


class Customer(Base):
    """
    Synced from: GET /otapis/cronjob/ai-order/fetch-customers
    Identified in calls by business_name.
    allow_products stores a JSON-encoded list of permitted product IDs, e.g. "[1,2,3]".
    """
    __tablename__ = "customers"

    customer_id   = Column(Integer, primary_key=True, index=True)
    business_name = Column(String(300), index=True, default="")
    email         = Column(String(300), default="")
    phone         = Column(String(50), default="", nullable=True)
    allow_products = Column(Text, default="[]")   # JSON list: "[1, 2, 3]"
    synced_at     = Column(DateTime, default=datetime.datetime.utcnow)


class Product(Base):
    """
    Synced from: GET /otapis/cronjob/ai-order/fetch-products
    Searched locally; orders are forwarded to the external create-order API.
    """
    __tablename__ = "products"

    id            = Column(Integer, primary_key=True, index=True)
    product_code  = Column(String(200), default="")
    name          = Column(String(300), index=True, default="")
    desc          = Column(Text, default="")
    image         = Column(String(500), nullable=True)
    cat_id        = Column(String(50), default="")
    base_unit_id  = Column(Integer, default=0)
    order_unit_id = Column(String(50), default="")
    min_order_qut      = Column(String(50), default="1")
    max_order_qut      = Column(String(50), default="")
    allow_decimal_qty  = Column(SmallInteger, default=1)
    base_unit          = Column(String(100), default="")
    order_unit         = Column(String(100), default="")
    category           = Column(String(200), default="")
    synced_at          = Column(DateTime, default=datetime.datetime.utcnow)
