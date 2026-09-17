"""Shared helpers for SAJ eSolar sensor entities."""
from __future__ import annotations

from typing import Any

from .const import PLANT_RUNNING_STATE_OFFLINE

_OFFLINE_ONLINE_VALUES = frozenset({"N", "0", "FALSE"})
_EMPTY_VALUES = frozenset({"", "--", "N/A", "n/a", "null"})


def has_value(value: Any) -> bool:
    """Return True when the API sent a real (possibly zero) value."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() in _EMPTY_VALUES:
        return False
    return True


def as_number(value: Any) -> float | None:
    """Parse a numeric API field, ignoring empty placeholders."""
    if not has_value(value):
        return None
    if isinstance(value, str):
        value = value.strip().rstrip("%").replace(",", ".")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def first_present(*values: Any) -> Any:
    """Return the first non-empty API value."""
    for value in values:
        if has_value(value):
            return value
    return None


def find_inverter(plant: dict, inverter_sn: str) -> dict:
    for device in plant.get("devices") or []:
        if isinstance(device, dict) and device.get("deviceSn") == inverter_sn:
            return device
    return {}


def inverter_properties(device: dict) -> dict[str, Any]:
    """Firmware/warranty fields for the inverter device page."""
    attrs: dict[str, Any] = {}
    mapping = (
        ("display_fw", "displayFw"),
        ("master_mcu_fw", "masterMcuFw"),
        ("software_version", "softwareVersion"),
        ("hardware_version", "hardwareVersion"),
        ("device_pc", "devicePc"),
        ("warranty_end", "warrantyEndTime"),
        ("device_model", "deviceModel"),
    )
    for dest, src in mapping:
        value = device.get(src)
        if has_value(value):
            attrs[dest] = value
    return attrs


def battery_properties(battery: dict) -> dict[str, Any]:
    """BMS/warranty fields for the battery device page."""
    attrs: dict[str, Any] = {}
    mapping = (
        ("bms_sn", "bmsSn"),
        ("bms_software_version", "bmsSoftwareVersion"),
        ("bms_hardware_version", "bmsHardwareVersion"),
        ("warranty_start", "warrantyStartTime"),
        ("warranty_end", "warrantyEndTime"),
        ("heat_film_status", "batHeatFilmStatusName"),
        ("battery_model", "batModel"),
        ("device_sn", "deviceSn"),
        ("cluster_id", "clusterId"),
    )
    for dest, src in mapping:
        value = battery.get(src)
        if has_value(value):
            attrs[dest] = value
    if not attrs.get("heat_film_status") and has_value(battery.get("batHeatFilmStatus")):
        attrs["heat_film_status"] = battery.get("batHeatFilmStatus")
    return attrs


def module_properties(module: dict) -> dict[str, Any]:
    """Firmware fields for AIO/WiFi/SEC/meter devices."""
    attrs: dict[str, Any] = {}
    mapping = (
        ("software_version", "softwareVersion"),
        ("hardware_version", "hardwareVersion"),
        ("module_fw", "moduleFw"),
        ("module_pc", "modulePc"),
        ("ccid", "ccid"),
        ("alias_name", "aliasName"),
        ("module_model", "moduleModel"),
    )
    for dest, src in mapping:
        value = module.get(src)
        if has_value(value):
            attrs[dest] = value
    return attrs


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
