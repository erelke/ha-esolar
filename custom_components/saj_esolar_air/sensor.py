"""Support for ESolar sensors."""
from __future__ import annotations

import datetime
from datetime import timedelta
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ESolarCoordinator, ESolarResponse
from .const import (
    B_B_LOAD,
    B_BACKUP_POWER_W,
    B_BUY_RATE,
    B_BUYELEC,
    B_CAPACITY,
    B_CURRENT,
    B_DIR_CH,
    B_DIR_DIS,
    B_DIR_STB,
    B_DIRECTION,
    B_EXPORT,
    B_GRID_DIRECT,
    B_GRID_POWER_VA,
    B_GRID_POWER_W,
    B_H_LOAD,
    B_IMPORT,
    B_ON_G_FREQ,
    B_ON_G_POWER_W,
    B_ON_G_VOLT,
    B_OUT_CURR,
    B_OUT_FREQ,
    B_OUT_POWER_VA,
    B_OUT_POWER_WATT,
    B_OUT_VOLT,
    B_POWER,
    B_PVELEC,
    B_SELL_RATE,
    B_SELLELEC,
    B_T_LOAD,
    B_USELEC,
    CONF_INVERTER_SENSORS,
    CONF_MONITORED_SITES,
    CONF_PV_GRID_DATA,
    DOMAIN,
    G_POWER,
    I_ALARM,
    I_CTR,
    I_CURRENT_POWER,
    I_DB,
    I_G_CURR_L,
    I_G_FREQ_L,
    I_G_VOL_L,
    I_HISTORY,
    I_MOD_SN,
    I_MODEL,
    I_MONTH_E,
    I_NORMAL,
    I_OFFLINE,
    I_PC,
    I_PV_CURR_PV,
    I_PV_VOL_PV,
    I_SN,
    I_STATUS,
    I_STOCK,
    I_TODAY_E,
    I_TOTAL_E,
    I_TYPE,
    IO_DIRECTION,
    IO_POWER,
    MANUFACTURER,
    P_ADR,
    P_CO2,
    P_CURRENCY,
    P_CURRENT_POWER,
    P_INCOME,
    P_NAME,
    P_PEAK_POWER,
    P_POWER,
    P_TODAY_E,
    P_TOTAL_E,
    P_TREES,
    P_TYPE,
    P_TYPE_AC_COUPLING,
    P_TYPE_BLEND,
    P_TYPE_GRID,
    P_TYPE_ONGRID,
    P_TYPE_STORAGE,
    P_UID,
    P_UNKNOWN,
    PLANT_MODEL,
    PV_DIRECTION,
    PV_POWER,
    S_POWER,
)

ICON_POWER = "mdi:solar-power"
ICON_PANEL = "mdi:solar-panel"
ICON_LIGHTNING = "mdi:lightning-bolt"
ICON_LIGHTNING_CIRCLE = "mdi:lightning-bolt-circle"
ICON_SOCKET = "mdi:power-socket-de"
ICON_TRIANGLE = "mdi:flash-triangle-outline"
ICON_METER = "mdi:meter-electric-outline"
ICON_GRID = "mdi:transmission-tower"
ICON_GRID_EXPORT = "mdi:transmission-tower-export"
ICON_GRID_IMPORT = "mdi:transmission-tower-import"

SCAN_INTERVAL = timedelta(minutes=1)
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eSolar sensor."""
    coordinator: ESolarCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ESolarSensor] = []
    esolar_data: ESolarResponse = coordinator.data
    my_plants = entry.options.get(CONF_MONITORED_SITES)
    use_inverter_sensors = entry.options.get(CONF_INVERTER_SENSORS)
    use_pv_grid_attributes = entry.options.get(CONF_PV_GRID_DATA)

    if my_plants is None:
        return

    for enabled_plant in my_plants:
        for plant in esolar_data["plantList"]:
            if plant["plantname"] != enabled_plant:
                continue

            _LOGGER.debug(
                "Setting up ESolarSensorPlant sensor for %s", plant["plantname"]
            )
            entities.append(
                ESolarSensorPlant(coordinator, plant["plantname"], plant["plantuid"])
            )
            if plant["type"] == 0:
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantTotalEnergy sensor for %s",
                    plant["plantname"],
                )
                entities.append(
                    ESolarSensorPlantTotalEnergy(
                        coordinator, plant["plantname"], plant["plantuid"]
                    )
                )
            elif plant["type"] == 3:
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantBatterySellEnergy sensor for %s",
                    plant["plantname"],
                )
                entities.append(
                    ESolarSensorPlantBatterySellEnergy(
                        coordinator, plant["plantname"], plant["plantuid"]
                    )
                )
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantBatteryBuyEnergy sensor for %s",
                    plant["plantname"],
                )
                entities.append(
                    ESolarSensorPlantBatteryBuyEnergy(
                        coordinator, plant["plantname"], plant["plantuid"]
                    )
                )
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantBatteryChargeEnergy sensor for %s",
                    plant["plantname"],
                )
                entities.append(
                    ESolarSensorPlantBatteryChargeEnergy(
                        coordinator, plant["plantname"], plant["plantuid"]
                    )
                )
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantBatteryDischargeEnergy sensor for %s",
                    plant["plantname"],
                )
                entities.append(
                    ESolarSensorPlantBatteryDischargeEnergy(
                        coordinator, plant["plantname"], plant["plantuid"]
                    )
                )
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantBatterySoC sensor for %s",
                    plant["plantname"],
                )
                entities.append(
                    ESolarSensorPlantBatterySoC(
                        coordinator, plant["plantname"], plant["plantuid"]
                    )
                )

            if use_inverter_sensors:
                for inverter in plant["plantDetail"]["snList"]:
                    _LOGGER.debug(
                        "Setting up ESolarInverterEnergyTotal sensor for %s and inverter %s",
                        plant["plantname"],
                        inverter,
                    )
                    entities.append(
                        ESolarInverterEnergyTotal(
                            coordinator,
                            plant["plantname"],
                            plant["plantuid"],
                            inverter,
                        )
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverterPower sensor for %s and inverter %s",
                        plant["plantname"],
                        inverter,
                    )
                    entities.append(
                        ESolarInverterPower(
                            coordinator,
                            plant["plantname"],
                            plant["plantuid"],
                            inverter,
                            use_pv_grid_attributes,
                        )
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverter PV sensors for %s and inverter %s",
                        plant["plantname"],
                        inverter,
                    )
                    entities.append(
                        ESolarInverterPV1(coordinator, plant["plantname"], plant["plantuid"], inverter,)
                    )
                    if plant["type"] == 3:
                        _LOGGER.debug(
                            "Setting up ESolarInverterBatterySoC sensor for %s and inverter %s",
                            plant["plantname"],
                            inverter,
                        )
                        entities.append(
                            ESolarInverterBatterySoC(
                                coordinator,
                                plant["plantname"],
                                plant["plantuid"],
                                inverter,
                            )
                        )

    async_add_entities(entities, True)


class ESolarSensor(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid

        self._device_name: None | str = None
        self._device_model: None | str = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._plant_name)},
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
        )

        return device_info


class ESolarSensorPlant(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_PANEL
        self._attr_name = f"Plant {self._plant_name} Status"

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
            P_ADR: None,
            P_TYPE: None,
            P_POWER: None,
            P_CURRENCY: None,
            P_TOTAL_E: None,
            P_CO2: None,
            P_TREES: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]
                self._attr_extra_state_attributes[P_ADR] = (
                    plant["address"] + " " + plant["country"]
                )
                if plant["type"] == 0:
                    self._attr_extra_state_attributes[P_TYPE] = P_TYPE_GRID
                if plant["type"] == 1:
                    self._attr_extra_state_attributes[P_TYPE] = P_TYPE_STORAGE
                if plant["type"] == 2:
                    self._attr_extra_state_attributes[P_TYPE] = P_TYPE_BLEND
                if plant["type"] == 3:
                    self._attr_extra_state_attributes[P_TYPE] = P_TYPE_AC_COUPLING
                self._attr_extra_state_attributes[P_POWER] = float(plant["systempower"])
                self._attr_extra_state_attributes[P_CURRENCY] = plant["currency"]

                # Setup state
                if plant["runningState"] == 1:
                    self._attr_native_value = "Normal"
                elif plant["runningState"] == 2:
                    self._attr_native_value = "Alarm"
                elif plant["runningState"] == 3:
                    self._attr_native_value = "Offline"
                else:
                    self._attr_native_value = None

    @property
    def native_value(self) -> str | None:
        """Return sensor state."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup dynamic attributes
                if (plant["plantDetail"]["type"]) == 0:
                    self._attr_extra_state_attributes[P_INCOME] = plant["plantDetail"][
                        "income"
                    ]
                else:
                    self._attr_extra_state_attributes[P_INCOME] = None
                self._attr_extra_state_attributes[P_CO2] = plant["plantDetail"][
                    "totalReduceCo2"
                ]
                self._attr_extra_state_attributes[P_TREES] = plant["plantDetail"][
                    "totalPlantTreeNum"
                ]
                self._attr_extra_state_attributes[P_TOTAL_E] = plant["totalElectricity"]

                # Setup state
                if plant["runningState"] == 1:
                    value = "Normal"
                elif plant["runningState"] == 2:
                    value = "Alarm"
                elif plant["runningState"] == 3:
                    value = "Offline"
                else:
                    value = None

        return value


class ESolarSensorPlantTotalEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Energy Total "
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
            P_TODAY_E: None,
            P_CURRENT_POWER: None,
            P_PEAK_POWER: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]

                # Setup state
                self._attr_native_value = float(plant["totalElectricity"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup dynamic attributes
                self._attr_extra_state_attributes[P_TODAY_E] = float(
                    plant["todayElectricity"]
                )
                self._attr_extra_state_attributes[P_CURRENT_POWER] = float(
                    plant["nowPower"]
                )
                if plant["type"] == 0:
                    peak_power = float(0.0)
                    if plant["peakList"] is not None:
                        for inverter in plant["peakList"]:
                            peak_power += inverter["peakPower"]
                    self._attr_extra_state_attributes[P_PEAK_POWER] = float(peak_power)
                else:
                    self._attr_extra_state_attributes[P_PEAK_POWER] = None

                # Setup state
                value = float(plant["totalElectricity"])

        return value


class ESolarSensorPlantBatteryBuyEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_buy_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Buy Energy Total"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]

                # Setup state
                if plant["plantDetail"]["totalBuyElec"] is not None:
                    self._attr_native_value = float(
                        plant["plantDetail"]["totalBuyElec"]
                    )

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup state
                if plant["plantDetail"]["totalBuyElec"] is not None:
                    value = float(plant["plantDetail"]["totalBuyElec"])

        return value


class ESolarSensorPlantBatterySellEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_sell_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Sell Energy Total"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]

                # Setup state
                if plant["plantDetail"]["totalSellElec"] is not None:
                    self._attr_native_value = float(
                        plant["plantDetail"]["totalSellElec"]
                    )

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup state
                if plant["plantDetail"]["totalSellElec"] is not None:
                    value = float(plant["plantDetail"]["totalSellElec"])

        return value


class ESolarSensorPlantBatteryChargeEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_charge_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Charge Energy"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]

                # Setup state
                charge = float(0)
                if "beanList" in plant and plant["beanList"] is not None:
                    for bean in plant["beanList"]:
                        charge += float(bean["chargeElec"])
                self._attr_native_value = charge

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup state
                charge = float(0)
                if "beanList" in plant and plant["beanList"] is not None:
                    for bean in plant["beanList"]:
                        charge += float(bean["chargeElec"])
                value = charge

        return value


class ESolarSensorPlantBatteryDischargeEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_discharge_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Discharge Energy"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]

                # Setup state
                discharge = float(0)
                if "beanList" in plant and plant["beanList"] is not None:
                    for bean in plant["beanList"]:
                        discharge += float(bean["dischargeElec"])
                self._attr_native_value = discharge

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup state
                discharge = float(0)
                if "beanList" in plant and plant["beanList"] is not None:
                    for bean in plant["beanList"]:
                        discharge += float(bean["dischargeElec"])
                value = discharge

        return value


class ESolarSensorPlantBatterySoC(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_battery_soc_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_name = f"Plant {self._plant_name} State Of Charge"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        installed_power = float(0)
        available_power = float(0)
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            # Setup static attributes
            self._attr_available = True
            self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
            self._attr_extra_state_attributes[P_UID] = plant["plantuid"]

            # Setup state
            for inverter in plant["plantDetail"]["snList"]:
                if "kitList" not in plant or plant["kitList"] is None:
                    continue
                for kit in plant["kitList"]:
                    if inverter == kit["devicesn"] and kit["onLineStr"] == "1":
                        installed_power += kit["storeDevicePower"]["batCapcity"]
                        available_power += (
                            kit["storeDevicePower"]["batCapcity"]
                            * kit["storeDevicePower"]["batEnergyPercent"]
                        )

            if installed_power > 0:
                self._attr_native_value = float(available_power / installed_power)

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        installed_power = float(0)
        available_power = float(0)
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            # Setup state
            for inverter in plant["plantDetail"]["snList"]:
                if "kitList" not in plant or plant["kitList"] is None:
                    continue
                for kit in plant["kitList"]:
                    if inverter == kit["devicesn"] and kit["onLineStr"] == "1":
                        installed_power += kit["storeDevicePower"]["batCapcity"]
                        available_power += (
                            kit["storeDevicePower"]["batCapcity"]
                            * kit["storeDevicePower"]["batEnergyPercent"]
                        )
            if installed_power > 0:
                value = float(available_power / installed_power)
            else:
                value = None

        return value


class ESolarInverterEnergyTotal(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}"
        self.inverter_sn = inverter_sn

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} Energy Total"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
            I_MODEL: None,
            I_TYPE: None,
            I_SN: None,
            I_PC: None,
            I_DB: None,
            I_CTR: None,
            I_MOD_SN: None,
            I_TODAY_E: None,
            I_MONTH_E: None,
            I_TOTAL_E: None,
            I_STATUS: None,
            I_CURRENT_POWER: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]
                if "kitList" not in plant or plant["kitList"] is None:
                    continue
                for kit in plant["kitList"]:
                    if kit["devicesn"] == self.inverter_sn:
                        self._attr_extra_state_attributes[I_MODEL] = kit["devicetype"]

                        if kit["type"] == 0:
                            self._attr_extra_state_attributes[I_TYPE] = P_TYPE_ONGRID
                        elif kit["type"] == 1:
                            self._attr_extra_state_attributes[I_TYPE] = P_TYPE_STORAGE
                        elif kit["type"] == 2:
                            self._attr_extra_state_attributes[
                                I_TYPE
                            ] = P_TYPE_AC_COUPLING
                        else:
                            self._attr_extra_state_attributes[I_TYPE] = P_UNKNOWN

                        self._attr_extra_state_attributes[I_SN] = kit["devicesn"]
                        self._attr_extra_state_attributes[I_PC] = kit["devicepc"]
                        self._attr_extra_state_attributes[I_DB] = kit["displayfw"]
                        self._attr_extra_state_attributes[I_CTR] = kit["mastermcufw"]
                        self._attr_extra_state_attributes[I_MOD_SN] = kit["kitSn"]

                        # Setup state
                        self._attr_native_value = float(kit["totalSellEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            if "kitList" in plant and plant["kitList"] is not None:
                for kit in plant["kitList"]:
                    if kit["devicesn"] != self.inverter_sn:
                        continue
                    # Setup state
                    value = float(kit["totalSellEnergy"])

                    # Setup dynamic attributes
                    self._attr_extra_state_attributes[I_TODAY_E] = float(
                        kit["todaySellEnergy"]
                    )
                    self._attr_extra_state_attributes[I_MONTH_E] = float(
                        kit["monthSellEnergy"]
                    )
                    self._attr_extra_state_attributes[I_TOTAL_E] = float(
                        kit["totalSellEnergy"]
                    )
                    if kit["onLineStr"] == "1":
                        self._attr_extra_state_attributes[I_STATUS] = I_NORMAL
                    elif kit["onLineStr"] == "2":
                        self._attr_extra_state_attributes[I_STATUS] = I_ALARM
                    elif kit["onLineStr"] == "3":
                        self._attr_extra_state_attributes[I_STATUS] = I_OFFLINE
                    elif kit["onLineStr"] == "4":
                        self._attr_extra_state_attributes[I_STATUS] = I_STOCK
                    elif kit["onLineStr"] == "4":
                        self._attr_extra_state_attributes[I_STATUS] = I_HISTORY
                    else:
                        self._attr_extra_state_attributes[I_STATUS] = P_UNKNOWN

                    self._attr_extra_state_attributes[I_CURRENT_POWER] = kit["powernow"]

                    if kit["type"] == 2:
                        if kit["storeDevicePower"]["batteryDirection"] == 0:
                            self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_STB
                        elif kit["storeDevicePower"]["batteryDirection"] == 1:
                            self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_DIS
                        elif kit["storeDevicePower"]["batteryDirection"] == -1:
                            self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_CH
                        else:
                            self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN
            if "beanList" in plant and plant["beanList"] is not None:
                for bean in plant["beanList"]:
                    if bean["devicesn"] == self.inverter_sn:
                        self._attr_extra_state_attributes[B_PVELEC] = bean["pvElec"]
                        self._attr_extra_state_attributes[B_USELEC] = bean["useElec"]
                        self._attr_extra_state_attributes[B_BUYELEC] = bean["buyElec"]
                        self._attr_extra_state_attributes[B_SELLELEC] = bean["sellElec"]
                        self._attr_extra_state_attributes[B_BUY_RATE] = bean["buyRate"]
                        self._attr_extra_state_attributes[B_SELL_RATE] = bean[
                            "sellRate"
                        ]

        return value


class ESolarInverterPower(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
        use_pv_grid_attributes,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self.use_pv_grid_attributes = use_pv_grid_attributes
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"PV_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT

        if self.use_pv_grid_attributes:
            self._attr_extra_state_attributes = {
                P_NAME: None,
                P_UID: None,
                I_MODEL: None,
                I_SN: None,
                I_PV_VOL_PV: None,
                I_PV_CURR_PV: None,
                I_G_VOL_L: None,
                I_G_CURR_L: None,
                I_G_FREQ_L: None,
            }
        else:
            self._attr_extra_state_attributes = {
                P_NAME: None,
                P_UID: None,
                I_MODEL: None,
                I_SN: None,
            }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
                self._attr_extra_state_attributes[P_UID] = plant["plantuid"]
                if "kitList" in plant and plant["kitList"] is not None:
                    for kit in plant["kitList"]:
                        if kit["devicesn"] == self.inverter_sn:
                            self._attr_extra_state_attributes[I_MODEL] = kit[
                                "devicetype"
                            ]
                            self._attr_extra_state_attributes[I_SN] = kit["devicesn"]

                            # Setup state
                            self._attr_native_value = float(kit["powernow"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            # Setup dynamic attributes
            if "kitList" not in plant or plant["kitList"] is None:
                continue
            for kit in plant["kitList"]:
                if kit["devicesn"] != self.inverter_sn:
                    continue

                # Setup state
                value = float(kit["powernow"])

                if not self.use_pv_grid_attributes:
                    continue

                if kit["onLineStr"] == "1":
                    self._attr_extra_state_attributes[I_PV_VOL_PV] = [
                        kit["findRawdataPageList"]["pV1Volt"],
                        kit["findRawdataPageList"]["pV2Volt"],
                        kit["findRawdataPageList"]["pV3Volt"],
                    ]
                    self._attr_extra_state_attributes[I_PV_CURR_PV] = [
                        kit["findRawdataPageList"]["pV1Curr"],
                        kit["findRawdataPageList"]["pV2Curr"],
                        kit["findRawdataPageList"]["pV3Curr"],
                    ]
                    self._attr_extra_state_attributes[I_G_VOL_L] = [
                        kit["findRawdataPageList"]["rGridVolt"],
                        kit["findRawdataPageList"]["sGridVolt"],
                        kit["findRawdataPageList"]["tGridVolt"],
                    ]
                    self._attr_extra_state_attributes[I_G_CURR_L] = [
                        kit["findRawdataPageList"]["rGridCurr"],
                        kit["findRawdataPageList"]["sGridCurr"],
                        kit["findRawdataPageList"]["tGridCurr"],
                    ]
                    self._attr_extra_state_attributes[I_G_FREQ_L] = [
                        kit["findRawdataPageList"]["rGridFreq"],
                        kit["findRawdataPageList"]["sGridFreq"],
                        kit["findRawdataPageList"]["tGridFreq"],
                    ]
                    if (kit["findRawdataPageList"]["deviceType"]) == 2:

                        self._attr_extra_state_attributes[B_GRID_POWER_W] = [
                            kit["findRawdataPageList"]["rGridPowerWatt"],
                            kit["findRawdataPageList"]["sGridPowerWatt"],
                            kit["findRawdataPageList"]["tGridPowerWatt"],
                        ]
                        self._attr_extra_state_attributes[B_GRID_POWER_VA] = [
                            kit["findRawdataPageList"]["rGridPowerVA"],
                            kit["findRawdataPageList"]["sGridPowerVA"],
                            kit["findRawdataPageList"]["tGridPowerVA"],
                        ]
                        self._attr_extra_state_attributes[B_OUT_VOLT] = [
                            kit["findRawdataPageList"]["rOutVolt"],
                            kit["findRawdataPageList"]["sOutVolt"],
                            kit["findRawdataPageList"]["tOutVolt"],
                        ]
                        self._attr_extra_state_attributes[B_OUT_CURR] = [
                            kit["findRawdataPageList"]["rOutCurr"],
                            kit["findRawdataPageList"]["sOutCurr"],
                            kit["findRawdataPageList"]["tOutCurr"],
                        ]
                        self._attr_extra_state_attributes[B_OUT_POWER_WATT] = [
                            kit["findRawdataPageList"]["rOutPowerWatt"],
                            kit["findRawdataPageList"]["sOutPowerWatt"],
                            kit["findRawdataPageList"]["tOutPowerWatt"],
                        ]
                        self._attr_extra_state_attributes[B_OUT_POWER_VA] = [
                            kit["findRawdataPageList"]["rOutPowerVA"],
                            kit["findRawdataPageList"]["sOutPowerVA"],
                            kit["findRawdataPageList"]["tOutPowerVA"],
                        ]
                        self._attr_extra_state_attributes[B_OUT_FREQ] = [
                            kit["findRawdataPageList"]["rOutFreq"],
                            kit["findRawdataPageList"]["sOutFreq"],
                            kit["findRawdataPageList"]["tOutFreq"],
                        ]
                        self._attr_extra_state_attributes[B_ON_G_VOLT] = [
                            kit["findRawdataPageList"]["rOnGridOutVolt"],
                            kit["findRawdataPageList"]["sOnGridOutVolt"],
                            kit["findRawdataPageList"]["tOnGridOutVolt"],
                        ]
                        self._attr_extra_state_attributes[B_ON_G_FREQ] = [
                            kit["findRawdataPageList"]["rOnGridOutFreq"]
                        ]
                        self._attr_extra_state_attributes[B_ON_G_POWER_W] = [
                            kit["findRawdataPageList"]["rOnGridOutPowerWatt"],
                            kit["findRawdataPageList"]["sOnGridOutPowerWatt"],
                            kit["findRawdataPageList"]["tOnGridOutPowerWatt"],
                        ]
                        self._attr_extra_state_attributes[B_ON_G_FREQ] = [
                            kit["findRawdataPageList"]["rOnGridOutFreq"]
                        ]
                        self._attr_extra_state_attributes[B_BACKUP_POWER_W] = [
                            kit["findRawdataPageList"]["rBackupPowerWatt"]
                        ]
                else:
                    self._attr_extra_state_attributes[I_PV_VOL_PV] = [
                        None,
                        None,
                        None,
                    ]
                    self._attr_extra_state_attributes[I_PV_CURR_PV] = [
                        None,
                        None,
                        None,
                    ]
                    self._attr_extra_state_attributes[I_G_VOL_L] = [
                        None,
                        None,
                        None,
                    ]
                    self._attr_extra_state_attributes[I_G_CURR_L] = [
                        None,
                        None,
                        None,
                    ]
                    self._attr_extra_state_attributes[I_G_FREQ_L] = [
                        None,
                        None,
                        None,
                    ]

        return value


class ESolarInverterPV1(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"PV_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PV1"
        self._attr_native_unit_of_measurement = UnitOfPower.VOLT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "kitList" in plant and plant["kitList"] is not None:
                    for kit in plant["kitList"]:
                        if kit["devicesn"] == self.inverter_sn:
                            # Setup state
                            self._attr_native_value = float(kit["findRawdataPageList"]["pV1Volt"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            # Setup dynamic attributes
            if "kitList" not in plant or plant["kitList"] is None:
                continue
            for kit in plant["kitList"]:
                if kit["devicesn"] != self.inverter_sn:
                    continue

                if kit["onLineStr"] == "1":
                    # Setup state
                    value = float(kit["findRawdataPageList"]["pV1Volt"])

        return value

class ESolarInverterBatterySoC(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Battery_SOC_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn
        self._attr_native_value = None

        self._attr_name = f"Inverter {inverter_sn} Battery State Of Charge"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT

        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
            I_MODEL: None,
            I_SN: None,
            B_CAPACITY: None,
            B_CURRENT: None,
            B_POWER: None,
            B_DIRECTION: None,
            G_POWER: None,
            B_GRID_DIRECT: None,
            IO_POWER: None,
            IO_DIRECTION: None,
            PV_POWER: None,
            PV_DIRECTION: None,
            B_T_LOAD: None,
            B_H_LOAD: None,
            B_B_LOAD: None,
            S_POWER: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            # Setup static attributes
            self._attr_available = True
            self._attr_extra_state_attributes[P_NAME] = plant["plantname"]
            self._attr_extra_state_attributes[P_UID] = plant["plantuid"]
            if "kitList" not in plant or plant["kitList"] is None:
                continue
            for kit in plant["kitList"]:
                if kit["devicesn"] == self.inverter_sn:
                    self._attr_extra_state_attributes[I_MODEL] = kit["devicetype"]
                    self._attr_extra_state_attributes[I_SN] = kit["devicesn"]
                    self._attr_extra_state_attributes[B_CAPACITY] = kit[
                        "storeDevicePower"
                    ]["batCapcityStr"]

                    # Setup state
                    if kit["onLineStr"] == "1":
                        self._attr_native_value = kit["storeDevicePower"][
                            "batEnergyPercent"
                        ]

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        # Setup state
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantname"] != self._plant_name:
                continue
            if "kitList" not in plant or plant["kitList"] is None:
                continue
            for kit in plant["kitList"]:
                if self.inverter_sn == kit["devicesn"] and kit["onLineStr"] == "1":
                    value = float(kit["storeDevicePower"]["batEnergyPercent"])

                    # Setup dynamic attributes
                    self._attr_extra_state_attributes[B_CURRENT] = kit[
                        "storeDevicePower"
                    ]["batCurr"]
                    self._attr_extra_state_attributes[B_POWER] = kit[
                        "storeDevicePower"
                    ]["batteryPower"]

                    if kit["storeDevicePower"]["batteryDirection"] == 0:
                        self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_STB
                    elif kit["storeDevicePower"]["batteryDirection"] == 1:
                        self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_DIS
                    elif kit["storeDevicePower"]["batteryDirection"] == -1:
                        self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_CH
                    else:
                        self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN

                    self._attr_extra_state_attributes[G_POWER] = kit[
                        "storeDevicePower"
                    ]["gridPower"]

                    if kit["storeDevicePower"]["gridDirection"] == 1:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = B_EXPORT
                    elif kit["storeDevicePower"]["gridDirection"] == -1:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = B_IMPORT
                    else:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN

                    self._attr_extra_state_attributes[IO_POWER] = kit[
                        "storeDevicePower"
                    ]["inputOutputPower"]

                    if kit["storeDevicePower"]["outPutDirection"] == 1:
                        self._attr_extra_state_attributes[IO_DIRECTION] = B_EXPORT
                    elif kit["storeDevicePower"]["outPutDirection"] == -1:
                        self._attr_extra_state_attributes[IO_DIRECTION] = B_IMPORT
                    else:
                        self._attr_extra_state_attributes[IO_DIRECTION] = P_UNKNOWN

                    self._attr_extra_state_attributes[PV_POWER] = kit[
                        "storeDevicePower"
                    ]["pvPower"]

                    if kit["storeDevicePower"]["pvDirection"] == 1:
                        self._attr_extra_state_attributes[PV_DIRECTION] = B_EXPORT
                    elif kit["storeDevicePower"]["pvDirection"] == -1:
                        self._attr_extra_state_attributes[PV_DIRECTION] = B_IMPORT
                    else:
                        self._attr_extra_state_attributes[PV_DIRECTION] = P_UNKNOWN

                    self._attr_extra_state_attributes[B_T_LOAD] = kit[
                        "storeDevicePower"
                    ]["totalLoadPower"]
                    self._attr_extra_state_attributes[B_H_LOAD] = kit[
                        "storeDevicePower"
                    ]["homeLoadPower"]
                    self._attr_extra_state_attributes[B_B_LOAD] = kit[
                        "storeDevicePower"
                    ]["backupLoadPower"]
                    self._attr_extra_state_attributes[S_POWER] = kit[
                        "storeDevicePower"
                    ]["solarPower"]

        return value
