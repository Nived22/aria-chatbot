# utils/logger.py
# GDPR-compliant session logger
# Writes to DynamoDB when AWS is configured (deployed), local files otherwise (local dev)

import os
import json
import uuid
from datetime import datetime, timedelta

RETENTION_DAYS = 365
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

SESSION_TABLE = "shopsmart-sessions"


# ── Secrets helper ────────────────────────────────────────────────────────────
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


def _get_session_table():
    import boto3
    session = boto3.Session(
        aws_access_key_id     = _get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = _get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name           = _get_secret("AWS_REGION") or "eu-north-1",
    )
    return session.resource("dynamodb").Table(SESSION_TABLE)


def _ensure_session_table():
    """Create shopsmart-sessions table if it doesn't exist."""
    import boto3
    from botocore.exceptions import ClientError
    session = boto3.Session(
        aws_access_key_id     = _get_secret("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = _get_secret("AWS_SECRET_ACCESS_KEY"),
        region_name           = _get_secret("AWS_REGION") or "eu-north-1",
    )
    dynamodb = session.resource("dynamodb")
    try:
        table = dynamodb.create_table(
            TableName=SESSION_TABLE,
            KeySchema=[{"AttributeName":"session_id","KeyType":"HASH"}],
            AttributeDefinitions=[{"AttributeName":"session_id","AttributeType":"S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        print(f"[Logger] ✅ Created DynamoDB table: {SESSION_TABLE}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            pass  # Table already exists
        else:
            raise


# ── Core helpers ──────────────────────────────────────────────────────────────
def get_session_id() -> str:
    return str(uuid.uuid4())


def _log_path(session_id: str) -> str:
    return os.path.join(LOG_DIR, f"session_{session_id[:8]}.json")


def _empty_log(session_id: str, high_value_customer: bool = False) -> dict:
    return {
        "session_id":          session_id,
        "started_at":          datetime.utcnow().isoformat(),
        "expires_at":          (datetime.utcnow() + timedelta(days=RETENTION_DAYS)).isoformat(),
        "high_value_customer": high_value_customer,
        "turns":               [],
        "peak_frustration":    0.0,
        "handover_triggered":  False,
        "handover_reason":     None,
        "customer_name":       "",
        "customer_id":         "",
        "customer_data":       {},
        "last_updated":        datetime.utcnow().isoformat(),
    }


# ── Load / Save — DynamoDB or local file ─────────────────────────────────────
def _load(session_id: str, high_value_customer: bool = False) -> dict:
    if _aws_configured():
        try:
            table = _get_session_table()
            resp  = table.get_item(Key={"session_id": session_id})
            item  = resp.get("Item")
            if item:
                # DynamoDB stores turns as string — decode if needed
                if isinstance(item.get("turns"), str):
                    item["turns"] = json.loads(item["turns"])
                if "turns" not in item:
                    item["turns"] = []
                return item
        except Exception as e:
            print(f"[Logger] DynamoDB load error: {e} — using local file")

    # Local file fallback
    path = _log_path(session_id)
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
                if "turns" not in data:
                    data["turns"] = []
                return data
        except (json.JSONDecodeError, ValueError):
            os.remove(path)

    return _empty_log(session_id, high_value_customer)


def _save(session_id: str, log: dict):
    log["last_updated"] = datetime.utcnow().isoformat()

    if _aws_configured():
        try:
            import decimal
            table = _get_session_table()
            # DynamoDB can't store floats — convert to Decimal
            item = json.loads(
                json.dumps(log, default=str),
                parse_float=decimal.Decimal
            )
            table.put_item(Item=item)
            return
        except Exception as e:
            print(f"[Logger] DynamoDB save error: {e} — using local file")

    # Local file fallback
    path = _log_path(session_id)
    with open(path, "w") as f:
        json.dump(log, f, indent=2, default=str)


# ── Public API ────────────────────────────────────────────────────────────────
def log_turn(session_id: str, turn_data: dict, high_value_customer: bool = False):
    log = _load(session_id, high_value_customer)
    if "turns" not in log:
        log["turns"] = []

    log["turns"].append({
        "turn_number":        turn_data.get("turn_number", len(log["turns"]) + 1),
        "user_message":       turn_data.get("user_message", ""),
        "frustration_score":  turn_data.get("frustration_score", 0),
        "frustration_level":  turn_data.get("frustration_level", ""),
        "sentiment_score":    turn_data.get("sentiment_score", 0),
        "response_mode":      turn_data.get("response_type", "normal"),
        "bot_response":       turn_data.get("bot_response", ""),
        "handover_triggered": turn_data.get("handover_triggered", False),
        "trend":              turn_data.get("trend", "stable"),
        "timestamp":          datetime.utcnow().isoformat(),
    })

    if turn_data.get("frustration_score", 0) > log.get("peak_frustration", 0):
        log["peak_frustration"] = turn_data["frustration_score"]

    if turn_data.get("handover_triggered"):
        log["handover_triggered"] = True

    log["high_value_customer"] = high_value_customer
    _save(session_id, log)


def log_escalation(session_id: str, bundle: dict = None, reason: str = None,
                   frustration_score: float = None, trend: list = None,
                   last_messages: list = None):
    log = _load(session_id)
    log["handover_triggered"] = True
    if bundle:
        log["handover_reason"]   = bundle.get("escalation_reason", reason or "High frustration")
        log["handover_ref"]      = bundle.get("ref_id", "")
        log["handover_priority"] = bundle.get("priority", "NORMAL")
    else:
        log["handover_reason"]      = reason or "High frustration detected"
        log["handover_frustration"] = frustration_score
        log["handover_trend"]       = trend or []
        log["handover_last_msgs"]   = last_messages or []
    log["handover_at"] = datetime.utcnow().isoformat()
    _save(session_id, log)


def log_session_end(session_id: str, outcome: str = "completed"):
    log = _load(session_id)
    log["ended_at"]    = datetime.utcnow().isoformat()
    log["outcome"]     = outcome
    _save(session_id, log)


def load_session_log(session_id: str) -> dict:
    return _load(session_id)


def end_session(session_id: str, outcome: str = "completed"):
    log_session_end(session_id, outcome)


def load_all_sessions(max_age_mins: int = 120) -> list:
    """Load all sessions — from DynamoDB (deployed) or local files (local dev)."""
    sessions = []

    if _aws_configured():
        try:
            import decimal
            table  = _get_session_table()
            result = table.scan()
            items  = result.get("Items", [])
            # Handle pagination
            while "LastEvaluatedKey" in result:
                result = table.scan(ExclusiveStartKey=result["LastEvaluatedKey"])
                items += result.get("Items", [])

            for item in items:
                if isinstance(item.get("turns"), str):
                    item["turns"] = json.loads(item["turns"])
                if "turns" not in item:
                    item["turns"] = []
                # Filter by age
                ts = item.get("last_updated", "")
                if ts:
                    try:
                        dt  = datetime.fromisoformat(ts)
                        age = (datetime.utcnow() - dt).total_seconds() / 60
                        if age <= max_age_mins:
                            sessions.append(item)
                    except Exception:
                        sessions.append(item)
            return sessions
        except Exception as e:
            print(f"[Logger] DynamoDB scan error: {e} — using local files")

    # Local file fallback
    import glob
    for path in glob.glob(os.path.join(LOG_DIR, "session_*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            if "turns" not in data:
                data["turns"] = []
            ts = data.get("last_updated", "")
            if ts:
                dt  = datetime.fromisoformat(ts)
                age = (datetime.utcnow() - dt).total_seconds() / 60
                if age <= max_age_mins:
                    sessions.append(data)
        except Exception:
            pass
    return sessions


def purge_expired_logs() -> int:
    """Delete logs past 12-month expiry. GDPR FR10."""
    now     = datetime.utcnow()
    deleted = 0
    import glob
    for path in glob.glob(os.path.join(LOG_DIR, "session_*.json")):
        try:
            with open(path) as f:
                log = json.load(f)
            expiry = datetime.fromisoformat(log.get("expires_at","9999-01-01"))
            if now > expiry:
                os.remove(path)
                deleted += 1
        except Exception:
            pass
    return deleted