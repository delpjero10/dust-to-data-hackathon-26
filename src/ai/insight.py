"""Natural-language interpretation of the coverage report (AI layer).

The coverage report (`src/ai/coverage.py`) turns raw device payloads into numbers
(distance, coverage %, cells...). This module sends those metrics to the LLM so the
report ends with a short human sentence: what the robot actually did, whether that is
a problem, and the best next action. It makes the "AI layer" visible in the output
(see docs/architecture.md). Pure wrapper over `src/ai/llm.py` - no device access.
"""

from __future__ import annotations

from .llm import LLMClient, LLMError

INSIGHT_PROMPT = """You interpret live telemetry from a Bosch Spotless BCRD2W robot vacuum.

A sensor report is below. Reply with 2-4 short sentences a normal person would
understand: what the robot actually did, whether that is a problem, and the single
best next action. Do not just echo the numbers - say what they MEAN. If the robot has
barely cleaned yet, say that the measurement is not meaningful and how to get a real
one (start cleaning, then collect during the run).

Report:
{report}"""


def build_report_summary(report: dict) -> str:
    """Condense a coverage report into the numbers the model needs to judge."""
    g = report.get("grid") or {}
    cell_m2 = (g.get("resolution_cm", 5.0) / 100.0) ** 2
    width = g.get("width") or 1
    height = g.get("height") or 1
    total = max(width * height, 1)
    unknown_pct = round((g.get("unknown_cells") or 0) * 100.0 / total, 1)

    pos = (report.get("robot_position") or {}).get("position") or {}
    base = report.get("base_station") or {}
    near_dock = False
    if pos and "x" in base:
        dist = ((pos.get("x", 0) - base.get("x", 0)) ** 2
                + (pos.get("y", 0) - base.get("y", 0)) ** 2) ** 0.5
        near_dock = dist < 1500

    return "\n".join(
        [
            f"- map_id: {report.get('map_id')}",
            f"- distance_travelled_m: {report.get('distance_m')}",
            f"- distinct_spots_cleaned: {report.get('distinct_cells_visited')}",
            f"- area_swept_span_m: {report.get('path_span_m')}",
            f"- coverage_percent_of_swept_area: {report.get('coverage_percent')}",
            f"- floor_mapped_m2: {round((g.get('free_cells') or 0) * cell_m2, 1)}",
            f"- obstacles_m2: {round((g.get('obstacle_cells') or 0) * cell_m2, 1)}",
            f"- still_unmapped_percent: {unknown_pct}",
            f"- fake_cleaning_detected: {bool(report.get('fake_cleaning'))}",
            f"- robot_at_base_station: {near_dock}",
        ]
    )


def ai_insight(report: dict, llm: LLMClient | None = None) -> str:
    """Interpret the coverage report and return a short human verdict.

    Never raises: if the LLM is not configured or fails, it returns a short note so
    the rest of the report still prints.
    """
    try:
        llm = llm or LLMClient()
    except LLMError as exc:
        return f"(AI insight unavailable: {exc})"
    try:
        text = llm.chat(
            [
                {
                    "role": "user",
                    "content": INSIGHT_PROMPT.format(
                        report=build_report_summary(report)
                    ),
                }
            ],
            temperature=0.2,
            max_tokens=300,
        )
    except LLMError as exc:
        return f"(AI insight unavailable: {exc})"
    return text.strip()
