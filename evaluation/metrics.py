# evaluation/metrics.py
# All evaluation metrics from dissertation Chapter 5
# §5.2 System Performance Metrics + §5.3 Human-Centred Experience Metrics

import time
import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TurnRecord:
    """Records all data from a single conversation turn."""
    turn_number: int
    user_message: str
    sentiment_score: float        # [-1, 1]
    frustration_score: float      # [0, 1]
    frustration_level: str        # calm/mild/moderate/high/critical
    response_mode: str            # normal/empathetic_mild/empathetic_high/handover
    response_latency_ms: float    # milliseconds
    handover_triggered: bool
    trend: str                    # rising/stable/falling


@dataclass
class SessionRecord:
    """Complete session data for evaluation."""
    session_id: str
    participant_id: Optional[str]
    scenario: str                 # product_query / refund / delivery_complaint
    turns: List[TurnRecord] = field(default_factory=list)
    handover_triggered: bool = False
    handover_turn: Optional[int] = None
    satisfaction_score: Optional[float] = None      # 1-5 Likert
    perceived_empathy: Optional[float] = None       # 1-5 Likert
    trust_score: Optional[float] = None             # 1-5 Likert
    task_completed: bool = False
    total_duration_seconds: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# §5.2 SYSTEM PERFORMANCE METRICS
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_detection_accuracy(predictions: List[str], ground_truth: List[str]) -> dict:
    """
    FR metric: accuracy of emotion classification vs manually annotated set.
    Args:
        predictions: list of predicted labels ('positive'/'neutral'/'negative')
        ground_truth: list of ground truth labels
    Returns: accuracy, precision, recall, f1
    """
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    acc = accuracy_score(ground_truth, predictions)
    prec = precision_score(ground_truth, predictions, average="macro", zero_division=0)
    rec  = recall_score(ground_truth, predictions, average="macro", zero_division=0)
    f1   = f1_score(ground_truth, predictions, average="macro", zero_division=0)
    return {"accuracy": round(acc,4), "precision": round(prec,4),
            "recall": round(rec,4), "f1_macro": round(f1,4)}


def frustration_score_reliability(scores_run1: List[float], scores_run2: List[float]) -> dict:
    """
    Reliability: variance and correlation between two scoring runs on same inputs.
    Low variance + high correlation = reliable frustration scorer.
    """
    from scipy.stats import pearsonr
    arr1, arr2 = np.array(scores_run1), np.array(scores_run2)
    corr, _ = pearsonr(arr1, arr2)
    mae = float(np.mean(np.abs(arr1 - arr2)))
    var = float(np.var(arr1 - arr2))
    return {"pearson_correlation": round(corr,4), "mae_between_runs": round(mae,4),
            "variance": round(var,6), "reliable": corr > 0.9 and mae < 0.05}


def trend_detection_precision(
    predicted_escalations: List[bool],
    true_escalations: List[bool]
) -> dict:
    """
    Precision/recall for trend-based escalation detection.
    predicted_escalations: list of bool (did system escalate at turn T?)
    true_escalations: list of bool (should it have escalated at turn T?)
    """
    tp = sum(p and t for p,t in zip(predicted_escalations, true_escalations))
    fp = sum(p and not t for p,t in zip(predicted_escalations, true_escalations))
    fn = sum(not p and t for p,t in zip(predicted_escalations, true_escalations))
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": round(precision,4), "recall": round(recall,4),
            "f1": round(f1,4), "true_positives": tp, "false_positives": fp, "false_negatives": fn}


def response_latency_stats(latencies_ms: List[float]) -> dict:
    """
    Response latency analysis. Target: < 1000ms (§5.2).
    latencies_ms: list of response times in milliseconds
    """
    arr = np.array(latencies_ms)
    pct_under_1s = float(np.mean(arr < 1000) * 100)
    return {
        "mean_ms": round(float(np.mean(arr)), 1),
        "median_ms": round(float(np.median(arr)), 1),
        "p95_ms": round(float(np.percentile(arr, 95)), 1),
        "max_ms": round(float(np.max(arr)), 1),
        "pct_under_1000ms": round(pct_under_1s, 1),
        "meets_target": pct_under_1s >= 95.0
    }


def escalation_accuracy(
    system_handovers: List[bool],
    expert_labels: List[bool]
) -> dict:
    """
    Compare system handover decisions against expert-labelled ground truth.
    """
    return trend_detection_precision(system_handovers, expert_labels)


# ─────────────────────────────────────────────────────────────────────────────
# §5.3 HUMAN-CENTRED EXPERIENCE METRICS
# ─────────────────────────────────────────────────────────────────────────────

def frustration_recovery_rate(sessions: List[SessionRecord]) -> dict:
    """
    §5.3 Key metric: measures how often the chatbot successfully reduces frustration.

    FRR = (sessions where frustration decreased after empathetic response)
           / (sessions with frustration >= 0.5)

    Also reports mean frustration delta (positive = improvement).
    """
    eligible = []
    recovered = []

    for s in sessions:
        turns = s.turns
        if len(turns) < 2:
            continue

        peak_f = max(t.frustration_score for t in turns)
        if peak_f < 0.5:
            continue

        eligible.append(s)
        # Check if frustration dropped after peaking
        peak_idx = max(range(len(turns)), key=lambda i: turns[i].frustration_score)
        if peak_idx < len(turns) - 1:
            delta = turns[peak_idx].frustration_score - turns[-1].frustration_score
            if delta > 0.1:   # meaningful reduction
                recovered.append({"session": s.session_id, "delta": delta})

    frr = len(recovered) / len(eligible) if eligible else 0.0
    avg_delta = np.mean([r["delta"] for r in recovered]) if recovered else 0.0

    return {
        "frustration_recovery_rate": round(frr, 4),
        "pct": round(frr * 100, 1),
        "eligible_sessions": len(eligible),
        "recovered_sessions": len(recovered),
        "avg_frustration_reduction": round(float(avg_delta), 4)
    }


def handover_efficiency(sessions: List[SessionRecord]) -> dict:
    """
    §5.3: Measures quality of the human handover mechanism.

    Metrics:
      - handover_rate: % of sessions that triggered handover
      - avg_turn_at_handover: how many turns before escalation
      - early_alert_effectiveness: % where agent was alerted before critical
      - unnecessary_handovers: handovers where frustration was < 0.6
    """
    total = len(sessions)
    handovers = [s for s in sessions if s.handover_triggered]
    handover_rate = len(handovers) / total if total > 0 else 0

    turns_at_handover = [
        s.handover_turn for s in handovers if s.handover_turn is not None
    ]
    avg_turn = np.mean(turns_at_handover) if turns_at_handover else 0

    # Check for unnecessary handovers (peak frustration < 0.6)
    unnecessary = [
        s for s in handovers
        if s.turns and max(t.frustration_score for t in s.turns) < 0.6
    ]

    return {
        "handover_rate": round(handover_rate, 4),
        "handover_pct": round(handover_rate * 100, 1),
        "total_handovers": len(handovers),
        "avg_turn_at_handover": round(float(avg_turn), 1),
        "unnecessary_handovers": len(unnecessary),
        "unnecessary_pct": round(len(unnecessary) / len(handovers) * 100, 1) if handovers else 0
    }


def user_satisfaction_summary(sessions: List[SessionRecord]) -> dict:
    """§5.3: Aggregate post-chat satisfaction survey scores."""
    sat = [s.satisfaction_score for s in sessions if s.satisfaction_score is not None]
    emp = [s.perceived_empathy for s in sessions if s.perceived_empathy is not None]
    trust = [s.trust_score for s in sessions if s.trust_score is not None]

    def stats(arr):
        if not arr: return {"mean": None, "std": None, "n": 0}
        return {"mean": round(float(np.mean(arr)),2), "std": round(float(np.std(arr)),2), "n": len(arr)}

    return {
        "satisfaction": stats(sat),
        "perceived_empathy": stats(emp),
        "trust_reliability": stats(trust),
        "overall_mean": round(float(np.mean(sat + emp + trust)), 2) if (sat or emp or trust) else None
    }


def escalation_frequency_reduction(
    baseline_escalation_rate: float,
    system_escalation_rate: float
) -> dict:
    """
    §5.3: Did the emotion-aware system reduce unnecessary escalations vs baseline?
    baseline_escalation_rate: escalation rate without emotion awareness
    system_escalation_rate: escalation rate with our system
    """
    reduction = baseline_escalation_rate - system_escalation_rate
    pct_reduction = (reduction / baseline_escalation_rate * 100) if baseline_escalation_rate > 0 else 0
    return {
        "baseline_rate": round(baseline_escalation_rate, 4),
        "system_rate": round(system_escalation_rate, 4),
        "absolute_reduction": round(reduction, 4),
        "pct_reduction": round(pct_reduction, 1),
        "improved": reduction > 0
    }


# ─────────────────────────────────────────────────────────────────────────────
# FULL REPORT
# ─────────────────────────────────────────────────────────────────────────────

def generate_full_report(sessions: List[SessionRecord], output_path: str = None) -> dict:
    """
    Generate a complete evaluation report covering all §5.2 and §5.3 metrics.
    Saves to evaluation/results/ as JSON.
    """
    frr  = frustration_recovery_rate(sessions)
    he   = handover_efficiency(sessions)
    uss  = user_satisfaction_summary(sessions)

    # Latency from all turns
    all_latencies = [t.response_latency_ms for s in sessions for t in s.turns]
    latency = response_latency_stats(all_latencies) if all_latencies else {}

    # Frustration score progression across all sessions
    all_frustration = [t.frustration_score for s in sessions for t in s.turns]
    frustration_stats = {
        "mean": round(float(np.mean(all_frustration)), 4) if all_frustration else None,
        "std": round(float(np.std(all_frustration)), 4) if all_frustration else None,
        "peak": round(float(np.max(all_frustration)), 4) if all_frustration else None
    }

    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "total_sessions": len(sessions),
        "total_turns": sum(len(s.turns) for s in sessions),
        "system_performance": {
            "response_latency": latency,
            "frustration_score_stats": frustration_stats
        },
        "human_centred": {
            "frustration_recovery_rate": frr,
            "handover_efficiency": he,
            "user_satisfaction": uss
        }
    }

    if output_path:
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"[Metrics] Report saved to {output_path}")

    return report
