"""The eSolar integration."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any, TypedDict, cast
import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_REGION, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MONITORED_SITES, CONF_PV_GRID_DATA, CONF_UPDATE_INTERVAL, DOMAIN, CONF_PLANT_UPDATE_INTERVAL
from .esolar import get_esolar_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class ESolarResponse(TypedDict):
    """API response."""
    plantList: list[dict]
    status: str

async def update_listener(hass, entry):
    """Handle options update."""
    _LOGGER.debug(entry.options)


async def async_migrate_entry(hass, entry):
    """Migrálja a régi konfigurációs bejegyzést az új verzióra."""

    _LOGGER.debug(
        f"Checking migration. Version {entry.version}"
    )

    if entry.version == 1:
        new_fields = {
            CONF_REGION: "eu",
            CONF_PLANT_UPDATE_INTERVAL: 10
        }
        new_data = {**entry.data, **new_fields}  # Új mezők hozzáadása
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Beállítja az integrációt a konfigurációs bejegyzés alapján."""
    if not await async_migrate_entry(hass, entry):
        _LOGGER.debug(
            f"Migration failed"
        )
        return False  # Sikertelen migráció esetén ne folytassa

    """Set up eSolar from a config entry."""
    coordinator = ESolarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        domain_data = dict(hass.data[DOMAIN])  # Másolat készítése
        domain_data.pop(entry.entry_id, None)  # Biztonságos törlés
        hass.data[DOMAIN] = domain_data  # Frissített adat visszaírása

    return unload_ok


class ESolarCoordinator(DataUpdateCoordinator[ESolarResponse]):
    """Data update coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        update_interval = timedelta(minutes=(entry.options.get(CONF_PLANT_UPDATE_INTERVAL) or CONF_UPDATE_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self._entry = entry
        self._data = {}

    @property
    def entry_id(self) -> str:
        """Return entry ID."""
        return self._entry.entry_id

    async def _async_update_data(self) -> ESolarResponse:
        """Fetch the latest data from the source."""
        try:
            data = await self.hass.async_add_executor_job(
                get_data, self.hass, self._entry.data, self._entry.options
            )
            self._data.update({self._entry.entry_id: data})
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except ESolarError as err:
            raise UpdateFailed(str(err)) from err

        return data

    def get_data(self, entry_id) -> dict[Any, Any]:
        """Get data from the coordinator."""
        if entry_id in self._data:
            return self._data[entry_id]
        else:
            print(entry_id)
            return {}

class ESolarError(HomeAssistantError):
    """Base error."""


class InvalidAuth(ESolarError):
    """Raised when invalid authentication credentials are provided."""


class APIRatelimitExceeded(ESolarError):
    """Raised when the API rate limit is exceeded."""


class UnknownError(ESolarError):
    """Raised when an unknown error occurs."""


def get_data(
    hass: HomeAssistant, config: Mapping[str, Any], options: Mapping[str, Any]
) -> ESolarResponse:
    """Get data from the API."""

    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)
    region = config.get(CONF_REGION)
    plants = options.get(CONF_MONITORED_SITES)
    use_pv_grid_attributes = options.get(CONF_PV_GRID_DATA)

    try:
        _LOGGER.debug(
            "Fetching data with username %s, for plants %s with pv attributes set to %s",
            username,
            plants,
            use_pv_grid_attributes,
        )
        plant_info = get_esolar_data(region, username, password, plants, use_pv_grid_attributes)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)
    except ValueError as err:
        err_str = str(err)

        if "Invalid authentication credentials" in err_str:
            raise InvalidAuth from err
        if "API rate limit exceeded." in err_str:
            raise APIRatelimitExceeded from err

        _LOGGER.exception("Unexpected exception")
        raise UnknownError from err

    else:
        if "error" in plant_info:
            raise UnknownError(plant_info["error"])

        if plant_info.get("status") != "success":
            _LOGGER.exception("Unexpected response: %s", plant_info)
            raise UnknownError
    return cast(ESolarResponse, plant_info)
