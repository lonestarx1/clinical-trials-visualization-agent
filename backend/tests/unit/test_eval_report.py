"""The eval report: one table per stage, bars marked, the Q20 choice named."""

from evals.report import render

RESULT = {
    "label": "baseline",
    "date": "2026-10-25",
    "runs_per_case": 3,
    "cases": {"guard": 2},
    "stages": {
        "guard": {
            "gpt-5.4-nano:low": {
                "summary": {
                    "runs": 6,
                    "malicious_recall": 1.0,
                    "false_positive_rate": 0.0,
                    "off_topic_accuracy": 1.0,
                    "p50_ms": 700,
                    "p95_ms": 1200,
                    "cost_per_call": 0.00005,
                    "missed": [],
                    "false_positives": [],
                    "bars": {"malicious recall = 100%": True, "p95 <= 3 s": True},
                },
                "total_cost_usd": 0.0003,
            }
        }
    },
}


def test_the_report_has_a_row_per_candidate_and_names_the_choice() -> None:
    text = render(RESULT)
    assert "# AI evaluation: baseline" in text
    assert "## Guard" in text
    assert "| gpt-5.4-nano:low | 100% | 0% | 100% | 0.70 s | 1.20 s | $0.000050 | pass |" in text
    assert "Choice by the Q20 rule: **gpt-5.4-nano:low**" in text
