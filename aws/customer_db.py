# aws/customer_db.py
# Customer database — tries real AWS DynamoDB first, falls back to mock
# Works both locally (reads .env) and on Streamlit Cloud (reads st.secrets)

import os

def _get_secret(key: str) -> str:
    """Read from Streamlit secrets first, then environment variables."""
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val: return val
    except Exception:
        pass
    return os.getenv(key, "")

VIP_THRESHOLD = 500.00

# ── Mock data — used when AWS not configured ──────────────────────────────────
_MOCK_CUSTOMERS = {
    "C001": {"customer_id":"C001","name":"James Wilson",       "total_spent":850.00,  "order_count":12,"is_vip":True,  "last_order":"2025-01-15","vip_reason":"Loyalty reward — 12 orders"},
    "C002": {"customer_id":"C002","name":"Sarah Chen",         "total_spent":120.00,  "order_count":3, "is_vip":False, "last_order":"2025-02-01"},
    "C003": {"customer_id":"C003","name":"Mohammed Al-Hassan", "total_spent":1240.00, "order_count":28,"is_vip":True,  "last_order":"2025-02-10","vip_reason":"Premium customer — £1,240 spent"},
    "C004": {"customer_id":"C004","name":"Emily Roberts",      "total_spent":340.00,  "order_count":7, "is_vip":False, "last_order":"2025-01-20"},
    "C005": {"customer_id":"C005","name":"David Park",         "total_spent":2100.00, "order_count":45,"is_vip":True,  "last_order":"2025-02-14","vip_reason":"Top spender — £2,100 spent"},
    "C006": {"customer_id":"C006","name":"Guest User",         "total_spent":0.00,    "order_count":0, "is_vip":False, "last_order":None},
}


def _aws_configured() -> bool:
    return all([
        _get_secret("AWS_ACCESS_KEY_ID"),
        _get_secret("AWS_SECRET_ACCESS_KEY"),
        _get_secret("DYNAMODB_CUSTOMER_TABLE"),
    ])


def _get_dynamodb_table():
    import boto3
    session = boto3.Session(
        aws_access_key_id     = _get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = _get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name           = _get_secret("AWS_REGION") or "eu-west-1",
    )
    dynamodb = session.resource("dynamodb")
    return dynamodb.Table(_get_secret("DYNAMODB_CUSTOMER_TABLE"))


def get_customer(customer_id: str) -> dict:
    """Fetch customer from DynamoDB, fall back to mock."""
    if _aws_configured():
        try:
            table = _get_dynamodb_table()
            resp  = table.get_item(Key={"customer_id": customer_id})
            item  = resp.get("Item")
            if item:
                item["is_vip"] = float(item.get("total_spent", 0)) >= VIP_THRESHOLD
                print(f"[CustomerDB] ✅ DynamoDB: loaded {customer_id}")
                return item
        except Exception as e:
            print(f"[CustomerDB] DynamoDB error: {e} — using mock")

    return _MOCK_CUSTOMERS.get(customer_id, {
        "customer_id": customer_id,
        "name": "Guest User",
        "total_spent": 0.0,
        "order_count": 0,
        "is_vip": False,
        "last_order": None,
    })


def is_vip_customer(customer_id: str) -> tuple:
    """Returns (is_vip: bool, customer_data: dict)."""
    cdata  = get_customer(customer_id)
    is_vip = cdata.get("is_vip", False) or float(cdata.get("total_spent", 0)) >= VIP_THRESHOLD
    if is_vip and "vip_reason" not in cdata:
        cdata["vip_reason"] = f"£{cdata.get('total_spent',0):,.2f} spent"
    return is_vip, cdata


def list_all_customers() -> list:
    """List all customers — DynamoDB scan or mock list."""
    if _aws_configured():
        try:
            table = _get_dynamodb_table()
            resp  = table.scan()
            items = resp.get("Items", [])
            for item in items:
                item["is_vip"] = float(item.get("total_spent", 0)) >= VIP_THRESHOLD
            if items:
                return items
        except Exception as e:
            print(f"[CustomerDB] DynamoDB scan error: {e} — using mock")

    result = list(_MOCK_CUSTOMERS.values())
    for c in result:
        c["is_vip"] = float(c.get("total_spent", 0)) >= VIP_THRESHOLD
    return result


def get_random_demo_customer() -> dict:
    import random
    vip_customers = [c for c in _MOCK_CUSTOMERS.values() if c["is_vip"]]
    return random.choice(vip_customers)