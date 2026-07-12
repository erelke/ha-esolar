"""Shared helpers for SAJ eSolar sensor entities."""
from __future__ import annotations

from typing import Any

from .const import PLANT_RUNNING_STATE_OFFLINE

_OFFLINE_ONLINE_VALUES = frozenset({"N", "0", "FALSE"})


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def plant_is_offline(plant: dict) -> bool:
    """Return True when the plant is offline."""
    state = _as_int(plant.get("runningState"))
    if state == PLANT_RUNNING_STATE_OFFLINE:
        return True

    status = _as_int(plant.get("deviceStatus"))
    if status == PLANT_RUNNING_STATE_OFFLINE:
        return True

    online = plant.get("isOnline")
    if online is not None and str(online).upper() in _OFFLINE_ONLINE_VALUES:
        return True

    return False


def device_is_offline(device: dict) -> bool:
    """Return True when an inverter/device is offline."""
    state = _as_int(device.get("runningState"))
    if state == PLANT_RUNNING_STATE_OFFLINE:
        return True

    online = _as_int(device.get("onLine"))
    if online == PLANT_RUNNING_STATE_OFFLINE or online == 0:
        return True

    online_str = _as_int(device.get("onLineStr"))
    if online_str == PLANT_RUNNING_STATE_OFFLINE:
        return True

    return False


def is_live_data_offline(plant: dict, device: dict | None = None) -> bool:
    """Return True when plant or optional device should not expose live readings."""
    return plant_is_offline(plant) or (
        device is not None and device_is_offline(device)
    )


def offline_blocks_live_sensor(
    sensor: Any,
    plant: dict,
    device: dict | None = None,
    *,
    report_zero: bool = False,
) -> bool:
    """Mark a live sensor offline; optionally report zero instead of unavailable."""
    if not is_live_data_offline(plant, device):
        return False

    if report_zero:
        sensor._attr_available = True
        sensor._attr_native_value = 0
    else:
        sensor._attr_available = False
        sensor._attr_native_value = None
    return True
