# utils/logger.py
# GDPR-compliant session logger — all functions used across the project

import os
import json
import uuid
from datetime import datetime, timedelta

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

RETENTION_DAYS = 365  # 12 months — GDPR FR10


def get_session_id() -> str:
    return str(uuid.uuid4())


def _log_path(session_id: str) -> str:
    return os.path.join(LOG_DIR, f"session_{session_id[:8]}.json")


def _load_or_create(session_id: str, high_value_customer: bool = False) -> dict:
    path = _log_path(session_id)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            # Corrupted log file — delete and start fresh
            os.remove(path)
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


def _save(session_id: str, log: dict):
    with open(_log_path(session_id), "w") as f:
        json.dump(log, f, indent=2)


def log_turn(session_id: str, turn_data: dict, high_value_customer: bool = False):
    """Append a conversation turn to the session log."""
    log = _load_or_create(session_id, high_value_customer)

    if "turns" not in log:
        log["turns"] = []
    log["turns"].append({
        "turn_number":       turn_data.get("turn_number", len(log["turns"]) + 1),
        "user_message":      turn_data.get("user_message", ""),
        "frustration_score": turn_data.get("frustration_score", 0),
        "frustration_level": turn_data.get("frustration_level", ""),
        "sentiment_score":   turn_data.get("sentiment_score", 0),
        "response_mode":     turn_data.get("response_type", "normal"),
        "bot_response":      turn_data.get("bot_response", ""),
        "handover_triggered":turn_data.get("handover_triggered", False),
        "trend":             turn_data.get("trend", "stable"),
        "timestamp":         datetime.utcnow().isoformat(),
    })

    f_score = turn_data.get("frustration_score", 0)
    if f_score > log.get("peak_frustration", 0):
        log["peak_frustration"] = f_score

    if turn_data.get("handover_triggered"):
        log["handover_triggered"] = True

    log["last_updated"] = datetime.utcnow().isoformat()
    log["high_value_customer"] = high_value_customer
    _save(session_id, log)


def log_escalation(
    session_id: str,
    bundle: dict = None,
    reason: str = None,
    frustration_score: float = None,
    trend: list = None,
    last_messages: list = None
):
    """Log a handover escalation event. Accepts both bundle dict and individual args."""
    log = _load_or_create(session_id)
    log["handover_triggered"] = True

    # Support both calling styles:
    # log_escalation(session_id, bundle=bundle_dict)
    # log_escalation(session_id, reason=reason, frustration_score=score, ...)
    if bundle:
        log["handover_reason"]   = bundle.get("escalation_reason", reason or "High frustration detected")
        log["handover_ref"]      = bundle.get("ref_id", "")
        log["handover_priority"] = bundle.get("priority", "NORMAL")
    else:
        log["handover_reason"]      = reason or "High frustration detected"
        log["handover_frustration"] = frustration_score
        log["handover_trend"]       = trend or []
        log["handover_last_msgs"]   = last_messages or []

    log["handover_at"]   = datetime.utcnow().isoformat()
    log["last_updated"]  = datetime.utcnow().isoformat()
    _save(session_id, log)


def log_session_end(session_id: str, outcome: str = "completed"):
    """Mark session as ended with an outcome."""
    path = _log_path(session_id)
    if not os.path.exists(path):
        return
    with open(path, "r") as f:
        log = json.load(f)
    log["ended_at"] = datetime.utcnow().isoformat()
    log["outcome"] = outcome
    log["last_updated"] = datetime.utcnow().isoformat()
    _save(session_id, log)


def load_session_log(session_id: str) -> dict:
    """Load a session log file."""
    path = _log_path(session_id)
    if not os.path.exists(path):
        return {"turns": [], "session_id": session_id, "expires_at": ""}
    with open(path, "r") as f:
        return json.load(f)


def end_session(session_id: str, outcome: str = "completed"):
    """Alias for log_session_end — kept for compatibility."""
    log_session_end(session_id, outcome)


def purge_expired_logs() -> int:
    """Delete logs past their 12-month expiry. Returns count deleted. GDPR FR10."""
    now = datetime.utcnow()
    deleted = 0
    for filename in os.listdir(LOG_DIR):
        if not filename.endswith(".json"):
            continue
        full_path = os.path.join(LOG_DIR, filename)
        try:
            with open(full_path, "r") as f:
                log = json.load(f)
            expiry = datetime.fromisoformat(log.get("expires_at", "9999-01-01"))
            if now > expiry:
                os.remove(full_path)
                deleted += 1
        except Exception:
            pass
    return deleted