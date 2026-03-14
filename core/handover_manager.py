# core/handover_manager.py
# Human Handover Mechanism
# When frustration >= threshold or N consecutive high turns detected,
# this module builds a context bundle for the human agent containing:
#   - Last N user messages
#   - Frustration trend
#   - Escalation reason
#   - Session summary
# This prevents customers from repeating themselves (Prentice et al., 2023)

import os
import sys
import uuid
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import FRUSTRATION_HANDOVER_THRESHOLD, CONSECUTIVE_TURNS_FOR_ESCALATION
from utils.logger import log_escalation


class HandoverManager:
    """Manages emotion-based escalation to human agents."""

    # Escalation reasons
    REASON_HIGH_FRUSTRATION = "frustration_threshold_exceeded"
    REASON_TREND_ESCALATION = "consecutive_high_frustration_turns"
    REASON_CRITICAL = "critical_frustration_level"
    REASON_USER_REQUESTED = "user_requested_human"

    def __init__(self):
        self.handover_triggered = False
        self.handover_reason = None
        self.handover_ref = None

    def should_handover(self, frustration_score: float, trend_data: dict,
                        user_message: str) -> tuple:
        """
        Evaluate whether a handover should be triggered.

        Args:
            frustration_score: current turn frustration [0, 1]
            trend_data: dict from TrendTracker.update()
            user_message: current user message (to check for explicit requests)

        Returns:
            (should_handover: bool, reason: str | None)
        """
        # Check for explicit user request
        lowered = user_message.lower()
        explicit_keywords = [
            "speak to a human", "talk to a person", "real person",
            "human agent", "customer service", "speak to someone",
            "agent please", "transfer me", "escalate"
        ]
        if any(kw in lowered for kw in explicit_keywords):
            return True, self.REASON_USER_REQUESTED

        # Critical frustration — only handover if customer stays upset after 2 turns
        # First message: bot tries to calm the customer
        # Second message still critical: then handover
        consecutive = trend_data.get("consecutive_high_turns", 0)

        if frustration_score >= 0.9 and consecutive >= 2:
            return True, self.REASON_CRITICAL

        # Standard threshold — only trigger after 2 consecutive high frustration turns
        # First high-frustration message → bot tries to calm
        # Second high-frustration message → customer still upset → handover
        if frustration_score >= FRUSTRATION_HANDOVER_THRESHOLD and consecutive >= 2:
            return True, self.REASON_HIGH_FRUSTRATION

        # Trend-based escalation
        if trend_data.get("escalate_by_trend", False):
            return True, self.REASON_TREND_ESCALATION

        return False, None

    def build_context_bundle(
        self,
        session_id: str,
        conversation_history: list,
        frustration_score: float,
        trend_summary: dict,
        reason: str
    ) -> dict:
        """
        Build the context bundle passed to the human agent.
        Ensures agents have full context — customers don't repeat themselves.

        Args:
            session_id: anonymized session ID
            conversation_history: list of {'role': 'user'|'bot', 'text': str, 'frustration': float}
            frustration_score: current frustration score
            trend_summary: from TrendTracker.get_summary()
            reason: escalation reason string

        Returns:
            context bundle dict
        """
        ref_id = str(uuid.uuid4())[:8].upper()
        self.handover_triggered = True
        self.handover_reason = reason
        self.handover_ref = ref_id

        # Last 5 messages for agent context
        recent = conversation_history[-5:] if len(conversation_history) >= 5 else conversation_history
        recent_summary = [
            {
                "role": msg.get("role"),
                "text": msg.get("text", ""),
                "frustration": msg.get("frustration", None)
            }
            for msg in recent
        ]

        bundle = {
            "ref_id": ref_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "escalation_reason": reason,
            "escalation_reason_human": _reason_to_human(reason),
            "current_frustration_score": frustration_score,
            "frustration_level": _score_to_level(frustration_score),
            "trend_summary": trend_summary,
            "recent_conversation": recent_summary,
            "agent_note": _generate_agent_note(reason, frustration_score, trend_summary),
            "priority": "HIGH" if frustration_score >= 0.8 else "MEDIUM"
        }

        # Log the escalation event
        log_escalation(
            session_id=session_id,
            reason=reason,
            frustration_score=frustration_score,
            trend=trend_summary.get("scores", []),
            last_messages=[m.get("text", "") for m in recent_summary]
        )

        return bundle

    def format_bundle_for_display(self, bundle: dict) -> str:
        """Format context bundle as readable text for agent dashboard."""
        lines = [
            "=" * 50,
            f"🚨 HANDOVER REQUEST — Ref: {bundle['ref_id']}",
            f"Priority: {bundle['priority']}",
            f"Reason: {bundle['escalation_reason_human']}",
            f"Frustration: {bundle['current_frustration_score']:.2f} ({bundle['frustration_level']})",
            f"Trend: {bundle['trend_summary'].get('trend', 'N/A') if isinstance(bundle.get('trend_summary'), dict) else 'N/A'}",
            "",
            "📋 Agent Note:",
            bundle.get("agent_note", ""),
            "",
            "💬 Recent Conversation:",
        ]
        for msg in bundle.get("recent_conversation", []):
            role = "👤 Customer" if msg["role"] == "user" else "🤖 Bot"
            frust = f" [F:{msg['frustration']:.2f}]" if msg.get("frustration") is not None else ""
            lines.append(f"  {role}{frust}: {msg['text']}")
        lines.append("=" * 50)
        return "\n".join(lines)


def _reason_to_human(reason: str) -> str:
    mapping = {
        "frustration_threshold_exceeded": "Customer frustration exceeded handover threshold (≥0.7)",
        "consecutive_high_frustration_turns": f"Customer frustrated for {CONSECUTIVE_TURNS_FOR_ESCALATION}+ consecutive turns",
        "critical_frustration_level": "Critical frustration level detected (≥0.9)",
        "user_requested_human": "Customer explicitly requested a human agent"
    }
    return mapping.get(reason, reason)


def _score_to_level(score: float) -> str:
    if score >= 0.9:
        return "CRITICAL"
    elif score >= 0.7:
        return "HIGH"
    elif score >= 0.5:
        return "MODERATE"
    else:
        return "LOW"


def _generate_agent_note(reason: str, score: float, trend: dict) -> str:
    """Generate a concise briefing note for the incoming human agent."""
    avg = trend.get("average", score)
    peak = trend.get("peak", score)
    turns = trend.get("total_turns", 0)

    notes = [f"Customer has been in conversation for {turns} turn(s)."]

    if reason == "user_requested_human":
        notes.append("They explicitly asked to speak with a human agent.")
    elif reason == "critical_frustration_level":
        notes.append(f"Frustration reached a critical level ({score:.2f}). Immediate empathy and resolution required.")
    elif reason == "consecutive_high_frustration_turns":
        notes.append(f"Frustration has been persistently high over multiple turns (avg: {avg:.2f}, peak: {peak:.2f}).")
    else:
        notes.append(f"Frustration score: {score:.2f} (avg: {avg:.2f}, peak: {peak:.2f}).")

    notes.append("Full conversation history is available below. Customer should NOT need to repeat information.")
    return " ".join(notes)