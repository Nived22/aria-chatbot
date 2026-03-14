# aws/setup_ses.py
# Run once to verify your email address with AWS SES
# Usage: python aws/setup_ses.py your@email.com

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import boto3

def main():
    if len(sys.argv) < 2:
        print("Usage: python aws/setup_ses.py your@email.com")
        return

    email  = sys.argv[1]
    region = os.getenv("AWS_REGION", "eu-north-1")

    ses = boto3.client(
        "ses",
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name           = region,
    )

    try:
        ses.verify_email_identity(EmailAddress=email)
        print(f"✅ Verification email sent to: {email}")
        print(f"   Check your inbox and click the verification link.")
        print(f"   Once verified, add to your .env and Streamlit secrets:")
        print(f"")
        print(f'   ALERT_EMAIL = "{email}"')
        print(f'   SES_SENDER_EMAIL = "{email}"')
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
