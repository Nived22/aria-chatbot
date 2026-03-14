# core/trend_tracker.py
# Tracks frustration scores across conversation turns
# Detects escalation patterns: N consecutive high-frustration turns → trigger handover
# Also computes trend direction (rising / stable / falling)

import os
import sys
from collections import deque
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    CONSECUTIVE_TURNS_FOR_ESCALATION,
    TREND_WINDOW_SIZE,
    FRUSTRATION_HANDOVER_THRESHOLD,
    FRUSTRATION_ALERT_THRESHOLD
)


class TrendTracker:
    """
    Stateful multi-turn frustration trend tracker.
    One instance per conversation session.
    """

    def __init__(self):
        self.history: deque = deque(maxlen=TREND_WINDOW_SIZE)
        self.consecutive_high: int = 0
        self.turn_count: int = 0

    def update(self, frustration_score: float) -> dict:
        """
        Record a new frustration score and evaluate the current trend.

        Args:
            frustration_score: float [0, 1] from frustration_scorer

        Returns:
            dict with:
                - 'trend': 'rising' | 'stable' | 'falling'
                - 'trend_slope': float — average change per turn
                - 'consecutive_high_turns': int
                - 'escalate_by_trend': bool — N consecutive high turns reached
                - 'history': list of recent scores
                - 'average': float — mean of recent window
        """
        self.turn_count += 1
        self.history.append(frustration_score)

        # Track consecutive high-frustration turns
        if frustration_score >= FRUSTRATION_HANDOVER_THRESHOLD:
            self.consecutive_high += 1
        else:
            self.consecutive_high = 0

        trend, slope = self._compute_trend()
        escalate_by_trend = self.consecutive_high >= CONSECUTIVE_TURNS_FOR_ESCALATION

        return {
            "trend": trend,
            "trend_slope": round(slope, 4),
            "consecutive_high_turns": self.consecutive_high,
            "escalate_by_trend": escalate_by_trend,
            "history": list(self.history),
            "average": round(sum(self.history) / len(self.history), 4),
            "turn_count": self.turn_count
        }

    def _compute_trend(self) -> tuple:
        """
        Compute trend direction from recent history.

        Returns:
            (trend_label: str, slope: float)
        """
        scores = list(self.history)
        n = len(scores)

        if n < 2:
            return "stable", 0.0

        # Simple linear slope across window
        # slope = (last - first) / n
        slope = (scores[-1] - scores[0]) / n

        if slope > 0.05:
            return "rising", slope
        elif slope < -0.05:
            return "falling", slope
        else:
            return "stable", slope

    def get_summary(self) -> dict:
        """Return a summary of the full trend history for handover context bundle."""
        if not self.history:
            return {}
        scores = list(self.history)
        return {
            "scores": scores,
            "average": round(sum(scores) / len(scores), 4),
            "peak": round(max(scores), 4),
            "final": round(scores[-1], 4),
            "consecutive_high_turns": self.consecutive_high,
            "total_turns": self.turn_count
        }

    def reset(self):
        """Reset tracker (new session)."""
        self.history.clear()
        self.consecutive_high = 0
        self.turn_count = 0
