import json
import logging
import os
from typing import List, Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.database import Base, engine, get_db
from backend.models import Customer, Product
from backend.sync import sync_all

load_dotenv()

logger = logging.getLogger(__name__)

MIINEX_BASE_URL  = os.getenv("MIINEX_BASE_URL", "https://app.miinex.com/otapis/cronjob/ai-order")
MIINEX_API_TOKEN = os.getenv("MIINEX_API_TOKEN", "")
REQUEST_TIMEOUT  = int(os.getenv("MIINEX_REQUEST_TIMEOUT", "30"))

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ordertron Voice Agent API")

# Serve the frontend UI at /
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class FindCustomerRequest(BaseModel):
    business_name: str

class CustomerSchema(BaseModel):
    customer_id: int
    business_name: str
    email: str
    has_phone: bool

class FindCustomerResponse(BaseModel):
    found: bool
    customer: Optional[CustomerSchema] = None


class SavePhoneRequest(BaseModel):
    customer_id: int
    phone: str

class SavePhoneResponse(BaseModel):
    success: bool
    message: Optional[str] = None


class SearchProductsRequest(BaseModel):
    query: str
    customer_id: int
    unit: Optional[str] = None  # e.g. "kg", "g", "lbs", "CTN" — used to filter results

class ProductSchema(BaseModel):
    id: int
    product_code: str
    name: str
    desc: str
    order_unit: str
    base_unit: str
    min_order_qut: str
    max_order_qut: str
    category: str


class OrderItemSchema(BaseModel):
    product_id: int
    qty: float

class PlaceOrderRequest(BaseModel):
    customer_id: int
    items: List[OrderItemSchema]

class PlaceOrderResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_headers() -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if MIINEX_API_TOKEN:
        headers["X-API-KEY"] = MIINEX_API_TOKEN
    return headers


def _get_allowed_ids(db: Session, customer_id: int) -> Optional[List[int]]:
    """Return the list of allowed product IDs for this customer, or None if not found."""
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if customer is None:
        return None
    try:
        return json.loads(customer.allow_products or "[]")
    except (ValueError, TypeError):
        return []


def _normalise_unit_family(unit: Optional[str]) -> Optional[str]:
    """Map a customer-spoken unit to a canonical order_unit family for filtering."""
    if not unit:
        return None
    u = unit.strip().lower()
    if u in {"g", "gram", "grams", "kg", "kilogram", "kilograms", "kilo", "kilos",
             "kgs", "lb", "lbs", "pound", "pounds", "oz", "ounce", "ounces"}:
        return "kg"
    if u in {"ml", "millilitre", "millilitres", "milliliter", "milliliters",
             "l", "litre", "litres", "liter", "liters"}:
        return "L"
    if u in {"ctn", "carton", "cartons"}:
        return "CTN"
    if u in {"each", "ea"}:
        return "EACH"
    if u in {"bag", "bags"}:
        return "BAG"
    if u in {"bunch", "bunches"}:
        return "BUNCH"
    # Unknown unit — no filtering
    return None


def _to_product_schema(p: Product) -> ProductSchema:
    return ProductSchema(
        id=p.id,
        product_code=p.product_code or "",
        name=p.name or "",
        desc=p.desc or "",
        order_unit=p.order_unit or "",
        base_unit=p.base_unit or "",
        min_order_qut=p.min_order_qut or "1",
        max_order_qut=p.max_order_qut or "",
        category=p.category or "",
    )


def _search_products_in_db(
    db: Session, raw: str, allowed_ids: List[int]
) -> List[Product]:
    """Multi-tier fuzzy search, restricted to `allowed_ids`."""
    if not allowed_ids:
        return []

    def _query(filters) -> list:
        return (
            db.query(Product)
            .filter(Product.id.in_(allowed_ids), *filters)
            .limit(10)
            .all()
        )

    # Tier 1 — phrase match in name
    results = _query([Product.name.ilike(f"%{raw}%")])
    if results:
        return results

    # Tier 2 — space-normalised match (handles "CokeCTN" vs "Coke CTN")
    normalized = raw.replace(" ", "")
    if normalized != raw:
        results = _query([func.replace(Product.name, " ", "").ilike(f"%{normalized}%")])
        if results:
            return results

    # Tier 3 — match against product_code
    results = _query([Product.product_code.ilike(f"%{raw}%")])
    if results:
        return results

    # Tier 4 — all tokens must appear (AND)
    tokens = [t for t in raw.split() if len(t) > 1]
    if tokens:
        results = _query([Product.name.ilike(f"%{t}%") for t in tokens])
        if results:
            return results

    # Tier 5 — any token matches (OR, broadest fallback)
    if tokens:
        results = _query([or_(*[Product.name.ilike(f"%{t}%") for t in tokens])])
        if results:
            return results

    return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/find-customer", response_model=FindCustomerResponse)
def find_customer(req: FindCustomerRequest, db: Session = Depends(get_db)):
    """
    Search for a customer by business name (case-insensitive partial match).
    Returns the first match if found.
    """
    raw = req.business_name.strip()
    if not raw:
        return {"found": False}

    # Tier 1 — exact partial match (e.g. "Uptown Cafe" or "Uptown")
    customer = (
        db.query(Customer)
        .filter(Customer.business_name.ilike(f"%{raw}%"))
        .first()
    )

    # Tier 2 — space-normalised match (e.g. "UptownCafe" → "Uptown Cafe")
    if customer is None:
        normalized = raw.replace(" ", "")
        if normalized != raw:
            customer = (
                db.query(Customer)
                .filter(func.replace(Customer.business_name, " ", "").ilike(f"%{normalized}%"))
                .first()
            )
        else:
            # query has no spaces — also try matching stored name with spaces stripped
            customer = (
                db.query(Customer)
                .filter(func.replace(Customer.business_name, " ", "").ilike(f"%{raw}%"))
                .first()
            )

    # Tier 3 — all tokens must appear (AND)
    if customer is None:
        tokens = [t for t in raw.split() if len(t) > 1]
        if tokens:
            customer = (
                db.query(Customer)
                .filter(*[Customer.business_name.ilike(f"%{t}%") for t in tokens])
                .first()
            )

    # Tier 4 — any token matches (OR, broadest fallback)
    if customer is None:
        tokens = [t for t in raw.split() if len(t) > 1]
        if tokens:
            customer = (
                db.query(Customer)
                .filter(or_(*[Customer.business_name.ilike(f"%{t}%") for t in tokens]))
                .first()
            )

    if customer:
        return {
            "found": True,
            "customer": {
                "customer_id": customer.customer_id,
                "business_name": customer.business_name,
                "email": customer.email,
                "has_phone": bool(customer.phone and customer.phone.strip()),
            },
        }
    return {"found": False}


@app.post("/save-customer-phone", response_model=SavePhoneResponse)
def save_customer_phone(req: SavePhoneRequest, db: Session = Depends(get_db)):
    """
    Save or update the phone number for a customer.
    Only call this when the customer voluntarily provides their number.
    """
    customer = db.query(Customer).filter(Customer.customer_id == req.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    phone = req.phone.strip()
    if not phone:
        return SavePhoneResponse(success=False, message="Phone number cannot be empty")

    customer.phone = phone
    db.commit()
    return SavePhoneResponse(success=True)


@app.post("/search-products", response_model=List[ProductSchema])
def search_products(req: SearchProductsRequest, db: Session = Depends(get_db)):
    """
    Search products by name/code, filtered to products allowed for the customer.
    If `unit` is provided, results are further filtered to products whose order_unit
    matches the same unit family (e.g. unit="g" filters to kg products only).
    """
    allowed_ids = _get_allowed_ids(db, req.customer_id)
    if allowed_ids is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not allowed_ids:
        return []

    products = _search_products_in_db(db, req.query.strip(), allowed_ids)

    # Apply unit family filter if the caller specified a unit
    unit_family = _normalise_unit_family(req.unit)
    if unit_family and products:
        filtered = [p for p in products if (p.order_unit or "").upper() == unit_family.upper()]
        # Only apply filter if it still returns results; otherwise return unfiltered
        # so the agent can handle incompatibility itself
        if filtered:
            products = filtered

    # De-duplicate by ID
    seen, result = set(), []
    for p in products:
        if p.id not in seen:
            seen.add(p.id)
            result.append(_to_product_schema(p))
    return result


@app.post("/place-order", response_model=PlaceOrderResponse)
def place_order(req: PlaceOrderRequest, db: Session = Depends(get_db)):
    """
    Validate the customer and products locally, then forward the order to the
    external Miinex create-order API.
    """
    # --- Local validation ---
    customer = db.query(Customer).filter(Customer.customer_id == req.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    allowed_ids = json.loads(customer.allow_products or "[]")

    for item in req.items:
        if item.product_id not in allowed_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Product {item.product_id} is not available for this customer",
            )
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")

        min_qty = float(product.min_order_qut or 1)
        if item.qty < min_qty:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum order quantity for '{product.name}' is {int(min_qty) if min_qty == int(min_qty) else min_qty} {product.order_unit}",
            )

        if product.max_order_qut and product.max_order_qut.strip():
            max_qty = float(product.max_order_qut)
            if item.qty > max_qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"Maximum order quantity for '{product.name}' is {int(max_qty) if max_qty == int(max_qty) else max_qty} {product.order_unit}",
                )

    # --- Forward to external API ---
    payload = {
        "customer_id": req.customer_id,
        "products": [{"product_id": item.product_id, "qty": item.qty} for item in req.items],
    }

    try:
        resp = requests.post(
            f"{MIINEX_BASE_URL}/create-order",
            json=payload,
            headers=_build_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
    except requests.HTTPError as exc:
        logger.error("External create-order HTTP error: %s", exc)
        raise HTTPException(status_code=502, detail="External order API returned an error")
    except Exception as exc:
        logger.error("External create-order request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not reach external order API")

    if not body.get("status"):
        return PlaceOrderResponse(
            success=False,
            message=body.get("message", "Order was rejected by the server"),
            data=body,
        )

    return PlaceOrderResponse(success=True, data=body)


@app.post("/sync")
def trigger_sync():
    """
    Manually trigger a sync of customers and products from the external Miinex APIs.
    Safe to call at any time; upserts existing records.
    """
    result = sync_all()
    return result
