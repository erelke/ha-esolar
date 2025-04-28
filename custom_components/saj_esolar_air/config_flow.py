"""Config flow for eSolar integration."""
from __future__ import annotations

import logging
from email.policy import default
from typing import Any

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_REGION, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import (
    CONF_INVERTER_SENSORS,
    CONF_MONITORED_SITES,
    CONF_PV_GRID_DATA,
    DOMAIN,
    CONF_PLANT_UPDATE_INTERVAL,
    CONF_REGION,
    CONF_REGION_EU,
    CONF_REGION_IN,
    CONF_REGION_CN
)
from .esolar import esolar_web_autenticate, web_get_plant

CONF_TITLE = "SAJ eSolar"

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=CONF_REGION_EU): SelectSelector(
            SelectSelectorConfig(
                options=[
                    CONF_REGION_EU,
                    CONF_REGION_IN,
                    CONF_REGION_CN
                ],
                translation_key=CONF_REGION
            )
        ),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

class ESolarHub:
    """SAJ eSolar configuration validations."""

    def __init__(self) -> None:
        """Initialize."""
        self.plant_list: dict[str, Any] = {}

    def auth_and_get_solar_plants(self, region: str, username: str, password: str) -> bool:
        """Download and list available inverters."""
        try:
            session = esolar_web_autenticate(region, username, password)
            self.plant_list = web_get_plant(region, session).get("plantList")
        except requests.exceptions.HTTPError:
            _LOGGER.error("Login: HTTPError")
            return False
        except requests.exceptions.ConnectionError:
            _LOGGER.error("Login: ConnectionError")
            return False
        except requests.exceptions.Timeout:
            _LOGGER.error("Login: Timeout")
            return False
        except requests.exceptions.RequestException:
            _LOGGER.error("Login: RequestException")
            return False
        return True


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate that the user input allows us to connect and fetch list of sites."""

    hub = ESolarHub()
    if not await hass.async_add_executor_job(
        hub.auth_and_get_solar_plants,
        data[CONF_REGION],
        data[CONF_USERNAME],
        data[CONF_PASSWORD]
    ):
        raise InvalidAuth
    return {"plant_list": hub.plant_list}

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for eSolar."""

    VERSION = 2

    def __init__(self):
        """Set up the the config flow."""
        self.sites = {}
        self.data = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step. Username and password."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}
        self.data = user_input
        try:
            info = await validate_input(self.hass, self.data)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.sites = [site["plantName"] for site in info["plant_list"]]
            if len(self.sites) == 1:
                return self.async_create_entry(
                    title=CONF_TITLE,
                    data=self.data,
                    options={
                        CONF_MONITORED_SITES: self.sites,
                        CONF_INVERTER_SENSORS: False,
                        CONF_PV_GRID_DATA: False,
                        CONF_PLANT_UPDATE_INTERVAL: 10
                    },
                )

            # Account has more than one site, select sites to add

            return await self.async_step_sites()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_sites(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the second step. Select which sites to use."""

        errors = {}
        if user_input is not None:
            if len(user_input[CONF_MONITORED_SITES]) > 0:
                user_input.update({CONF_INVERTER_SENSORS: False})
                user_input.update({CONF_PV_GRID_DATA: False})
                user_input.update({CONF_PLANT_UPDATE_INTERVAL: 10})
                return self.async_create_entry(
                    title=CONF_TITLE, data=self.data, options=user_input
                )

            errors["base"] = "no_sites"

        return self.async_show_form(
            step_id="sites",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MONITORED_SITES, default=self.sites
                    ): cv.multi_select(self.sites),
                }
            ),
            errors=errors,
        )
    async def async_step_reconfigure_sites(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the second step. Select which sites to use."""

        errors = {}
        if user_input is not None:
            if len(user_input[CONF_MONITORED_SITES]) > 0:
                user_input.update({CONF_INVERTER_SENSORS: self._get_reconfigure_entry().options.get(CONF_INVERTER_SENSORS)})
                user_input.update({CONF_PV_GRID_DATA: self._get_reconfigure_entry().options.get(CONF_PV_GRID_DATA)})
                user_input.update({CONF_PLANT_UPDATE_INTERVAL: self._get_reconfigure_entry().options.get(CONF_PLANT_UPDATE_INTERVAL)})
                print (self.data)
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data=self.data,
                    options=user_input,
                    reload_even_if_entry_is_unchanged=False
                )

            errors["base"] = "no_sites"

        return self.async_show_form(
            step_id="reconfigure_sites",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_MONITORED_SITES, default=self.sites
                    ): cv.multi_select(self.sites),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration step."""
        errors = {}

        if user_input is None:
            return self.async_show_form(
                step_id="reconfigure", data_schema=STEP_USER_DATA_SCHEMA
            )

        self.data = user_input
        try:
            info = await validate_input(self.hass, self.data)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            self.sites = [site["plantName"] for site in info["plant_list"]]
            if len(self.sites) == 1:
                return self.async_update_reload_and_abort(
                    self._get_reconfigure_entry(),
                    data=self.data,
                    options={
                        CONF_MONITORED_SITES: self.sites,
                        CONF_INVERTER_SENSORS: self._get_reconfigure_entry().options.get(CONF_INVERTER_SENSORS),
                        CONF_PV_GRID_DATA: self._get_reconfigure_entry().options.get(CONF_PV_GRID_DATA),
                        CONF_PLANT_UPDATE_INTERVAL: self._get_reconfigure_entry().options.get(CONF_PLANT_UPDATE_INTERVAL),
                    },
                    reload_even_if_entry_is_unchanged=False,
                )
            return await self.async_step_reconfigure_sites()

        return self.async_show_form(
            step_id="reconfigure", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a options flow for eSolar."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""


    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            user_input.update(
                {
                    CONF_MONITORED_SITES: self.config_entry.options.get(
                        CONF_MONITORED_SITES
                    )
                }
            )
            return self.async_create_entry(title=CONF_TITLE, data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INVERTER_SENSORS,
                        default=self.config_entry.options.get(CONF_INVERTER_SENSORS),
                    ): bool,
                    vol.Required(
                        CONF_PV_GRID_DATA,
                        default=self.config_entry.options.get(CONF_PV_GRID_DATA),
                    ): bool,
                    vol.Required(
                        CONF_PLANT_UPDATE_INTERVAL,
                        default=self.config_entry.options.get(CONF_PLANT_UPDATE_INTERVAL),
                    ): int,
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
