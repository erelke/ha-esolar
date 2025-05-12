"""Diagnostics support for tuya-local."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_REGION, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.saj_esolar_air import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return _async_get_diagnostics(hass, entry)


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a device entry."""
    return _async_get_diagnostics(hass, entry, device)


@callback
def _async_get_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
    device: DeviceEntry | None = None,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""

    config = entry.as_dict()

    if 'plant_info' in config['data']:
        del config['data']['plant_info']

    coordinator = hass.data[DOMAIN][entry.entry_id]

    runtime_data = coordinator.data

    sensitive_keys = [CONF_PASSWORD, CONF_USERNAME, "latitude", "longitude", "latitudeStr", "longitudeStr", "plantUid", "address", "deviceSnList",
                      "deviceSn", "devicePc", "modulePc", "moduleSn", "userUid", "fullAddress", "ownerEmail", "moduleSnList",
                      "email", "plantId", "plantNo", "officeId", "reportId", "aliases", "identifiers", "serial_number",
                      "emsModulePc", "emsModuleSn"]
    data = {
        "name": entry.title,
        "entry": config,
        "runtime_data": runtime_data,
    }
    if device is not None:
        data["device"] = device.dict_repr

    return anonymize_data(data, sensitive_keys)


def anonymize_data(data, sensitive_keys):
    """Anonimizálja az adatokat, ha azok szerepelnek a sensitive_keys listában."""

    if isinstance(data, dict):  # Ha szótár, akkor nézzük meg az elemeket
        return {
            key: anonymize_data(value, sensitive_keys) if key not in sensitive_keys else (
                {k: REDACTED for k in value} if isinstance(value, dict) else
                [REDACTED for _ in value] if isinstance(value, list) else REDACTED
            )
            for key, value in data.items()
        }

    elif isinstance(data, list):  # Ha lista, akkor az összes elemen végigmegyünk
        return [anonymize_data(item, sensitive_keys) for item in data]

    return data  # Ha nem módosítandó, visszaadjuk eredeti értéket