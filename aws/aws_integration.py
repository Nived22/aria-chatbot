# aws/aws_integration.py
# AWS Cloud Integration — §4.3 of dissertation
# Covers: DynamoDB (session logs), CloudWatch (metrics), S3 (config), Lambda (handover alerts)
#
# Setup: pip install boto3
# Configure credentials in .env:
#   AWS_ACCESS_KEY_ID=...
#   AWS_SECRET_ACCESS_KEY=...
#   AWS_REGION=eu-west-2  (UK region for GDPR compliance)

import os
import json
import time
from datetime import datetime
from typing import Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

# Load env vars
AWS_REGION       = os.getenv("AWS_REGION", "eu-west-2")
DYNAMODB_TABLE   = os.getenv("DYNAMODB_TABLE", "emotion_chatbot_sessions")
S3_BUCKET        = os.getenv("S3_BUCKET", "emotion-chatbot-configs")
CLOUDWATCH_NS    = os.getenv("CLOUDWATCH_NAMESPACE", "EmotionChatbot")
LAMBDA_FUNC_NAME = os.getenv("LAMBDA_HANDOVER_FUNCTION", "emotion_chatbot_handover_alert")


def _get_client(service: str):
    """Get a boto3 client. Returns None if AWS not configured."""
    if not BOTO3_AVAILABLE:
        print(f"[AWS] boto3 not installed. Run: pip install boto3")
        return None
    try:
        return boto3.client(service, region_name=AWS_REGION)
    except NoCredentialsError:
        print(f"[AWS] No credentials found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env")
        return None


def _get_resource(service: str):
    if not BOTO3_AVAILABLE:
        return None
    try:
        return boto3.resource(service, region_name=AWS_REGION)
    except NoCredentialsError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DynamoDB — Session Logging (§4.3.1, FR9)
# ─────────────────────────────────────────────────────────────────────────────

def dynamodb_log_turn(session_id: str, turn_data: dict) -> bool:
    """
    Log a single conversation turn to DynamoDB.
    Table schema: PK=session_id, SK=turn_number, TTL=retention_timestamp
    """
    resource = _get_resource("dynamodb")
    if not resource:
        return False
    try:
        table = resource.Table(DYNAMODB_TABLE)
        item = {
            "session_id": session_id,
            "turn_id": f"{session_id}#{turn_data.get('turn_number', 0):04d}",
            "timestamp": datetime.utcnow().isoformat(),
            "user_message": turn_data.get("user_message", ""),
            "sentiment_score": str(turn_data.get("sentiment_score", 0)),
            "frustration_score": str(turn_data.get("frustration_score", 0)),
            "frustration_level": turn_data.get("frustration_level", ""),
            "response_mode": turn_data.get("response_mode", ""),
            "handover_triggered": str(turn_data.get("handover_triggered", False)),
            # TTL: 12 months from now (GDPR §4.4)
            "ttl": int(time.time()) + (365 * 24 * 3600)
        }
        table.put_item(Item=item)
        return True
    except ClientError as e:
        print(f"[AWS-DynamoDB] Error: {e.response['Error']['Message']}")
        return False


def dynamodb_log_escalation(session_id: str, bundle: dict) -> bool:
    """Log a handover escalation event to DynamoDB."""
    resource = _get_resource("dynamodb")
    if not resource:
        return False
    try:
        table = resource.Table(DYNAMODB_TABLE)
        table.put_item(Item={
            "session_id": session_id,
            "turn_id": f"{session_id}#HANDOVER",
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "HANDOVER",
            "ref_id": bundle.get("ref_id", ""),
            "priority": bundle.get("priority", ""),
            "escalation_reason": bundle.get("escalation_reason", ""),
            "frustration_score": str(bundle.get("current_frustration_score", 0)),
            "agent_note": bundle.get("agent_note", ""),
            "ttl": int(time.time()) + (365 * 24 * 3600)
        })
        return True
    except ClientError as e:
        print(f"[AWS-DynamoDB] Escalation log error: {e}")
        return False


def create_dynamodb_table_if_not_exists() -> bool:
    """Create the DynamoDB table if it doesn't exist yet."""
    client = _get_client("dynamodb")
    if not client:
        return False
    try:
        client.create_table(
            TableName=DYNAMODB_TABLE,
            KeySchema=[
                {"AttributeName": "session_id", "KeyType": "HASH"},
                {"AttributeName": "turn_id", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "turn_id", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST",
            # Enable TTL for auto-deletion (FR10: data retention)
        )
        # Enable TTL field
        client.update_time_to_live(
            TableName=DYNAMODB_TABLE,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"}
        )
        print(f"[AWS-DynamoDB] Table '{DYNAMODB_TABLE}' created with TTL enabled.")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"[AWS-DynamoDB] Table already exists.")
            return True
        print(f"[AWS-DynamoDB] Create error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CloudWatch — Performance Metrics (§4.3.1, §5.2)
# ─────────────────────────────────────────────────────────────────────────────

def cloudwatch_put_metric(metric_name: str, value: float, unit: str = "None",
                           dimensions: Optional[list] = None) -> bool:
    """
    Push a custom metric to AWS CloudWatch.
    Used for: frustration scores, response latency, escalation rates.
    """
    client = _get_client("cloudwatch")
    if not client:
        return False
    try:
        metric_data = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.utcnow()
        }
        if dimensions:
            metric_data["Dimensions"] = dimensions
        client.put_metric_data(
            Namespace=CLOUDWATCH_NS,
            MetricData=[metric_data]
        )
        return True
    except ClientError as e:
        print(f"[AWS-CloudWatch] Error: {e}")
        return False


def cloudwatch_log_frustration(session_id: str, frustration_score: float, turn: int) -> None:
    """Log frustration score as a CloudWatch metric for trend monitoring."""
    cloudwatch_put_metric("FrustrationScore", frustration_score, "None",
                          [{"Name": "Session", "Value": session_id[:8]}])


def cloudwatch_log_latency(latency_ms: float) -> None:
    """Log response latency to CloudWatch. Alert if > 1000ms (§5.2 target)."""
    cloudwatch_put_metric("ResponseLatencyMs", latency_ms, "Milliseconds")


def cloudwatch_log_handover(session_id: str, reason: str) -> None:
    """Increment handover counter in CloudWatch."""
    cloudwatch_put_metric("HandoverTriggered", 1.0, "Count",
                          [{"Name": "Reason", "Value": reason}])


# ─────────────────────────────────────────────────────────────────────────────
# S3 — Config and Model Storage (§4.3.1)
# ─────────────────────────────────────────────────────────────────────────────

def s3_upload_file(local_path: str, s3_key: str) -> bool:
    """Upload a file (model config, evaluation results) to S3."""
    client = _get_client("s3")
    if not client:
        return False
    try:
        client.upload_file(local_path, S3_BUCKET, s3_key)
        print(f"[AWS-S3] Uploaded {local_path} → s3://{S3_BUCKET}/{s3_key}")
        return True
    except ClientError as e:
        print(f"[AWS-S3] Upload error: {e}")
        return False


def s3_download_model_config(s3_key: str, local_path: str) -> bool:
    """Download model config or checkpoint from S3."""
    client = _get_client("s3")
    if not client:
        return False
    try:
        client.download_file(S3_BUCKET, s3_key, local_path)
        print(f"[AWS-S3] Downloaded s3://{S3_BUCKET}/{s3_key} → {local_path}")
        return True
    except ClientError as e:
        print(f"[AWS-S3] Download error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Lambda — Handover Alert Trigger (§3.1.1 Step 8, §4.3.1)
# ─────────────────────────────────────────────────────────────────────────────

def lambda_trigger_handover_alert(bundle: dict) -> bool:
    """
    Trigger AWS Lambda function when human handover is needed.
    Lambda function notifies the human agent queue / CRM system.
    Early alert at frustration >= 0.5; immediate at >= 0.7.
    """
    client = _get_client("lambda")
    if not client:
        return False
    try:
        payload = {
            "ref_id": bundle.get("ref_id"),
            "session_id": bundle.get("session_id"),
            "priority": bundle.get("priority"),
            "frustration_score": bundle.get("current_frustration_score"),
            "reason": bundle.get("escalation_reason"),
            "agent_note": bundle.get("agent_note"),
            "timestamp": datetime.utcnow().isoformat()
        }
        response = client.invoke(
            FunctionName=LAMBDA_FUNC_NAME,
            InvocationType="Event",   # async invocation
            Payload=json.dumps(payload).encode()
        )
        success = response["StatusCode"] == 202
        print(f"[AWS-Lambda] Handover alert {'sent' if success else 'FAILED'} for ref {bundle.get('ref_id')}")
        return success
    except ClientError as e:
        print(f"[AWS-Lambda] Error: {e}")
        return False


def lambda_trigger_early_alert(session_id: str, frustration_score: float) -> bool:
    """
    Early alert (§3.1.1 Step 8): notify agent at frustration >= 0.5 to stand by.
    Frustration 0.5 = alert, 0.7 = immediate handover.
    """
    client = _get_client("lambda")
    if not client:
        return False
    try:
        payload = {
            "type": "EARLY_ALERT",
            "session_id": session_id,
            "frustration_score": frustration_score,
            "timestamp": datetime.utcnow().isoformat()
        }
        client.invoke(
            FunctionName=LAMBDA_FUNC_NAME,
            InvocationType="Event",
            Payload=json.dumps(payload).encode()
        )
        return True
    except ClientError as e:
        print(f"[AWS-Lambda] Early alert error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

def check_aws_connectivity() -> dict:
    """Check connectivity to all AWS services. Run on startup."""
    status = {}
    for service in ["dynamodb", "s3", "cloudwatch", "lambda"]:
        client = _get_client(service)
        status[service] = "connected" if client else "unavailable"
    return status
