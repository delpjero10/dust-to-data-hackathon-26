"""Unit tests for the AI insight over the coverage report (src/ai/insight.py).

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import unittest

from src.ai.insight import ai_insight, build_report_summary
from src.ai.llm import LLMError


def sample_report(**overrides) -> dict:
    report = {
        "map_id": 490880568,
        "map_name": "(unnamed)",
        "distance_m": 0.35,
        "path_span_m": 0.21,
        "distinct_cells_visited": 11,
        "coverage_percent": 91.7,
        "fake_cleaning": False,
        "fake_cleaning_reason": "Short cleaning path (0.3 m travelled) - nothing unusual.",
        "grid": {
            "width": 800,
            "height": 800,
            "free_cells": 7571,
            "unknown_cells": 631652,
            "obstacle_cells": 777,
            "resolution_cm": 5.0,
        },
        "base_station": {"angleX": 43, "x": 1963, "y": 1965},
        "robot_position": {
            "isValid": True,
            "mapId": 490880568,
            "position": {"angleX": 46, "x": 2148, "y": 2079},
        },
    }
    report.update(overrides)
    return report


class FakeLLM:
    def __init__(self, reply: str):
        self._reply = reply
        self.messages = None

    def chat(self, messages, temperature=0.2, max_tokens=300):
        self.messages = messages
        return self._reply


class BuildReportSummaryTest(unittest.TestCase):
    def test_contains_the_key_metrics(self):
        summary = build_report_summary(sample_report())
        self.assertIn("distance_travelled_m: 0.35", summary)
        self.assertIn("coverage_percent_of_swept_area: 91.7", summary)
        self.assertIn("still_unmapped_percent: 98.7", summary)
        self.assertIn("robot_at_base_station: True", summary)

    def test_robot_away_from_base_flagged(self):
        report = sample_report(
            robot_position={"position": {"x": 1963 + 5000, "y": 1965}},
        )
        self.assertIn("robot_at_base_station: False", build_report_summary(report))

    def test_missing_grid_does_not_crash(self):
        report = sample_report(grid={})
        summary = build_report_summary(report)
        self.assertIn("distance_travelled_m", summary)


class AiInsightTest(unittest.TestCase):
    def test_returns_llm_reply(self):
        llm = FakeLLM("The robot barely cleaned - rerun during a real cleaning.")
        text = ai_insight(sample_report(), llm=llm)
        self.assertIn("barely cleaned", text)
        self.assertIn("distance_travelled_m", llm.messages[0]["content"])

    def test_never_raises_when_llm_fails(self):
        llm = FakeLLM("")
        llm.chat = lambda *a, **k: (_ for _ in ()).throw(
            LLMError("LLM endpoint -> 500: boom")
        )
        text = ai_insight(sample_report(), llm=llm)
        self.assertIn("AI insight unavailable", text)


if __name__ == "__main__":
    unittest.main()
