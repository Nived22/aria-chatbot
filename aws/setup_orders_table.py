# aws/setup_orders_table.py
# Creates shopsmart-orders table and populates with fake orders
# Usage: python aws/setup_orders_table.py

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
from datetime import datetime, timedelta
import random

REGION = os.getenv("AWS_REGION", "eu-north-1")

FAKE_ORDERS = [
    # James Wilson (C001) — VIP
    {"order_number":"34567",  "customer_id":"C001","product":"Wireless Headphones","quantity":1,"price":Decimal("89.99"), "total":Decimal("89.99"), "status":"delayed",          "status_label":"Delayed",          "status_emoji":"⚠️",  "order_date":"01 Mar 2026","delivery_info":"New estimated delivery: 18 Mar 2026","carrier":"DPD",        "tracking_number":"DPD8823991KL"},
    {"order_number":"34521",  "customer_id":"C001","product":"Laptop Stand",       "quantity":1,"price":Decimal("34.99"), "total":Decimal("34.99"), "status":"delivered",         "status_label":"Delivered",        "status_emoji":"✅",  "order_date":"10 Feb 2026","delivery_info":"Delivered on 14 Feb 2026",         "carrier":"Royal Mail","tracking_number":"RM7712900GB"},
    # Sarah Chen (C002)
    {"order_number":"45231",  "customer_id":"C002","product":"Yoga Mat",           "quantity":1,"price":Decimal("24.99"), "total":Decimal("24.99"), "status":"in_transit",        "status_label":"In Transit",       "status_emoji":"🚚",  "order_date":"12 Mar 2026","delivery_info":"Estimated delivery: 16 Mar 2026",   "carrier":"Evri",       "tracking_number":"EV992183744"},
    # Mohammed Al-Hassan (C003) — VIP
    {"order_number":"56789",  "customer_id":"C003","product":"Smart Watch",        "quantity":1,"price":Decimal("199.99"),"total":Decimal("199.99"),"status":"out_for_delivery",  "status_label":"Out for Delivery", "status_emoji":"🛵",  "order_date":"13 Mar 2026","delivery_info":"Expected today by 9pm",             "carrier":"DHL",        "tracking_number":"DHL44521KK9"},
    {"order_number":"56712",  "customer_id":"C003","product":"Coffee Maker",       "quantity":2,"price":Decimal("49.99"), "total":Decimal("99.98"), "status":"delivered",         "status_label":"Delivered",        "status_emoji":"✅",  "order_date":"01 Mar 2026","delivery_info":"Delivered on 05 Mar 2026",         "carrier":"DPD",        "tracking_number":"DPD7712KLP9"},
    # Emily Roberts (C004)
    {"order_number":"67890",  "customer_id":"C004","product":"Running Shoes",      "quantity":1,"price":Decimal("74.99"), "total":Decimal("74.99"), "status":"processing",        "status_label":"Processing",       "status_emoji":"⏳",  "order_date":"14 Mar 2026","delivery_info":"Estimated delivery: 17 Mar 2026",   "carrier":"Royal Mail","tracking_number":"RM8823100GB"},
    # David Park (C005) — VIP
    {"order_number":"78901",  "customer_id":"C005","product":"Bluetooth Speaker",  "quantity":1,"price":Decimal("59.99"), "total":Decimal("59.99"), "status":"dispatched",        "status_label":"Dispatched",       "status_emoji":"📦",  "order_date":"13 Mar 2026","delivery_info":"Estimated delivery: 15 Mar 2026",   "carrier":"DHL",        "tracking_number":"DHL9921KL44"},
    {"order_number":"78845",  "customer_id":"C005","product":"Mechanical Keyboard","quantity":1,"price":Decimal("129.99"),"total":Decimal("129.99"),"status":"delivered",         "status_label":"Delivered",        "status_emoji":"✅",  "order_date":"28 Feb 2026","delivery_info":"Delivered on 03 Mar 2026",         "carrier":"DPD",        "tracking_number":"DPD6612MNB1"},
]

def main():
    print(f"Connecting to DynamoDB — region: {REGION}\n")
    session  = boto3.Session(
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name           = REGION,
    )
    dynamodb = session.resource("dynamodb")

    # Create table
    try:
        table = dynamodb.create_table(
            TableName="shopsmart-orders",
            KeySchema=[{"AttributeName":"order_number","KeyType":"HASH"}],
            AttributeDefinitions=[{"AttributeName":"order_number","AttributeType":"S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        print("✅ Created table: shopsmart-orders\n")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print("✅ Table already exists: shopsmart-orders\n")
            table = dynamodb.Table("shopsmart-orders")
        else:
            print(f"❌ Error creating table: {e}")
            return

    # Insert orders
    success = 0
    for order in FAKE_ORDERS:
        try:
            table.put_item(Item=order)
            print(f"  ✅ Order #{order['order_number']} — {order['product']} — {order['status_emoji']} {order['status_label']}")
            success += 1
        except Exception as e:
            print(f"  ❌ Failed #{order['order_number']}: {e}")

    print(f"\n{'='*50}")
    print(f"✅ {success}/{len(FAKE_ORDERS)} orders added to DynamoDB")
    print(f"\nCustomers can now use these order numbers:")
    print(f"  James Wilson:       #34567 (delayed), #34521 (delivered)")
    print(f"  Sarah Chen:         #45231 (in transit)")
    print(f"  Mohammed Al-Hassan: #56789 (out for delivery), #56712 (delivered)")
    print(f"  Emily Roberts:      #67890 (processing)")
    print(f"  David Park:         #78901 (dispatched), #78845 (delivered)")

if __name__ == "__main__":
    main()
