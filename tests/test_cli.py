"""Unit tests for CLI helpers (src/cli.py).

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import unittest

from src.cli import is_docked

READY = "BSH.Common.EnumType.OperationState.Ready"
CHARGING = "BSH.Common.EnumType.BatteryChargingState.Charging"
DISCHARGING = "BSH.Common.EnumType.BatteryChargingState.Discharging"


class FakeClient:
    def __init__(self, operation, charging):
        self._status = [
            {"key": "BSH.Common.Status.OperationState", "value": operation},
            {"key": "BSH.Common.Status.BatteryChargingState", "value": charging},
        ]

    def get_status(self, ha_id):
        return self._status


class IsDockedTest(unittest.TestCase):
    def test_docked_is_true_when_ready_and_charging(self):
        self.assertTrue(is_docked(FakeClient(READY, CHARGING), "1"))

    def test_off_dock_idle_is_false(self):
        self.assertFalse(is_docked(FakeClient(READY, DISCHARGING), "1"))

    def test_cleaning_is_false(self):
        self.assertFalse(is_docked(FakeClient("BSH.Common.EnumType.OperationState.Run", DISCHARGING), "1"))


if __name__ == "__main__":
    unittest.main()
