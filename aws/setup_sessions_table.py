# aws/setup_sessions_table.py
# Run once to create the shopsmart-sessions DynamoDB table
# Usage: python aws/setup_sessions_table.py

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "eu-north-1")

def main():
    session  = boto3.Session(
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name           = REGION,
    )
    dynamodb = session.resource("dynamodb")

    try:
        table = dynamodb.create_table(
            TableName="shopsmart-sessions",
            KeySchema=[{"AttributeName":"session_id","KeyType":"HASH"}],
            AttributeDefinitions=[{"AttributeName":"session_id","AttributeType":"S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        print("✅ Created table: shopsmart-sessions")
        print("   Your deployed chatbot will now save all sessions to DynamoDB.")
        print("   The backend dashboard will read from the same table in real time.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print("✅ Table already exists: shopsmart-sessions")
        else:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()