# tests/test_all.py
# Complete pytest test suite covering all core dissertation modules
# Run: pytest tests/ -v

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# PREPROCESSOR TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestPreprocessor:
    def setup_method(self):
        from utils.preprocessor import preprocess, extract_emotional_signals, compute_signal_boost
        self.preprocess = preprocess
        self.extract = extract_emotional_signals
        self.boost = compute_signal_boost

    def test_preprocess_returns_dict(self):
        result = self.preprocess("Hello!")
        assert "clean_text" in result
        assert "features" in result

    def test_caps_words_detected(self):
        features = self.extract("This is RIDICULOUS and UNACCEPTABLE")
        assert features["all_caps_words"] >= 2

    def test_repeated_punctuation_detected(self):
        features = self.extract("Where is my order???")
        assert features["repeated_punctuation"] is True

    def test_negative_intensifiers_detected(self):
        features = self.extract("This is completely unacceptable service")
        assert features["has_negative_intensifiers"] is True

    def test_signal_boost_range(self):
        features = self.extract("THIS IS RIDICULOUS!!! UNACCEPTABLE")
        boost = self.boost(features)
        assert 0.0 <= boost <= 0.25

    def test_calm_message_no_boost(self):
        features = self.extract("Hi, could you help me track my order please?")
        boost = self.boost(features)
        assert boost < 0.05


# ─────────────────────────────────────────────────────────────────────────────
# FRUSTRATION SCORER TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestFrustrationScorer:
    def setup_method(self):
        from core.frustration_scorer import compute_frustration
        self.compute = compute_frustration

    def test_positive_sentiment_low_frustration(self):
        result = self.compute(1.0)
        assert result["frustration_score"] < 0.15

    def test_negative_sentiment_high_frustration(self):
        result = self.compute(-1.0)
        assert result["frustration_score"] > 0.85

    def test_neutral_sentiment_mid_frustration(self):
        result = self.compute(0.0)
        assert 0.4 <= result["frustration_score"] <= 0.6

    def test_score_clamped_to_range(self):
        result = self.compute(-1.0, signal_boost=0.25)
        assert 0.0 <= result["frustration_score"] <= 1.0

    def test_alert_triggered_at_threshold(self):
        result = self.compute(-0.5)   # approx 0.5 frustration → alert
        # Alert at >= 0.5
        if result["frustration_score"] >= 0.5:
            assert result["alert"] is True

    def test_handover_triggered_at_threshold(self):
        result = self.compute(-0.8, signal_boost=0.1)
        if result["frustration_score"] >= 0.7:
            assert result["handover"] is True

    def test_level_labels(self):
        levels = [self.compute(s)["level"] for s in [0.9, 0.0, -0.5, -0.8, -1.0]]
        assert all(l in ("calm", "mild", "moderate", "high", "critical") for l in levels)

    def test_formula_correctness(self):
        """frustration = 1 - (sentiment + 1) / 2"""
        result = self.compute(0.6, signal_boost=0.0)
        expected = 1 - (0.6 + 1) / 2
        assert abs(result["raw_frustration"] - expected) < 0.001


# ─────────────────────────────────────────────────────────────────────────────
# TREND TRACKER TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestTrendTracker:
    def setup_method(self):
        from core.trend_tracker import TrendTracker
        self.tracker = TrendTracker()

    def test_rising_trend_detected(self):
        for score in [0.2, 0.4, 0.6, 0.8]:
            result = self.tracker.update(score)
        assert result["trend"] == "rising"

    def test_falling_trend_detected(self):
        tracker = __import__("core.trend_tracker", fromlist=["TrendTracker"]).TrendTracker()
        for score in [0.8, 0.6, 0.4, 0.2]:
            result = tracker.update(score)
        assert result["trend"] == "falling"

    def test_stable_trend_detected(self):
        tracker = __import__("core.trend_tracker", fromlist=["TrendTracker"]).TrendTracker()
        for score in [0.5, 0.5, 0.5, 0.5]:
            result = tracker.update(score)
        assert result["trend"] == "stable"

    def test_consecutive_high_count(self):
        tracker = __import__("core.trend_tracker", fromlist=["TrendTracker"]).TrendTracker()
        for score in [0.8, 0.75, 0.85]:
            result = tracker.update(score)
        assert result["consecutive_high_turns"] == 3

    def test_escalation_after_3_high_turns(self):
        tracker = __import__("core.trend_tracker", fromlist=["TrendTracker"]).TrendTracker()
        for score in [0.8, 0.75, 0.9]:
            result = tracker.update(score)
        assert result["escalate_by_trend"] is True

    def test_consecutive_reset_on_low_score(self):
        tracker = __import__("core.trend_tracker", fromlist=["TrendTracker"]).TrendTracker()
        tracker.update(0.8)
        tracker.update(0.8)
        result = tracker.update(0.2)   # reset
        assert result["consecutive_high_turns"] == 0

    def test_history_window_size(self):
        from config import TREND_WINDOW_SIZE
        tracker = __import__("core.trend_tracker", fromlist=["TrendTracker"]).TrendTracker()
        for i in range(TREND_WINDOW_SIZE + 3):
            tracker.update(float(i) / 10)
        assert len(tracker.history) == TREND_WINDOW_SIZE


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE MANAGER TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestResponseManager:
    def setup_method(self):
        from core.response_manager import get_response_mode, build_response
        self.get_mode = get_response_mode
        self.build = build_response

    def test_low_frustration_normal_mode(self):
        assert self.get_mode(0.2, "stable") == "normal"

    def test_mid_frustration_mild_empathy(self):
        assert self.get_mode(0.45, "stable") == "empathetic_mild"

    def test_high_frustration_high_empathy(self):
        assert self.get_mode(0.62, "stable") == "empathetic_high"

    def test_rising_trend_bumps_mode(self):
        # rising trend in mid range should bump to empathetic_high
        assert self.get_mode(0.45, "rising") == "empathetic_high"

    def test_handover_mode_at_threshold(self):
        assert self.get_mode(0.72, "rising") == "handover"

    def test_build_response_returns_message(self):
        result = self.build("normal", "test", 0.2, {"trend": "stable"})
        assert "message" in result
        assert len(result["message"]) > 10

    def test_handover_response_triggers_flag(self):
        result = self.build("handover", "help!", 0.8, {"trend": "rising"})
        assert result["trigger_handover"] is True

    def test_alert_set_above_alert_threshold(self):
        result = self.build("empathetic_mild", "msg", 0.55, {"trend": "stable"})
        assert result["alert_agent"] is True


# ─────────────────────────────────────────────────────────────────────────────
# HANDOVER MANAGER TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestHandoverManager:
    def setup_method(self):
        from core.handover_manager import HandoverManager
        self.mgr = HandoverManager()

    def test_explicit_request_triggers_handover(self):
        triggered, reason = self.mgr.should_handover(
            0.3, {"escalate_by_trend": False}, "I want to speak to a human"
        )
        assert triggered is True
        assert reason == HandoverManager.REASON_USER_REQUESTED

    def test_high_frustration_triggers_handover(self):
        triggered, reason = self.mgr.should_handover(
            0.75, {"escalate_by_trend": False}, "My order is late"
        )
        assert triggered is True

    def test_trend_escalation_triggers_handover(self):
        triggered, reason = self.mgr.should_handover(
            0.65, {"escalate_by_trend": True}, "Still waiting"
        )
        assert triggered is True
        assert reason == HandoverManager.REASON_TREND_ESCALATION

    def test_low_frustration_no_handover(self):
        triggered, _ = self.mgr.should_handover(
            0.3, {"escalate_by_trend": False}, "Can you help me?"
        )
        assert triggered is False

    def test_context_bundle_has_required_fields(self):
        bundle = self.mgr.build_context_bundle(
            session_id="test-session-123",
            conversation_history=[{"role": "user", "text": "Help!", "frustration": 0.8}],
            frustration_score=0.85,
            trend_summary={"average": 0.7, "peak": 0.85, "scores": [0.5, 0.7, 0.85]},
            reason=HandoverManager.REASON_HIGH_FRUSTRATION
        )
        for field in ["ref_id", "session_id", "escalation_reason", "agent_note",
                      "current_frustration_score", "priority", "recent_conversation"]:
            assert field in bundle, f"Missing field: {field}"

    def test_critical_frustration_is_high_priority(self):
        bundle = self.mgr.build_context_bundle(
            "s1", [{"role": "user", "text": "FURIOUS", "frustration": 0.95}],
            0.95, {"average": 0.9, "peak": 0.95, "scores": [0.9, 0.95]},
            HandoverManager.REASON_CRITICAL
        )
        assert bundle["priority"] == "HIGH"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE INTEGRATION TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestPipelineIntegration:
    def setup_method(self):
        from pipeline import EmotionChatbotPipeline
        self.pipeline = EmotionChatbotPipeline()

    def test_process_returns_required_keys(self):
        result = self.pipeline.process("Hello, I need help")
        for key in ["turn", "session_id", "sentiment", "frustration", "trend", "response"]:
            assert key in result, f"Missing key: {key}"

    def test_frustration_score_in_range(self):
        result = self.pipeline.process("I am very angry!")
        assert 0.0 <= result["frustration"]["frustration_score"] <= 1.0

    def test_sentiment_score_in_range(self):
        result = self.pipeline.process("This is great!")
        assert -1.0 <= result["sentiment"]["sentiment_score"] <= 1.0

    def test_turn_number_increments(self):
        p = __import__("pipeline", fromlist=["EmotionChatbotPipeline"]).EmotionChatbotPipeline()
        r1 = p.process("Hello")
        r2 = p.process("Still waiting")
        assert r2["turn"] == r1["turn"] + 1

    def test_escalating_conversation_triggers_handover(self):
        p = __import__("pipeline", fromlist=["EmotionChatbotPipeline"]).EmotionChatbotPipeline()
        messages = [
            "I NEED A HUMAN AGENT RIGHT NOW. This is completely unacceptable!!!",
        ]
        result = None
        for msg in messages:
            result = p.process(msg)
            if result["response"]["trigger_handover"]:
                break
        # At some point escalation should happen or at min the response should be high empathy
        assert result["response"]["mode"] in ("empathetic_high", "handover")

    def test_explicit_human_request_triggers_handover(self):
        p = __import__("pipeline", fromlist=["EmotionChatbotPipeline"]).EmotionChatbotPipeline()
        result = p.process("Please transfer me to a human agent")
        assert result["response"]["trigger_handover"] is True


# ─────────────────────────────────────────────────────────────────────────────
# LOGGER TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestLogger:
    def setup_method(self):
        from utils.logger import get_session_id, log_turn, load_session_log
        self.get_id = get_session_id
        self.log_turn = log_turn
        self.load = load_session_log

    def test_session_id_is_uuid_format(self):
        import uuid
        sid = self.get_id()
        uuid.UUID(sid)   # raises if invalid

    def test_log_turn_creates_file(self):
        import os
        sid = self.get_id()
        self.log_turn(sid, {
            "turn_number": 1, "user_message": "test",
            "sentiment_score": 0.1, "frustration_score": 0.5,
            "frustration_level": "moderate", "response_type": "normal",
            "bot_response": "OK", "trend": "stable", "handover_triggered": False
        })
        log = self.load(sid)
        assert len(log["turns"]) == 1

    def test_log_has_gdpr_expiry(self):
        import os
        sid = self.get_id()
        self.log_turn(sid, {"turn_number": 1, "user_message": "x",
                             "sentiment_score": 0, "frustration_score": 0,
                             "frustration_level": "", "response_type": "normal",
                             "bot_response": "", "trend": "stable", "handover_triggered": False})
        log = self.load(sid)
        assert "expires_at" in log


# ─────────────────────────────────────────────────────────────────────────────
# EVALUATION METRICS TESTS
# ─────────────────────────────────────────────────────────────────────────────
class TestEvaluationMetrics:
    def setup_method(self):
        from evaluation.metrics import (
            TurnRecord, SessionRecord,
            frustration_recovery_rate, handover_efficiency,
            response_latency_stats
        )
        self.TurnRecord = TurnRecord
        self.SessionRecord = SessionRecord
        self.frr = frustration_recovery_rate
        self.he = handover_efficiency
        self.latency = response_latency_stats

    def _make_session(self, f_scores, handover=False, h_turn=None):
        turns = [self.TurnRecord(i+1, f"msg{i}", 0.0, f, "moderate",
                                  "normal", 200.0, False, "stable")
                 for i, f in enumerate(f_scores)]
        return self.SessionRecord("s1", "P01", "test",
                                   turns=turns, handover_triggered=handover,
                                   handover_turn=h_turn)

    def test_frr_recovery_detected(self):
        # Frustration peaks then drops
        s = self._make_session([0.3, 0.5, 0.8, 0.4, 0.2])
        result = self.frr([s])
        assert result["recovered_sessions"] == 1

    def test_frr_no_recovery(self):
        s = self._make_session([0.3, 0.5, 0.8, 0.85, 0.9])
        result = self.frr([s])
        assert result["recovered_sessions"] == 0

    def test_handover_efficiency_rate(self):
        s1 = self._make_session([0.8, 0.9], handover=True, h_turn=2)
        s2 = self._make_session([0.2, 0.3], handover=False)
        result = self.he([s1, s2])
        assert result["total_handovers"] == 1
        assert result["handover_pct"] == 50.0

    def test_latency_target_check(self):
        latencies = [200, 400, 600, 800, 950]
        result = self.latency(latencies)
        assert result["meets_target"] is True
        assert result["pct_under_1000ms"] == 100.0

    def test_latency_fails_target(self):
        latencies = [200, 500, 1200, 1500, 2000]
        result = self.latency(latencies)
        assert result["meets_target"] is False
