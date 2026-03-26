# pipeline.py
# Main emotion-aware chatbot pipeline
# Orchestrates: preprocessing → sentiment → frustration → trend → response → handover
# This is the single entry point used by both the Streamlit UI and any test scripts.

import os
try:
    from dotenv import load_dotenv
    load_dotenv()  # Loads .env file automatically
except ImportError:
    pass
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.sentiment_engine import analyse
from core.frustration_scorer import compute_frustration
from core.trend_tracker import TrendTracker
from core.response_manager import get_response_mode, build_response, format_debug_info
from core.intent_engine import get_contextual_reply, detect_intent
from core.handover_manager import HandoverManager
try:
    from aws.alert_manager import send_handover_alert
    _alerts_available = True
except ImportError:
    _alerts_available = False
from utils.logger import get_session_id, log_turn, log_session_end, purge_expired_logs
from utils.input_validator import validate_input
from config import BOT_NAME, COMPANY_NAME


class EmotionChatbotPipeline:
    """
    Full end-to-end emotion-aware chatbot pipeline.
    One instance per conversation session.

    Usage:
        pipeline = EmotionChatbotPipeline()
        result = pipeline.process("My order still hasn't arrived!")
        print(result['response']['message'])
    """

    def __init__(self):
        self.session_id = get_session_id()
        self.trend_tracker = TrendTracker()
        self.handover_manager = HandoverManager()
        self._customer_data = {}
        self._alert_sent = False

        # FIX: initialise here so they always exist before process() is called
        self.conversation_history = []
        self.turn_number = 0
        self.is_handed_over = False

        # Run GDPR cleanup on startup
        deleted = purge_expired_logs()
        if deleted > 0:
            print(f"[Pipeline] Purged {deleted} expired log file(s).")

        # FIX: warm up RoBERTa model now so first user message is fast
        try:
            from models.model_loader import load_model
            load_model()
            print("[Pipeline] Model warmed up ✓")
        except Exception as e:
            print(f"[Pipeline] Model warmup skipped: {e}")

        print(f"[Pipeline] Session started: {self.session_id}")

    @property
    def customer_data(self):
        return self._customer_data

    @customer_data.setter
    def customer_data(self, value):
        self._customer_data = value or {}
        if self._customer_data:
            self._write_customer_to_log(self._customer_data)

    def _write_customer_to_log(self, customer_data: dict):
        """Write customer info into log immediately so backend can display it."""
        log_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "logs",
            f"session_{self.session_id[:8]}.json"
        )
        try:
            import json as _json
            from datetime import datetime as _dt
            log = {"turns": [], "session_id": self.session_id,
                   "started_at": _dt.utcnow().isoformat(),
                   "peak_frustration": 0.0, "handover_triggered": False}
            if os.path.exists(log_path):
                try:
                    with open(log_path) as _f:
                        log = _json.load(_f)
                except Exception:
                    pass
            if "turns" not in log:
                log["turns"] = []
            log["customer_data"]       = customer_data
            log["customer_name"]       = customer_data.get("name", "Unknown")
            log["customer_id"]         = customer_data.get("customer_id", "")
            log["high_value_customer"] = customer_data.get("is_vip", False)
            log["last_updated"]        = _dt.utcnow().isoformat()
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w") as _f:
                _json.dump(log, _f, indent=2)
        except Exception as e:
            print(f"[Pipeline] Log write error: {e}")

    def process(self, user_message: str, task_response: str = None, customer_data: dict = None) -> dict:
        """
        Process a single user message through the full pipeline.

        Args:
            user_message: raw text from the user
            task_response: optional string with task-specific content
                           (e.g., order status retrieved from a backend system)

        Returns:
            Full analysis dict:
            {
                'turn': int,
                'session_id': str,
                'sentiment': {...},
                'frustration': {...},
                'trend': {...},
                'response': {
                    'mode': str,
                    'message': str,
                    'alert_agent': bool,
                    'trigger_handover': bool
                },
                'handover_bundle': dict | None,
                'debug': str
            }
        """
        if self.is_handed_over:
            return self._post_handover_message()

        # ── Input validation — catch gibberish before NLP ───────────────────
        validation = validate_input(user_message)
        if not validation["valid"]:
            return self._invalid_input_response(validation["reply"])

        self.turn_number += 1
        if customer_data:
            self.customer_data = customer_data  # property setter writes to log automatically

        # ── Step 1: Sentiment Analysis ──────────────────────────────────────────
        sentiment = analyse(user_message)

        # ── Step 2: Frustration Scoring ─────────────────────────────────────────
        frustration = compute_frustration(
            sentiment_score=sentiment["sentiment_score"],
            signal_boost=sentiment["signal_boost"]
        )

        # ── Step 3: Trend Tracking ──────────────────────────────────────────────
        trend = self.trend_tracker.update(frustration["frustration_score"])

        # ── Step 4: Check for Handover ──────────────────────────────────────────
        should_handover, handover_reason = self.handover_manager.should_handover(
            frustration_score=frustration["frustration_score"],
            trend_data=trend,
            user_message=user_message
        )

        # ── Step 4b: Detect intent ─────────────────────────────────────────────
        intent = detect_intent(user_message)

        # ── Step 4c: Append user turn to history BEFORE calling Claude ─────────
        # This means Claude sees the full conversation including the current message
        self.conversation_history.append({
            "role": "user",
            "text": user_message,
            "frustration": frustration["frustration_score"],
            "intent": intent,
            "turn": self.turn_number
        })

        contextual_reply = get_contextual_reply(
            message=user_message,
            frustration_score=frustration["frustration_score"],
            conversation_history=self.conversation_history,
            customer_data=getattr(self, "customer_data", None),
            intent=intent,
        )

        # ── Step 5: Determine Response Mode ────────────────────────────────────
        if should_handover:
            mode = "handover"
            self.is_handed_over = True
        else:
            mode = get_response_mode(frustration["frustration_score"], trend["trend"])

        # ── Step 6: Build Response ──────────────────────────────────────────────
        response = build_response(
            mode=mode,
            user_message=user_message,
            frustration_score=frustration["frustration_score"],
            trend_data=trend,
            task_response=contextual_reply,  # Never pass raw hv_task — only Claude's reply
            ref_id=self.handover_manager.handover_ref
        )

        # ── Step 7: Build Handover Bundle (if needed) ───────────────────────────
        handover_bundle = None
        if should_handover:
            handover_bundle = self.handover_manager.build_context_bundle(
                session_id=self.session_id,
                conversation_history=self.conversation_history,
                frustration_score=frustration["frustration_score"],
                trend_summary=self.trend_tracker.get_summary(),
                reason=handover_reason
            )
            # ── Send email alert ─────────────────────────────────────────────
            if _alerts_available and not getattr(self, "_alert_sent", False):
                try:
                    cdata = getattr(self, "_customer_data", {}) or {}
                    send_handover_alert(
                        customer_name    = cdata.get("name", "Unknown Customer"),
                        customer_id      = cdata.get("customer_id", ""),
                        frustration_score= frustration["frustration_score"],
                        session_id       = self.session_id,
                        last_messages    = self.conversation_history[-6:],
                        is_vip           = cdata.get("is_vip", False),
                        reason           = handover_reason or "High frustration detected",
                    )
                    self._alert_sent = True  # Only send once per session
                except Exception as e:
                    print(f"[Pipeline] Alert error: {e}")

        # ── Step 8: Log Turn ────────────────────────────────────────────────────
        # user turn already appended at Step 4c — only append bot reply here
        self.conversation_history.append({
            "role": "bot",
            "text": response["message"],
            "frustration": None,
            "turn": self.turn_number
        })

        log_turn(self.session_id, {
            "turn_number": self.turn_number,
            "user_message": user_message,
            "sentiment_score": sentiment["sentiment_score"],
            "frustration_score": frustration["frustration_score"],
            "frustration_level": frustration["level"],
            "response_type": mode,
            "bot_response": response["message"],
            "trend": trend["trend"],
            "handover_triggered": should_handover
        })

        # ── Build final result ──────────────────────────────────────────────────
        result = {
            "turn": self.turn_number,
            "session_id": self.session_id,
            "sentiment": sentiment,
            "frustration": frustration,
            "trend": trend,
            "response": response,
            "handover_bundle": handover_bundle,
            "debug": format_debug_info({
                "sentiment": sentiment,
                "frustration": frustration,
                "trend": trend
            })
        }

        return result

    def end_session(self, status: str = "resolved"):
        """End the session and finalise logs."""
        log_session_end(self.session_id, status)
        print(f"[Pipeline] Session {self.session_id} ended with status: {status}")

    def _invalid_input_response(self, reply: str) -> dict:
        """Return a gentle clarification response for invalid/gibberish input."""
        return {
            "turn": self.turn_number,
            "session_id": self.session_id,
            "sentiment": {"sentiment_score": 0, "signal_boost": 0, "roberta_label": "neutral"},
            "frustration": {"frustration_score": 0, "level": "calm", "alert": False, "handover": False},
            "trend": {"trend": "stable", "trend_slope": 0, "consecutive_high_turns": 0},
            "response": {
                "mode": "normal",
                "message": reply or "I didn't quite understand that. Could you rephrase?",
                "alert_agent": False,
                "trigger_handover": False,
                "frustration_score": 0,
                "trend": "stable"
            },
            "handover_bundle": None,
            "debug": "Input validation failed — skipped NLP pipeline"
        }

    def _post_handover_message(self) -> dict:
        """Return a holding message if user messages after handover."""
        return {
            "turn": self.turn_number,
            "session_id": self.session_id,
            "response": {
                "mode": "handover",
                "message": (
                    f"You're currently in the queue to speak with a {COMPANY_NAME} specialist. "
                    f"They'll have your full conversation history and will be with you shortly. "
                    f"Reference: {self.handover_manager.handover_ref}"
                ),
                "alert_agent": True,
                "trigger_handover": True
            },
            "handover_bundle": None
        }


# ── CLI Demo ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  {BOT_NAME} — Emotion-Aware Chatbot  |  {COMPANY_NAME}")
    print(f"{'='*60}")
    print("Type 'quit' to exit | 'debug' to toggle debug info\n")

    pipeline = EmotionChatbotPipeline()
    show_debug = False

    # Warm up the model
    print(f"[{BOT_NAME}] Hello! I'm {BOT_NAME}, your {COMPANY_NAME} assistant. How can I help you today?\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "debug":
            show_debug = not show_debug
            print(f"[Debug mode: {'ON' if show_debug else 'OFF'}]\n")
            continue

        result = pipeline.process(user_input)

        if show_debug:
            print(f"\n── Debug ──────────────────────────────────")
            print(result["debug"])
            print(f"──────────────────────────────────────────\n")

        print(f"\n[{BOT_NAME}]: {result['response']['message']}\n")

        if result["response"].get("alert_agent") and not result["response"].get("trigger_handover"):
            print(f"  [⚠️  Agent alert: frustration rising — agent on standby]\n")

        if result.get("handover_bundle"):
            print("\n" + pipeline.handover_manager.format_bundle_for_display(result["handover_bundle"]))

    pipeline.end_session()
    print(f"\nSession ended. Goodbye!")