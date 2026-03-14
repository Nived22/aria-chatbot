

# core/response_manager.py
# Response manager — simplified now that Claude handles all content and tone
# Main job: handle handover messages and pass Claude's reply through cleanly

import os
import re
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    FRUSTRATION_HANDOVER_THRESHOLD,
    FRUSTRATION_ALERT_THRESHOLD,
    EMPATHY_SCORE_TRIGGER,
    SIMPLIFY_LANGUAGE_TRIGGER
)

# Handover messages — still template-based since these are structural, not conversational
_HANDOVER_INTROS = [
    "I want to make sure this gets sorted properly, so I'm connecting you with one of our team right now. They'll have full context of everything we've talked about — you won't need to repeat yourself.",
    "You deserve proper help with this, so I'm getting a real person on the line for you now. They're fully briefed.",
    "I'm handing this over to one of our team who can take direct action. They'll know everything already.",
    "Let me get you to someone who can actually fix this right now — they'll have all the details.",
]

_HANDOVER_QUEUED = [
    "All our agents are helping other customers right now, but I've flagged you as priority — someone will be with you in under 15 minutes. Your reference is {ref_id}.",
    "Our team is briefly at capacity but you're next in the queue. Expected wait: under 10 minutes. Ref: {ref_id}.",
    "I've marked this as urgent — an agent will reach out very shortly. Your case ref is {ref_id}.",
]


def get_response_mode(frustration_score: float, trend: str) -> str:
    """Determine response mode — still needed for UI indicators and logging."""
    if frustration_score >= FRUSTRATION_HANDOVER_THRESHOLD:
        return "handover"
    elif frustration_score >= SIMPLIFY_LANGUAGE_TRIGGER:
        return "empathetic_high"
    elif frustration_score >= EMPATHY_SCORE_TRIGGER:
        return "empathetic_high" if trend == "rising" else "empathetic_mild"
    else:
        return "normal"


def build_response(
    mode: str,
    user_message: str,
    frustration_score: float,
    trend_data: dict,
    task_response: str = None,
    ref_id: str = None
) -> dict:
    """
    Build the final response dict.

    - Handover: uses handover template (structural message)
    - Everything else: uses Claude's reply from task_response directly
    - Fallback: only if Claude was unavailable
    """
    alert_agent      = frustration_score >= FRUSTRATION_ALERT_THRESHOLD
    trigger_handover = mode == "handover"

    # ── Handover — always use our own message, not Claude's ───────────────────
    if mode == "handover":
        intro = random.choice(_HANDOVER_INTROS)
        if ref_id:
            queued  = random.choice(_HANDOVER_QUEUED).replace("{ref_id}", ref_id)
            message = f"{intro}\n\n{queued}"
        else:
            message = intro

    # ── Claude's reply — use it directly, no wrapping needed ─────────────────
    elif task_response:
        message = task_response

    # ── Emergency fallback — Claude was unavailable ───────────────────────────
    else:
        if frustration_score >= 0.65:
            message = "I'm really sorry about this. Could you give me your order number and I'll look into it immediately?"
        elif frustration_score >= 0.40:
            message = "I'm sorry to hear that — let me help. Could you share your order number?"
        else:
            message = "Happy to help! What do you need?"

    return {
        "mode":               mode,
        "message":            message,
        "show_empathy_prefix": mode in ("empathetic_mild", "empathetic_high", "handover"),
        "alert_agent":        alert_agent,
        "trigger_handover":   trigger_handover,
        "frustration_score":  frustration_score,
        "trend":              trend_data.get("trend", "stable")
    }


def format_debug_info(analysis: dict) -> str:
    f = analysis.get("frustration", {})
    s = analysis.get("sentiment",  {})
    t = analysis.get("trend",      {})
    return "\n".join([
        f"🎭 Sentiment:    {s.get('sentiment_score', 0):+.3f}  [{s.get('roberta_label', '?')}]",
        f"😤 Frustration:  {f.get('frustration_score', 0):.3f}  [{f.get('level', '?')}]",
        f"📈 Trend:        {t.get('trend', '?')} (slope {t.get('trend_slope', 0):+.3f})",
        f"🔁 Consec. high: {t.get('consecutive_high_turns', 0)} turn(s)",
        f"⚡ Signal boost: +{s.get('signal_boost', 0):.3f}",
    ])