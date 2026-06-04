"""
sync.py — Pulls fresh customer and product data from the Miinex external APIs
and upserts them into the local SQLite database.

Run directly:
    python -m backend.sync

Or trigger via the API:
    POST /sync
"""

import json
import datetime
import logging
import os

import requests
from dotenv import load_dotenv

from backend.database import engine, Base, SessionLocal
from backend.models import Customer, Product

load_dotenv()

logger = logging.getLogger(__name__)

MIINEX_BASE_URL   = os.getenv("MIINEX_BASE_URL", "https://app.miinex.com/otapis/cronjob/ai-order")
MIINEX_API_TOKEN  = os.getenv("MIINEX_API_TOKEN", "")  # X-API-KEY value

# Seconds to wait for each external HTTP request
REQUEST_TIMEOUT = int(os.getenv("MIINEX_REQUEST_TIMEOUT", "30"))


def _build_headers() -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if MIINEX_API_TOKEN:
        headers["X-API-KEY"] = MIINEX_API_TOKEN
    return headers


def _fetch_json(url: str) -> dict:
    try:
        resp = requests.get(url, headers=_build_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        return None


def sync_customers(db=None) -> dict:
    """Fetch customers from external API and upsert into local DB."""
    close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        data = _fetch_json(f"{MIINEX_BASE_URL}/fetch-customers")
        if data is None or not data.get("status"):
            return {"success": False, "message": "Failed to fetch customers from external API"}

        customers = data["data"]["customers"]
        now = datetime.datetime.utcnow()
        upserted = 0

        for c in customers:
            existing = db.query(Customer).filter(Customer.customer_id == c["customer_id"]).first()
            allow_products_json = json.dumps(c.get("allow_products", []))

            if existing:
                existing.business_name   = c.get("business_name", "")
                existing.email           = c.get("email", "")
                existing.allow_products  = allow_products_json
                existing.synced_at       = now
            else:
                db.add(Customer(
                    customer_id    = c["customer_id"],
                    business_name  = c.get("business_name", ""),
                    email          = c.get("email", ""),
                    allow_products = allow_products_json,
                    synced_at      = now,
                ))
            upserted += 1

        db.commit()
        logger.info("Synced %d customers.", upserted)
        return {"success": True, "upserted": upserted}

    except Exception as exc:
        db.rollback()
        logger.exception("Error syncing customers: %s", exc)
        return {"success": False, "message": str(exc)}
    finally:
        if close_db:
            db.close()


def sync_products(db=None) -> dict:
    """Fetch products from external API and upsert into local DB."""
    close_db = db is None
    if db is None:
        db = SessionLocal()

    try:
        data = _fetch_json(f"{MIINEX_BASE_URL}/fetch-products")
        if data is None or not data.get("status"):
            return {"success": False, "message": "Failed to fetch products from external API"}

        products = data["data"]["products"]
        now = datetime.datetime.utcnow()
        upserted = 0

        for p in products:
            existing = db.query(Product).filter(Product.id == p["id"]).first()

            fields = dict(
                product_code  = p.get("product_code", ""),
                name          = p.get("name", ""),
                desc          = p.get("desc", ""),
                image         = p.get("image"),
                cat_id        = str(p.get("cat_id", "")),
                base_unit_id  = int(p.get("base_unit_id", 0)),
                order_unit_id = str(p.get("order_unit_id", "")),
                min_order_qut     = str(p.get("min_order_qut", "1")),
                max_order_qut     = str(p.get("max_order_qut", "")),
                allow_decimal_qty = int(p.get("allow_decimal_qty", 1)),
                base_unit         = p.get("base_unit", ""),
                order_unit    = p.get("order_unit", ""),
                category      = p.get("category", ""),
                synced_at     = now,
            )

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
            else:
                db.add(Product(id=p["id"], **fields))

            upserted += 1

        db.commit()
        logger.info("Synced %d products.", upserted)
        return {"success": True, "upserted": upserted}

    except Exception as exc:
        db.rollback()
        logger.exception("Error syncing products: %s", exc)
        return {"success": False, "message": str(exc)}
    finally:
        if close_db:
            db.close()


def sync_all() -> dict:
    """Run both customer and product sync in sequence."""
    Base.metadata.create_all(bind=engine)
    customers_result = sync_customers()
    products_result  = sync_products()
    return {"customers": customers_result, "products": products_result}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = sync_all()
    print(result)
