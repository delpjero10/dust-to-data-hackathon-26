"""Unit tests for coverage analysis + fake-cleaning detection.

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import base64
import json
import unittest
import zstandard

from src.ai.coverage import (
    analyze_cleaning,
    decode_cleaning_path,
    decode_occupancy_grid,
    distinct_cells,
    fake_cleaning_verdict,
    grid_histogram,
)


def make_zstd_blob(obj) -> str:
    """Encode a JSON object as a URL-safe + Zstandard base64 blob (like the device)."""
    raw = zstandard.ZstdCompressor().compress(json.dumps(obj).encode())
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class DecodeTest(unittest.TestCase):
    def test_occupancy_grid_roundtrip(self):
        grid = [0, 1, 2, 1, 0] * 100
        blob = make_zstd_blob(grid)
        self.assertEqual(decode_occupancy_grid(blob), grid)

    def test_cleaning_path_roundtrip(self):
        path = [{"x": 100.0, "y": 200.0}, {"x": 150, "y": 250}]
        blob = make_zstd_blob(path)
        self.assertEqual(decode_cleaning_path(blob), [(100.0, 200.0), (150.0, 250.0)])

    def test_grid_histogram(self):
        counts = grid_histogram([0, 0, 1, 1, 1, 2])
        self.assertEqual(counts[0], 2)
        self.assertEqual(counts[1], 3)
        self.assertEqual(counts[2], 1)


class CoverageTest(unittest.TestCase):
    def test_full_sweep_high_coverage(self):
        # Sweep across a 2 x 2 m zone (coords in mm), 6 cm rows => dense coverage
        points = []
        step_mm = 50  # 5 cm rows
        for row in range(0, 2001, step_mm):
            for col in range(0, 2001, 50):
                points.append((col, row))
            points.append((2000, row))  # reset edge a bit
        report = analyze_cleaning(None, points, resolution_cm=5)
        self.assertGreaterEqual(report["coverage_percent"], 80.0)
        self.assertFalse(report["fake_cleaning"])

    def test_sparse_zigzag_low_coverage(self):
        # Only a fraction of the bbox's cells are touched (wide rows)
        points = []
        for row in range(0, 2001, 400):
            for col in range(0, 2001, 50):
                points.append((col, row))
        report = analyze_cleaning(None, points, resolution_cm=5)
        self.assertLess(report["coverage_percent"], 50.0)
        self.assertFalse(report["fake_cleaning"])


class FakeCleaningTest(unittest.TestCase):
    def test_circling_in_tiny_spot_is_fake(self):
        # Many orbits around a 0.3 m radius circle -> tens of metres, few distinct
        # cells: cells/m stays tiny even though distance keeps growing.
        import math

        points = [
            (1000 + 300 * math.cos(t), 1000 + 300 * math.sin(t))
            for t in [i * 0.1 for i in range(6000)]
        ]
        fake, reason = fake_cleaning_verdict(points, resolution_cm=5)
        self.assertTrue(fake)
        self.assertIn("FAKE", reason)

    def test_normal_sweep_is_not_fake(self):
        points = []
        for row in range(0, 2001, 100):
            for col in range(0, 2001, 100):
                points.append((col, row))
        fake, _ = fake_cleaning_verdict(points, resolution_cm=5)
        self.assertFalse(fake)

    def test_too_few_points_no_verdict(self):
        fake, reason = fake_cleaning_verdict([(0, 0), (10, 10)], resolution_cm=5)
        self.assertFalse(fake)
        self.assertIn("Not enough", reason)

    def test_distinct_cells_quantization(self):
        cells = distinct_cells([(0, 0), (49, 49), (51, 51)], resolution_cm=5)
        # cells of 50 mm: (0,0) & (49,49) share a cell, (51,51) is in the next one
        self.assertEqual(len(cells), 2)


if __name__ == "__main__":
    unittest.main()
