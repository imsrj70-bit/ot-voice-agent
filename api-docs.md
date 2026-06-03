# Ordertron Voice Agent — API Docs

**Base URL:** `http://127.0.0.1:8000`  
All endpoints accept and return **JSON**. All requests use **POST**.

---

## 1. Find Customer

**`POST /find-customer`**

Searches the local DB by business name. Uses multi-tier fuzzy matching:
- Tier 1: Partial phrase match — `"Uptown"` matches `"Uptown Cafe"`
- Tier 2: Space-normalised match — `"UptownCafe"` matches `"Uptown Cafe"`
- Tier 3: All words must appear (AND) — `"cafe uptown"` matches `"Uptown Cafe"`
- Tier 4: Any word matches (OR, broadest) — `"cafe"` matches `"Uptown Cafe"`

**Request**
```json
{
  "business_name": "Uptown Cafe"
}
```

**Response — found**
```json
{
  "found": true,
  "customer": {
    "customer_id": 2,
    "business_name": "Uptown Cafe",
    "email": "clairecv@encloud.com.au",
    "has_phone": false
  }
}
```

**Response — not found**
```json
{
  "found": false,
  "customer": null
}
```

---

## 2. Save Customer Phone

**`POST /save-customer-phone`**

Saves or updates the phone number for a customer. Only call this when the customer willingly provides their number — the voice agent should only ask if `has_phone` was `false` on the `find_customer` response.

**Request**
```json
{
  "customer_id": 2,
  "phone": "+61491579724"
}
```

**Response — success**
```json
{
  "success": true,
  "message": null
}
```

**Errors**
| Status | Body | Reason |
|--------|------|--------|
| 404 | `{"detail": "Customer not found"}` | Invalid `customer_id` |
| 200 | `{"success": false, "message": "Phone number cannot be empty"}` | Empty phone string |

---

## 3. Search Products

**`POST /search-products`**

Fuzzy-searches products by name or product code. Results are **filtered to only the products that customer is allowed to order** (based on `allow_products` from Miinex).

If `unit` is provided, results are further filtered to products whose `order_unit` belongs to the same unit family (e.g. `"g"`, `"kg"`, `"lbs"` all resolve to the `kg` family). If the unit filter would return zero results, it is ignored and the full fuzzy results are returned instead.

Unit family mapping:
| Customer says | Filters `order_unit` to |
|---|---|
| `g`, `grams`, `kg`, `lbs`, `oz` etc. | `kg` |
| `ml`, `L`, `litres` etc. | `L` |
| `ctn`, `carton` | `CTN` |
| `each`, `ea` | `EACH` |
| `bag` | `BAG` |
| `bunch` | `BUNCH` |

Multi-tier fuzzy matching:
- Tier 1: Phrase match in name — `"coke"` matches `"Coke CTN"`
- Tier 2: Space-normalised — `"CokeCTN"` matches `"Coke CTN"`
- Tier 3: Match against product code — `"Coke24"` matches by code
- Tier 4: All tokens AND — `"coke ctn"` matches `"Coke CTN"`
- Tier 5: Any token OR (broadest) — `"coke"` matches any product with that word

Returns up to **10** results.

**Request**
```json
{
  "query": "bananas",
  "customer_id": 2,
  "unit": "kg"
}
```

`unit` is optional. Omit it when the customer gives no unit.

**Response**
```json
[
  {
    "id": 1,
    "product_code": "APPGRN10KG",
    "name": "Apples Green Per KG",
    "desc": "Fresh green apples, sold per kg",
    "order_unit": "kg",
    "base_unit": "kg",
    "min_order_qut": "1",
    "max_order_qut": "",
    "category": "FRESH PRODUCE"
  }
]
```

**Errors**
| Status | Body | Reason |
|--------|------|--------|
| 404 | `{"detail": "Customer not found"}` | Invalid `customer_id` |
| 200 | `[]` | No matching products for that customer |

---

## 3. Place Order

**`POST /place-order`**

Validates the order locally (customer exists, products are in their allowed list, minimum qty met), then forwards the order to the **Miinex external API** (`create-order`).

**Request**
```json
{
  "customer_id": 2,
  "items": [
    { "product_id": 34, "qty": 2 },
    { "product_id": 5,  "qty": 10 }
  ]
}
```

**Response — success**
```json
{
  "success": true,
  "message": null,
  "data": { "...external API response..." }
}
```

**Response — rejected by Miinex**
```json
{
  "success": false,
  "message": "Products not found",
  "data": { "status": false, "message": "Products not found" }
}
```

**Validation errors**
| Status | Body | Reason |
|--------|------|--------|
| 404 | `{"detail": "Customer not found"}` | Invalid `customer_id` |
| 404 | `{"detail": "Product 99 not found"}` | Product not in local DB |
| 400 | `{"detail": "Product 99 is not available for this customer"}` | Not in customer's allowed list |
| 400 | `{"detail": "Minimum order quantity for 'Coke CTN' is 1.0"}` | `qty` below `min_order_qut` |
| 502 | `{"detail": "External order API returned an error"}` | Miinex API HTTP error |

---

## 4. Sync

**`POST /sync`**

Pulls fresh customers and products from Miinex (`fetch-customers` + `fetch-products`) and upserts them into the local SQLite DB. Safe to call at any time — existing records are updated, new ones are inserted.

**Request** — no body needed

**Response**
```json
{
  "customers": { "success": true, "upserted": 2 },
  "products":  { "success": true, "upserted": 16 }
}
```

**Error (external API unreachable / auth failed)**
```json
{
  "customers": { "success": false, "message": "Failed to fetch customers from external API" },
  "products":  { "success": false, "message": "Failed to fetch products from external API" }
}
```

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Seed local DB from Miinex (run once, then as needed)
python -m backend.sync

# 3. Start server
uvicorn backend.app:app --reload --port 8000
```

Interactive docs available at: `http://127.0.0.1:8000/docs`

---

## Environment Variables (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `MIINEX_BASE_URL` | Base URL for Miinex external APIs | `https://app.miinex.com/otapis/cronjob/ai-order` |
| `MIINEX_API_TOKEN` | Value sent as `X-API-KEY` header | *(empty)* |
| `MIINEX_REQUEST_TIMEOUT` | HTTP timeout in seconds for external calls | `30` |
