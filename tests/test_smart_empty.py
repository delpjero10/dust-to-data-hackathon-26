"""Unit tests for the real-time false-empty detection (src/ai/smart_empty.py).

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import unittest

from src.ai.smart_empty import EmptyMonitor

READY = "BSH.Common.EnumType.OperationState.Ready"
RUN = "BSH.Common.EnumType.OperationState.Run"
CHARGING = "BSH.Common.EnumType.BatteryChargingState.Charging"
DISCHARGING = "BSH.Common.EnumType.BatteryChargingState.Discharging"


def status(operation: str, charging: str) -> list[dict]:
    return [
        {"key": "BSH.Common.Status.OperationState", "value": operation},
        {"key": "BSH.Common.Status.BatteryChargingState", "value": charging},
    ]


class EmptyMonitorTest(unittest.TestCase):
    def test_idle_at_dock_produces_no_event(self):
        monitor = EmptyMonitor(min_seconds=120)
        event = monitor.on_status(status(READY, CHARGING), now=0)
        self.assertIsNone(event)
        self.assertFalse(monitor.session_active)

    def test_short_session_docking_is_false_empty(self):
        monitor = EmptyMonitor(min_seconds=120)
        t = 0.0
        self.assertIsNone(monitor.on_status(status(READY, CHARGING), now=t))  # idle
        self.assertIsNone(monitor.on_status(status(RUN, DISCHARGING), now=t))  # starts
        self.assertTrue(monitor.session_active)
        # clean for 30 s, then return to base 5 s later
        self.assertIsNone(monitor.on_status(status(RUN, DISCHARGING), now=t + 30))
        event = monitor.on_status(status(READY, CHARGING), now=t + 35)
        self.assertIsNotNone(event)
        self.assertFalse(event.empty_justified)
        self.assertAlmostEqual(event.cleaning_seconds, 35)
        self.assertEqual(event.min_clean_seconds, 120)
        self.assertFalse(monitor.session_active)  # state reset after docking

    def test_long_session_docking_is_justified(self):
        monitor = EmptyMonitor(min_seconds=120)
        t = 0.0
        monitor.on_status(status(RUN, DISCHARGING), now=t)
        event = monitor.on_status(status(READY, CHARGING), now=t + 150)
        self.assertIsNotNone(event)
        self.assertTrue(event.empty_justified)
        self.assertAlmostEqual(event.cleaning_seconds, 150)

    def test_stop_then_go_home_still_counts_as_one_session(self):
        """A stop (Ready/Discharging) keeps the session open until the robot docks."""
        monitor = EmptyMonitor(min_seconds=120)
        t = 0.0
        monitor.on_status(status(RUN, DISCHARGING), now=t)  # cleaning starts
        monitor.on_status(status(RUN, DISCHARGING), now=t + 60)
        monitor.on_status(status(READY, DISCHARGING), now=t + 60)  # user stops
        self.assertTrue(monitor.session_active)
        monitor.on_status(status(RUN, DISCHARGING), now=t + 70)  # GoHome travel
        event = monitor.on_status(status(READY, CHARGING), now=t + 100)  # docked
        self.assertIsNotNone(event)
        self.assertFalse(event.empty_justified)
        self.assertAlmostEqual(event.cleaning_seconds, 100)

    def test_resume_after_dock_starts_fresh_session(self):
        monitor = EmptyMonitor(min_seconds=120)
        t = 0.0
        monitor.on_status(status(RUN, DISCHARGING), now=t)
        monitor.on_status(status(READY, CHARGING), now=t + 10)  # docked => event
        self.assertFalse(monitor.session_active)
        monitor.on_status(status(RUN, DISCHARGING), now=t + 1000)  # new session
        # no event on the transient Ready/Discharging read just before docking
        self.assertIsNone(monitor.on_status(status(READY, DISCHARGING), now=t + 1010))
        event = monitor.on_status(status(READY, CHARGING), now=t + 1010)
        self.assertIsNotNone(event)
        self.assertAlmostEqual(event.cleaning_seconds, 10)


if __name__ == "__main__":
    unittest.main()
