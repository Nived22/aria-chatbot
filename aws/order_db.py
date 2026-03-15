# aws/order_db.py
# Real order lookup from DynamoDB shopsmart-orders table
# Falls back to generated fake data if AWS not configured

import os
from datetime import datetime, timedelta
import random

def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val: return str(val)
    except Exception:
        pass
    return os.getenv(key, "")

def _aws_configured() -> bool:
    return bool(_get_secret("AWS_ACCESS_KEY_ID") and _get_secret("AWS_SECRET_ACCESS_KEY"))

def _get_table():
    import boto3
    session = boto3.Session(
        aws_access_key_id     = _get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = _get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name           = _get_secret("AWS_REGION") or "eu-north-1",
    )
    return session.resource("dynamodb").Table("shopsmart-orders")


# ── Fake order generator — used as fallback ───────────────────────────────────
_PRODUCTS = [
    "Wireless Headphones", "Running Shoes", "Coffee Maker", "Laptop Stand",
    "Yoga Mat", "Smart Watch", "Desk Lamp", "Backpack", "Water Bottle",
    "Keyboard", "Phone Case", "Sunglasses", "Bluetooth Speaker", "Jacket"
]
_STATUSES = [
    {"status": "delivered",   "label": "Delivered",       "emoji": "✅"},
    {"status": "in_transit",  "label": "In Transit",      "emoji": "🚚"},
    {"status": "processing",  "label": "Processing",      "emoji": "⏳"},
    {"status": "dispatched",  "label": "Dispatched",      "emoji": "📦"},
    {"status": "delayed",     "label": "Delayed",         "emoji": "⚠️"},
    {"status": "out_for_delivery", "label": "Out for Delivery", "emoji": "🛵"},
]

def _generate_fake_order(order_number: str) -> dict:
    """Generate a believable fake order based on order number as seed."""
    seed = sum(ord(c) for c in order_number)
    rng  = random.Random(seed)

    product      = rng.choice(_PRODUCTS)
    status_info  = rng.choice(_STATUSES)
    days_ago     = rng.randint(1, 14)
    order_date   = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%d %b %Y")
    price        = round(rng.uniform(12.99, 199.99), 2)
    qty          = rng.randint(1, 3)

    # Estimated delivery based on status
    if status_info["status"] == "delivered":
        delivery_date = (datetime.utcnow() - timedelta(days=rng.randint(1,3))).strftime("%d %b %Y")
        delivery_msg  = f"Delivered on {delivery_date}"
    elif status_info["status"] == "delayed":
        delivery_date = (datetime.utcnow() + timedelta(days=rng.randint(3,7))).strftime("%d %b %Y")
        delivery_msg  = f"New estimated delivery: {delivery_date}"
    elif status_info["status"] == "out_for_delivery":
        delivery_msg  = "Expected today by 9pm"
    else:
        delivery_date = (datetime.utcnow() + timedelta(days=rng.randint(1,5))).strftime("%d %b %Y")
        delivery_msg  = f"Estimated delivery: {delivery_date}"

    carrier    = rng.choice(["Royal Mail", "DPD", "Evri", "DHL", "Hermes"])
    tracking   = f"{''.join(rng.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=12))}"

    return {
        "order_number":   order_number,
        "product":        product,
        "quantity":       qty,
        "price":          price,
        "total":          round(price * qty, 2),
        "status":         status_info["status"],
        "status_label":   status_info["label"],
        "status_emoji":   status_info["emoji"],
        "order_date":     order_date,
        "delivery_info":  delivery_msg,
        "carrier":        carrier,
        "tracking_number": tracking,
        "source":         "generated"
    }


def lookup_order(order_number: str) -> dict | None:
    """
    Look up order from DynamoDB first, fall back to generated fake data.
    Always returns something for any order number — makes conversations realistic.
    """
    # Clean the order number
    order_number = str(order_number).strip().lstrip("#")

    # Try DynamoDB first
    if _aws_configured():
        try:
            table = _get_table()
            resp  = table.get_item(Key={"order_number": order_number})
            item  = resp.get("Item")
            if item:
                item["source"] = "database"
                print(f"[OrderDB] ✅ Found order {order_number} in DynamoDB")
                return item
        except Exception as e:
            print(f"[OrderDB] DynamoDB error: {e} — using generated data")

    # Fall back to generated fake order (always works)
    order = _generate_fake_order(order_number)
    print(f"[OrderDB] 📦 Generated fake order for {order_number}: {order['status_label']}")
    return order


def format_order_for_claude(order: dict) -> str:
    """
    Format order data as a context string for Claude.
    Claude uses this to give accurate, specific responses.
    """
    if not order:
        return "No order information available."

    lines = [
        f"ORDER DATA FOR #{order['order_number']}:",
        f"  Product: {order['quantity']}x {order['product']} — £{order['total']:.2f}",
        f"  Status: {order['status_emoji']} {order['status_label']}",
        f"  Order placed: {order['order_date']}",
        f"  Delivery: {order['delivery_info']}",
        f"  Carrier: {order['carrier']} | Tracking: {order['tracking_number']}",
    ]

    # Add status-specific guidance for Claude
    status = order.get("status","")
    if status == "delivered":
        lines.append("  INSTRUCTION: Order has been delivered. If customer says they haven't received it, apologise and offer to investigate with the carrier.")
    elif status == "delayed":
        lines.append("  INSTRUCTION: Order is delayed. Acknowledge this proactively, apologise sincerely, and give the new delivery date.")
    elif status == "out_for_delivery":
        lines.append("  INSTRUCTION: Order is out for delivery today. Reassure the customer it will arrive today.")
    elif status == "in_transit":
        lines.append("  INSTRUCTION: Order is on its way. Give the estimated delivery date and tracking number.")
    elif status == "processing":
        lines.append("  INSTRUCTION: Order is still being processed. Let the customer know it will be dispatched soon.")

    return "\n".join(lines)
