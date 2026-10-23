"""Unit tests for obstacle-loop detection + auto-recovery planning.

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import math
import unittest

from src.ai.obstacle import (
    analyze_obstacles,
    count_reversals,
    window_stuck_analysis,
)


class ReversalTest(unittest.TestCase):
    def test_oscillation_counts_many_reversals(self):
        # back-and-forth on a 0.3 m line -> direction flips every point
        pts = []
        for i in range(20):
            pts.append((1000, 1000 + (300 if i % 2 else 0)))
        self.assertGreaterEqual(count_reversals(pts), 15)

    def test_straight_line_no_reversals(self):
        pts = [(0 + i * 100, 0) for i in range(20)]
        self.assertEqual(count_reversals(pts), 0)


class StuckWindowTest(unittest.TestCase):
    def test_oscillation_within_small_radius_is_stuck(self):
        pts = []
        for i in range(40):
            pts.append((1000, 1000 + (335 if i % 2 else 0)))  # 0.34 m span, lots of motion
        report = window_stuck_analysis(pts)
        self.assertTrue(report["stuck"])
        self.assertGreaterEqual(report["hits"], 3)
        self.assertIn("STUCK", report["reason"])

    def test_normal_sweep_is_not_stuck(self):
        # classic lawnmower sweep: the most recent points span the whole room
        pts = []
        for row in range(0, 2001, 50):
            for col in range(0, 2001, 50):
                pts.append((col, row))
        report = window_stuck_analysis(pts)
        self.assertFalse(report["stuck"])

    def test_too_few_points_no_verdict(self):
        pts = [(i * 10, 0) for i in range(5)]
        report = window_stuck_analysis(pts)
        self.assertFalse(report["stuck"])
        self.assertIn("Not enough", report["reason"])


class AnalyzeTest(unittest.TestCase):
    def test_problem_sets_recovery_steps(self):
        pts = []
        for i in range(40):
            pts.append((1000, 1000 + (335 if i % 2 else 0)))
        report = analyze_obstacles(pts)
        self.assertTrue(report["problem"])
        self.assertEqual(
            report["recovery_steps"], ["stop", "go_home", "wait_until_docked", "restart_cleaning"]
        )
        self.assertIn("Rolling back", report["recommendation"])

    def test_clean_path_no_problem(self):
        pts = [(0 + i * 100, 0) for i in range(40)]
        report = analyze_obstacles(pts)
        self.assertFalse(report["problem"])
        self.assertEqual(report["recovery_steps"], [])

    def test_large_circle_is_not_flagged_as_obstacle_loop(self):
        # wide circling spans the room -> that's normal manoeuvring, not a stuck spot
        pts = [
            (1000 + 1000 * math.cos(t), 1000 + 1000 * math.sin(t))
            for t in [i * 0.01 for i in range(60)]
        ]
        report = analyze_obstacles(pts)
        self.assertFalse(report["problem"])


if __name__ == "__main__":
    unittest.main()
