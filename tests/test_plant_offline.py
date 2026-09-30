"""Regression tests for plant offline detection.

Run from the repo root:
    python tests/test_plant_offline.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "saj_esolar_air"


def _load_component_module(name: str, filename: str):
    """Load a component module without importing Home Assistant via __init__."""
    package = sys.modules.get("saj_esolar_air")
    if package is None:
        package = types.ModuleType("saj_esolar_air")
        package.__path__ = [str(_COMPONENT)]
        sys.modules["saj_esolar_air"] = package
    spec = importlib.util.spec_from_file_location(
        f"saj_esolar_air.{name}",
        _COMPONENT / filename,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_helpers = _load_component_module("sensor_helpers", "sensor_helpers.py")
device_is_offline = _helpers.device_is_offline
is_live_data_offline = _helpers.is_live_data_offline
offline_blocks_live_sensor = _helpers.offline_blocks_live_sensor
plant_is_offline = _helpers.plant_is_offline


class _Sensor:
    def __init__(self) -> None:
        self._attr_available = True
        self._attr_native_value = 1176


class PlantOfflineTest(unittest.TestCase):
    def test_running_state_online_ignores_contradictory_device_status(self) -> None:
        plant = {"runningState": 1, "deviceStatus": 3, "isOnline": "Y"}
        self.assertFalse(plant_is_offline(plant))

    def test_running_state_string_online_ignores_device_status_string(self) -> None:
        plant = {"runningState": "1", "deviceStatus": "3"}
        self.assertFalse(plant_is_offline(plant))

    def test_v2_normal_running_state_ignores_device_status(self) -> None:
        plant = {"runningState": 6, "deviceStatus": 3}
        self.assertFalse(plant_is_offline(plant))

    def test_alarm_is_not_offline_when_device_status_says_offline(self) -> None:
        plant = {"runningState": 2, "deviceStatus": 3}
        self.assertFalse(plant_is_offline(plant))

    def test_running_state_offline_still_blocks(self) -> None:
        plant = {"runningState": 3, "deviceStatus": 1, "isOnline": "Y"}
        self.assertTrue(plant_is_offline(plant))

    def test_device_status_fallback_when_running_state_missing(self) -> None:
        self.assertTrue(plant_is_offline({"deviceStatus": 3}))
        self.assertTrue(plant_is_offline({"deviceStatus": "3"}))
        self.assertFalse(plant_is_offline({"deviceStatus": 1}))

    def test_unparsable_running_state_falls_back_to_device_status(self) -> None:
        self.assertTrue(plant_is_offline({"runningState": "Normal", "deviceStatus": 3}))
        self.assertFalse(plant_is_offline({"runningState": "", "deviceStatus": 1}))

    def test_is_online_still_marks_offline(self) -> None:
        self.assertTrue(plant_is_offline({"runningState": 1, "deviceStatus": 1, "isOnline": "N"}))
        self.assertTrue(plant_is_offline({"runningState": 1, "isOnline": 0}))
        self.assertTrue(plant_is_offline({"isOnline": "false"}))
        self.assertFalse(plant_is_offline({"runningState": 1, "isOnline": "Y"}))
        self.assertFalse(plant_is_offline({"isOnline": 1}))

    def test_device_offline_still_blocks_live_readings(self) -> None:
        plant = {"runningState": 1, "deviceStatus": 3}
        device = {"runningState": 3, "deviceStatus": 1}
        self.assertFalse(plant_is_offline(plant))
        self.assertTrue(device_is_offline(device))
        self.assertTrue(is_live_data_offline(plant, device))
        self.assertFalse(is_live_data_offline(plant, {"runningState": 1, "onLine": 1}))

    def test_contradictory_plant_status_keeps_live_sensor_value(self) -> None:
        sensor = _Sensor()
        blocked = offline_blocks_live_sensor(
            sensor,
            {"runningState": 1, "deviceStatus": 3},
        )
        self.assertFalse(blocked)
        self.assertTrue(sensor._attr_available)
        self.assertEqual(sensor._attr_native_value, 1176)

    def test_offline_running_state_still_clears_live_sensor(self) -> None:
        sensor = _Sensor()
        blocked = offline_blocks_live_sensor(
            sensor,
            {"runningState": 3, "deviceStatus": 1},
        )
        self.assertTrue(blocked)
        self.assertFalse(sensor._attr_available)
        self.assertIsNone(sensor._attr_native_value)

    def test_offline_still_can_report_zero(self) -> None:
        sensor = _Sensor()
        blocked = offline_blocks_live_sensor(
            sensor,
            {"deviceStatus": 3},
            report_zero=True,
        )
        self.assertTrue(blocked)
        self.assertTrue(sensor._attr_available)
        self.assertEqual(sensor._attr_native_value, 0)


if __name__ == "__main__":
    unittest.main()
