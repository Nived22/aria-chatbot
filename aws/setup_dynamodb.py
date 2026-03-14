# aws/setup_dynamodb.py
# Run this ONCE to populate your DynamoDB table with customer data
# Usage: python aws/setup_dynamodb.py

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import boto3
from decimal import Decimal

# ── Config ────────────────────────────────────────────────────────────────────
TABLE_NAME = os.getenv("DYNAMODB_CUSTOMER_TABLE", "shopsmart-customers")
REGION     = os.getenv("AWS_REGION", "eu-north-1")

# ── Customers to insert ───────────────────────────────────────────────────────
CUSTOMERS = [
    {
        "customer_id":  "C001",
        "name":         "James Wilson",
        "total_spent":  Decimal("850.00"),
        "order_count":  12,
        "is_vip":       True,
        "last_order":   "2025-01-15",
        "vip_reason":   "Loyalty reward — 12 orders"
    },
    {
        "customer_id":  "C002",
        "name":         "Sarah Chen",
        "total_spent":  Decimal("120.00"),
        "order_count":  3,
        "is_vip":       False,
        "last_order":   "2025-02-01"
    },
    {
        "customer_id":  "C003",
        "name":         "Mohammed Al-Hassan",
        "total_spent":  Decimal("1240.00"),
        "order_count":  28,
        "is_vip":       True,
        "last_order":   "2025-02-10",
        "vip_reason":   "Premium customer — £1,240 spent"
    },
    {
        "customer_id":  "C004",
        "name":         "Emily Roberts",
        "total_spent":  Decimal("340.00"),
        "order_count":  7,
        "is_vip":       False,
        "last_order":   "2025-01-20"
    },
    {
        "customer_id":  "C005",
        "name":         "David Park",
        "total_spent":  Decimal("2100.00"),
        "order_count":  45,
        "is_vip":       True,
        "last_order":   "2025-02-14",
        "vip_reason":   "Top spender — £2,100 spent"
    },
    {
        "customer_id":  "C006",
        "name":         "Guest User",
        "total_spent":  Decimal("0.00"),
        "order_count":  0,
        "is_vip":       False,
        "last_order":   None
    },
]


def main():
    print(f"Connecting to DynamoDB — region: {REGION}")
    print(f"Table: {TABLE_NAME}\n")

    session = boto3.Session(
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name           = REGION,
    )
    dynamodb = session.resource("dynamodb")
    table    = dynamodb.Table(TABLE_NAME)

    success = 0
    for customer in CUSTOMERS:
        # Remove None values — DynamoDB doesn't accept None
        item = {k: v for k, v in customer.items() if v is not None}
        try:
            table.put_item(Item=item)
            vip = "⭐ VIP" if customer["is_vip"] else "     "
            print(f"  ✅ {vip}  {customer['customer_id']} — {customer['name']}")
            success += 1
        except Exception as e:
            print(f"  ❌ Failed {customer['customer_id']}: {e}")

    print(f"\n{'='*45}")
    print(f"✅ {success}/{len(CUSTOMERS)} customers added to DynamoDB")
    print(f"Table: {TABLE_NAME} in {REGION}")
    print(f"\nYour chatbot will now use real AWS data!")


if __name__ == "__main__":
    main()
