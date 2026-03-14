# aws/alert_manager.py
# Sends email alerts when a customer needs a human agent
# Uses AWS SES (Simple Email Service) — free for first 62,000 emails/month

import os
import json
from datetime import datetime

def _get_secret(key: str) -> str:
    try:
        import streamlit as st
        val = st.secrets.get(key, "")
        if val: return str(val)
    except Exception:
        pass
    return os.getenv(key, "")


def send_handover_alert(
    customer_name: str,
    customer_id: str,
    frustration_score: float,
    session_id: str,
    last_messages: list = None,
    is_vip: bool = False,
    reason: str = "Customer requested human agent"
):
    """
    Send email alert when customer needs human agent.
    Falls back to console log if SES not configured.
    """
    alert_email = _get_secret("ALERT_EMAIL")
    sender_email = _get_secret("SES_SENDER_EMAIL") or alert_email

    if not alert_email:
        print(f"[Alert] ⚠️ No ALERT_EMAIL set — logging to console only")
        _log_alert(customer_name, frustration_score, reason)
        return

    # Build email content
    vip_tag    = "⭐ VIP CUSTOMER — " if is_vip else ""
    frust_pct  = int(frustration_score * 100)
    time_str   = datetime.utcnow().strftime("%d %b %Y at %H:%M UTC")

    # Last 3 messages for context
    msg_html = ""
    if last_messages:
        for msg in last_messages[-3:]:
            role    = msg.get("role","")
            text    = msg.get("text","")
            color   = "#ff6b6b" if role == "user" else "#6c63ff"
            label   = "Customer" if role == "user" else "Aria"
            msg_html += f'<p style="margin:4px 0"><b style="color:{color}">{label}:</b> {text}</p>'

    subject = f"🚨 {vip_tag}Human Agent Needed — {customer_name} (Frustration: {frust_pct}%)"

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f0f1a;color:#e2e8f0;padding:24px;border-radius:12px">
        <h2 style="color:#ff6b6b;margin-top:0">🚨 Human Agent Required</h2>

        <div style="background:#1a1a2e;padding:16px;border-radius:8px;margin-bottom:16px;border-left:4px solid {'#ffd700' if is_vip else '#ff6b6b'}">
            <p style="margin:4px 0"><b>Customer:</b> {customer_name} {'⭐ VIP' if is_vip else ''}</p>
            <p style="margin:4px 0"><b>Customer ID:</b> {customer_id}</p>
            <p style="margin:4px 0"><b>Frustration Level:</b> {frust_pct}%</p>
            <p style="margin:4px 0"><b>Reason:</b> {reason}</p>
            <p style="margin:4px 0"><b>Time:</b> {time_str}</p>
            <p style="margin:4px 0"><b>Session:</b> {session_id[:12]}...</p>
        </div>

        <div style="background:#1a1a2e;padding:16px;border-radius:8px;margin-bottom:16px">
            <h3 style="color:#6c63ff;margin-top:0">Last Messages</h3>
            {msg_html if msg_html else '<p style="color:#888">No message history available</p>'}
        </div>

        <p style="color:#888;font-size:12px">
            ShopSmart Aria Chatbot — Agent Alert System<br>
            This is an automated alert. Please respond to the customer as soon as possible.
        </p>
    </div>
    """

    text_body = f"""
HUMAN AGENT REQUIRED — ShopSmart Aria

Customer: {customer_name} {'(VIP)' if is_vip else ''}
Customer ID: {customer_id}
Frustration: {frust_pct}%
Reason: {reason}
Time: {time_str}
Session: {session_id[:12]}...

Please respond to this customer immediately.
    """

    # Try AWS SES
    if _get_secret("AWS_ACCESS_KEY_ID"):
        try:
            import boto3
            ses = boto3.client(
                "ses",
                aws_access_key_id     = _get_secret("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key = _get_secret("AWS_SECRET_ACCESS_KEY"),
                region_name           = _get_secret("AWS_REGION") or "eu-north-1",
            )
            ses.send_email(
                Source      = sender_email,
                Destination = {"ToAddresses": [alert_email]},
                Message     = {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": text_body, "Charset": "UTF-8"},
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                    },
                },
            )
            print(f"[Alert] ✅ Email sent to {alert_email} for {customer_name}")
            return
        except Exception as e:
            print(f"[Alert] SES error: {e}")

    _log_alert(customer_name, frustration_score, reason)


def _log_alert(name, score, reason):
    print(f"[Alert] 🚨 HANDOVER NEEDED — {name} | Frustration: {int(score*100)}% | {reason}")
