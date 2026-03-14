# evaluation/run_eval.py
# Main evaluation script — §5.4 Participant Study
# Runs all 3 scripted scenarios, collects metrics, generates report
# Run: python evaluation/run_eval.py

import os, sys, time, json, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline import EmotionChatbotPipeline
from evaluation.metrics import (
    TurnRecord, SessionRecord, generate_full_report,
    frustration_recovery_rate, handover_efficiency,
    response_latency_stats, user_satisfaction_summary
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ── §5.4 Scripted Participant Scenarios ──────────────────────────────────────
SCENARIOS = {
    "product_query": {
        "description": "Customer asking about product, escalating when bot can't help",
        "messages": [
            "Hi, I'm looking for a laptop under £800 with good battery life",
            "Does it come with Windows 11 pre-installed?",
            "The bot on the website said it did but now you're saying it doesn't",
            "This is really confusing. I need a straight answer.",
            "I've been asking the same thing for 10 minutes. Can I speak to someone who knows?",
        ]
    },
    "refund_complaint": {
        "description": "Customer requesting refund, becoming frustrated with delays",
        "messages": [
            "Hi, I need to return an item I ordered last week",
            "I already sent it back 5 days ago but haven't received my refund",
            "I have the tracking number - it was delivered to your warehouse on Monday",
            "So where is my refund?? It's been 5 days since you received it!",
            "I want my money back NOW. This is absolutely unacceptable!!",
            "I'm going to dispute this with my bank if I don't hear back TODAY",
        ]
    },
    "delivery_complaint": {
        "description": "Customer with missing delivery, escalating over multiple turns",
        "messages": [
            "My order hasn't arrived yet, it was supposed to come yesterday",
            "The tracking says it's been delivered but I never received it",
            "I was home all day! Nobody knocked or rang the bell.",
            "I've waited 2 weeks for this order and now you're saying it was delivered?!",
            "This is completely unacceptable. I want a replacement or refund IMMEDIATELY",
            "NO I don't want to wait another 5-7 days. I need this sorted TODAY!!",
        ]
    }
}


def run_scenario(scenario_name: str, messages: list, participant_id: str = None) -> SessionRecord:
    """Run one scripted scenario through the pipeline and collect all metrics."""
    pipeline = EmotionChatbotPipeline()
    session = SessionRecord(
        session_id=pipeline.session_id,
        participant_id=participant_id or f"eval_{uuid.uuid4().hex[:6]}",
        scenario=scenario_name
    )

    print(f"\n  Scenario: {scenario_name}")
    print(f"  {'─'*50}")

    for msg in messages:
        start = time.time()
        result = pipeline.process(msg)
        latency_ms = (time.time() - start) * 1000

        f = result.get("frustration", {})
        s = result.get("sentiment", {})
        t = result.get("trend", {})
        r = result.get("response", {})

        turn = TurnRecord(
            turn_number=result.get("turn", 0),
            user_message=msg,
            sentiment_score=s.get("sentiment_score", 0),
            frustration_score=f.get("frustration_score", 0),
            frustration_level=f.get("level", ""),
            response_mode=r.get("mode", "normal"),
            response_latency_ms=round(latency_ms, 1),
            handover_triggered=r.get("trigger_handover", False),
            trend=t.get("trend", "stable")
        )
        session.turns.append(turn)

        f_bar = "█" * int(turn.frustration_score * 20) + "░" * (20 - int(turn.frustration_score * 20))
        print(f"  T{turn.turn_number}: [{f_bar}] {turn.frustration_score:.2f} {turn.frustration_level:10} "
              f"| {turn.response_mode:18} | {latency_ms:.0f}ms")

        if turn.handover_triggered:
            session.handover_triggered = True
            session.handover_turn = turn.turn_number
            print(f"       🚨 HANDOVER TRIGGERED at turn {turn.turn_number}")
            break

    pipeline.end_session("eval_complete")
    return session


def collect_survey_scores(session: SessionRecord) -> SessionRecord:
    """
    Simulate post-conversation survey collection.
    In the real participant study, these come from actual participants.
    Here we use rule-based simulation for automated evaluation.
    """
    # Simulate: lower frustration at end = higher satisfaction
    final_f = session.turns[-1].frustration_score if session.turns else 0.5
    # Scale: frustration 0→1 maps to satisfaction 5→1
    session.satisfaction_score = round(max(1.0, 5.0 - final_f * 4.0), 1)
    # Empathy: higher if empathetic/handover responses were used
    empathy_modes = sum(1 for t in session.turns if "empathetic" in t.response_mode)
    session.perceived_empathy = min(5.0, 2.0 + empathy_modes * 0.8)
    # Trust: penalised if frustrated for many turns without recovery
    high_frustration_turns = sum(1 for t in session.turns if t.frustration_score > 0.7)
    session.trust_score = max(1.0, 4.5 - high_frustration_turns * 0.5)
    session.task_completed = not session.handover_triggered or session.handover_turn == len(session.turns)
    return session


def run_full_evaluation(n_repetitions: int = 1) -> dict:
    """
    Run all 3 scenarios (optionally repeated for robustness).
    Generates the full evaluation report.
    """
    print("\n" + "="*65)
    print("  EVALUATION RUNNER — §5.4 Participant Study Simulation")
    print("="*65)

    all_sessions = []

    for rep in range(n_repetitions):
        print(f"\n[Rep {rep+1}/{n_repetitions}]")
        for name, scenario in SCENARIOS.items():
            session = run_scenario(name, scenario["messages"], participant_id=f"P{rep+1:02d}")
            session = collect_survey_scores(session)
            all_sessions.append(session)

    # Generate report
    report_path = os.path.join(RESULTS_DIR, f"eval_report_{int(time.time())}.json")
    report = generate_full_report(all_sessions, output_path=report_path)

    # Print summary
    print("\n" + "="*65)
    print("  EVALUATION SUMMARY")
    print("="*65)
    frr = report["human_centred"]["frustration_recovery_rate"]
    he  = report["human_centred"]["handover_efficiency"]
    uss = report["human_centred"]["user_satisfaction"]
    lat = report["system_performance"]["response_latency"]

    print(f"  Total Sessions:           {report['total_sessions']}")
    print(f"  Total Turns:              {report['total_turns']}")
    print(f"  Frustration Recovery:     {frr['pct']}% ({frr['recovered_sessions']}/{frr['eligible_sessions']})")
    print(f"  Handover Rate:            {he['handover_pct']}%")
    print(f"  Avg Turn at Handover:     {he['avg_turn_at_handover']}")
    print(f"  Mean Satisfaction:        {uss['satisfaction']['mean']}/5")
    print(f"  Mean Perceived Empathy:   {uss['perceived_empathy']['mean']}/5")
    print(f"  Mean Trust:               {uss['trust_reliability']['mean']}/5")
    if lat:
        print(f"  Avg Response Latency:     {lat['mean_ms']}ms")
        print(f"  Meets <1s Target:         {'✓' if lat['meets_target'] else '✗'}")
    print(f"\n  Full report: {report_path}")
    print("="*65)

    return report


if __name__ == "__main__":
    run_full_evaluation(n_repetitions=1)
