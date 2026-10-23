"""Unit tests for the live device logger (src/ai/live_log.py).

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import unittest

from src.ai import live_log
from src.ai.live_log import LiveLogger

READY = "BSH.Common.EnumType.OperationState.Ready"
RUN = "BSH.Common.EnumType.OperationState.Run"
PAUSE = "BSH.Common.EnumType.OperationState.Pause"
CHARGING = "BSH.Common.EnumType.BatteryChargingState.Charging"
DISCHARGING = "BSH.Common.EnumType.BatteryChargingState.Discharging"


def status(operation, charging=DISCHARGING, battery=90, extra=None) -> list[dict]:
    items = [
        {"key": "BSH.Common.Status.OperationState", "value": operation},
        {"key": "BSH.Common.Status.BatteryChargingState", "value": charging},
        {"key": "BSH.Common.Status.BatteryLevel", "value": battery},
    ]
    for key, value in (extra or {}).items():
        items.append({"key": key, "value": value})
    return items


class LiveLoggerTest(unittest.TestCase):
    def test_first_snapshot_prints_current_state(self):
        logger = LiveLogger()
        lines, event = logger.on_status(status(READY, CHARGING, 90))
        self.assertIsNone(event)
        self.assertEqual(len(lines), 1)
        self.assertIn("ready/idle", lines[0])
        self.assertIn("battery 90%", lines[0])

    def test_cleaning_start_logs_state_change(self):
        logger = LiveLogger()
        logger.on_status(status(READY, DISCHARGING))
        lines, _ = logger.on_status(status(RUN, DISCHARGING))
        self.assertTrue(any("cleaning" in line for line in lines))

    def test_pause_logged(self):
        logger = LiveLogger()
        logger.on_status(status(RUN, DISCHARGING))
        lines, _ = logger.on_status(status(PAUSE, DISCHARGING))
        self.assertTrue(any("paused" in line for line in lines))

    def test_dock_and_leave_logged(self):
        logger = LiveLogger()
        logger.on_status(status(RUN, DISCHARGING))  # cleaning
        lines, _ = logger.on_status(status(READY, CHARGING))  # back at base
        self.assertTrue(any("docked" in line for line in lines))
        lines, _ = logger.on_status(status(READY, DISCHARGING))  # left again
        self.assertTrue(any("left the dock" in line for line in lines))

    def test_battery_change_logged(self):
        logger = LiveLogger()
        logger.on_status(status(READY, DISCHARGING, 90))
        lines, _ = logger.on_status(status(READY, DISCHARGING, 89))
        self.assertTrue(any("battery 89%" in line for line in lines))

    def test_short_dock_run_reports_false_empty_event(self):
        logger = LiveLogger()
        t = 0.0
        logger.on_status(status(RUN, DISCHARGING))
        lines, event = logger.on_status(status(READY, CHARGING))
        self.assertIsNotNone(event)
        self.assertFalse(event.empty_justified)
        self.assertTrue(any("FALSE EMPTY" in line for line in lines))

    def test_idle_snapshots_produce_no_lines(self):
        logger = LiveLogger()
        logger.on_status(status(READY, CHARGING))
        lines, event = logger.on_status(status(READY, CHARGING))
        self.assertIsNone(event)
        self.assertEqual(lines, [])

    def test_extra_status_keys_are_logged(self):
        logger = LiveLogger()
        logger.on_status(status(READY, CHARGING))
        lines, _ =         logger.on_status(status(READY, CHARGING, extra={"BSH.Common.Status.ProgramProgress": 42}))
        self.assertTrue(any("ProgramProgress: 42" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
