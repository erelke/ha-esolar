"""Support for ESolar sensors."""
from __future__ import annotations

import time
import datetime
from datetime import timedelta, datetime, timezone
import pytz
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfTemperature,
    EntityCategory
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ESolarCoordinator, ESolarResponse
from .const import (
    CONF_INVERTER_SENSORS,
    CONF_MONITORED_SITES,
    CONF_PV_GRID_DATA,
    DOMAIN,
    MANUFACTURER,
    P_CO2,
    P_TREES,
    P_UID,
    PLANT_MODEL,
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
ICON_THERMOMETER = "mdi:thermometer"
ICON_UPDATE = "mdi:update"
ICON_ALARM = "mdi:alarm-light"

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
            if plant["plantName"] != enabled_plant:
                continue

            _LOGGER.debug(
                "Setting up ESolarSensorPlant sensor for %s", plant["plantName"]
            )
            entities.append(
                ESolarSensorPlant(coordinator, plant["plantName"], plant["plantUid"])
            )
            if plant["type"] == 0:
                _LOGGER.debug(
                    "Setting up ESolarSensorPlantTotalEnergy sensor for %s",
                    plant["plantName"],
                )
                entities.append(
                    ESolarSensorPlantTotalEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                entities.append(
                    ESolarSensorPlantTodayEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                entities.append(
                    ESolarSensorPlantMonthEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                entities.append(
                    ESolarSensorPlantYearEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                entities.append(
                    ESolarSensorPlantPeakPower( coordinator, plant["plantName"], plant["plantUid"] )
                )
                entities.append(
                    ESolarSensorPlantLastUploadTime( coordinator, plant["plantName"], plant["plantUid"] )
                )

            if use_inverter_sensors:
                for inverter in plant["devices"]:
                    _LOGGER.debug(
                        "Setting up ESolarInverterEnergyTotal sensor for %s and inverter %s",
                        plant["plantName"],
                        inverter,
                    )
                    entities.append(
                        ESolarInverterEnergyTotal( coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverterPower sensor for %s and inverter %s",
                        plant["plantName"],
                        inverter,
                    )
                    entities.append(
                        ESolarInverterPower( coordinator, plant["plantName"], plant["plantUid"], inverter, use_pv_grid_attributes, )
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverter other sensors for %s and inverter %s",
                        plant["plantName"],
                        inverter,
                    )
                    entities.append(
                        ESolarInverterPV1( coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPV2(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPV3(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPC1(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPC2(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPC3(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterGV1(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterGV2(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterGV3(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterGC1(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterGC2(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterGC3(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPW1(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPW2(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterPW3(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterEnergyToday(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterEnergyMonth(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarInverterTemperature(coordinator, plant["plantName"], plant["plantUid"], inverter, )
                    )
                    entities.append(
                        ESolarSensorInverterTodayAlarmNum(coordinator, plant["plantName"], plant["plantUid"], inverter,)
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
            P_UID: None,
            P_CO2: None,
            P_TREES: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # self._attr_extra_state_attributes['Original data'] = plant
                self._attr_extra_state_attributes[P_UID] = plant["plantUid"]

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
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup dynamic attributes
                # self._attr_extra_state_attributes['Original data'] = plant
                self._attr_extra_state_attributes[P_CO2] = plant["totalReduceCo2"]
                self._attr_extra_state_attributes[P_TREES] = plant["totalPlantTreeNum"]

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

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True

                # Setup state
                self._attr_native_value = float(plant["totalPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                value = float(plant["totalPvEnergy"])

        return value

class ESolarSensorPlantTodayEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}_today"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Plant {self._plant_name} Energy Today "
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:

                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = float(plant["todayPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                value = float(plant["todayPvEnergy"])

        return value

class ESolarSensorPlantMonthEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}_month"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Plant {self._plant_name} Energy Month"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = float(plant["monthPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                value = float(plant["monthPvEnergy"])

        return value

class ESolarSensorPlantYearEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}_year"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Plant {self._plant_name} Energy Year"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = float(plant["yearPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                value = float(plant["yearPvEnergy"])

        return value

class ESolarSensorPlantLastUploadTime(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_lastUploadTime_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_UPDATE
        self._attr_name = f"Plant {self._plant_name} last Upload Time"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = datetime.strptime(plant["dataTime"]+" "+time.strftime('%z'), "%Y-%m-%d %H:%M:%S %z") #updateDate

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                value = datetime.strptime(plant["dataTime"]+" "+time.strftime('%z'), "%Y-%m-%d %H:%M:%S %z")

        return value

#TODO Find this data
class ESolarSensorPlantPeakPower(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_peakpower_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Peak Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if plant["type"] == 0:
                    peak_power = float(0.0)
                    if plant["peakList"] is not None:
                        for inverter in plant["peakList"]:
                            peak_power += inverter["peakPower"]
                    self._attr_native_value = float(peak_power)
                else:
                    self._attr_native_value = None
    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                if plant["type"] == 0:
                    peak_power = float(0.0)
                    if plant["peakList"] is not None:
                        for inverter in plant["peakList"]:
                            peak_power += inverter["peakPower"]
                    value = float(peak_power)
                else:
                    value = None

        return value


class ESolarSensorInverterTodayAlarmNum(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}_todayAlarmNum"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_ALARM
        self._attr_name = f"Plant {self._plant_name} Today Alarm Num"
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_value = 0

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" not in plant or plant["devices"] is None:
                    continue
                for kit in plant["device"]:
                    if kit["deviceSn"] == self.inverter_sn:
                        # Setup state
                        self._attr_native_value = kit["todayAlarmNum"]

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" not in plant or plant["devices"] is None:
                    continue
                for kit in plant["device"]:
                    if kit["deviceSn"] == self.inverter_sn:
                        # Setup state
                        value = kit["todayAlarmNum"]

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
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" not in plant or plant["devices"] is None:
                    continue
                for kit in plant["device"]:
                    if kit["deviceSn"] == self.inverter_sn:
                        # Setup state
                        self._attr_native_value = float(kit["deviceStatisticsData"]["totalPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self.inverter_sn:
                        continue
                    # Setup state
                    value = float(kit["deviceStatisticsData"]["totalPvEnergy"])
        return value


class ESolarInverterEnergyToday(ESolarSensor):
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

        self._attr_unique_id = f"inverter_{inverter_sn}_today"
        self.inverter_sn = inverter_sn

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Inverter {inverter_sn} Energy Today"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self.inverter_sn:
                        continue
                    # Setup state
                    self._attr_native_value = float(kit["deviceStatisticsData"]["todayPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self.inverter_sn:
                        continue
                    # Setup state
                    value = float(kit["deviceStatisticsData"]["todayPvEnergy"])

        return value


class ESolarInverterEnergyMonth(ESolarSensor):
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

        self._attr_unique_id = f"inverter_{inverter_sn}_month"
        self.inverter_sn = inverter_sn

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Inverter {inverter_sn} Energy Month"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self.inverter_sn:
                        continue
                    # Setup state
                    self._attr_native_value = float(kit["deviceStatisticsData"]["monthPvEnergy"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self.inverter_sn:
                        continue
                    # Setup state
                    value = float(kit["deviceStatisticsData"]["monthPvEnergy"])

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
        self._attr_unique_id = f"PW_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        # Setup state
                        self._attr_native_value = float(kit["deviceStatisticsData"]["powerNow"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            # Setup dynamic attributes
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self.inverter_sn:
                        continue
                    # Setup state
                    value = float(kit["deviceStatisticsData"]["powerNow"])

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
        self._attr_unique_id = f"PV1_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PV1"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 1:
                                self._attr_native_value = float(s["pvvolt"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 1:
                                value = float(s["pvvolt"])

        return value


class ESolarInverterPV2(ESolarSensor):
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
        self._attr_unique_id = f"PV2_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PV2"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 2:
                                self._attr_native_value = float(s["pvvolt"])


    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 2:
                                # Setup state
                                value = float(s["pvvolt"])

        return value


class ESolarInverterPV3(ESolarSensor):
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
        self._attr_unique_id = f"PV3_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PV3"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 3:
                                self._attr_native_value = float(s["pvvolt"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 3:
                                # Setup state
                                value = float(s["pvvolt"])

        return value


class ESolarInverterPC1(ESolarSensor):
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
        self._attr_unique_id = f"PC1_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PC1"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 1:
                                self._attr_native_value = float(s["pvcurr"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 1:
                                # Setup state
                                value = float(s["pvcurr"])

        return value


class ESolarInverterPC2(ESolarSensor):
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
        self._attr_unique_id = f"PC2_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PC2"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 2:
                                self._attr_native_value = float(s["pvcurr"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 2:
                                # Setup state
                                value = float(s["pvcurr"])
        return value


class ESolarInverterPC3(ESolarSensor):
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
        self._attr_unique_id = f"PC3_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PC3"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 3:
                                self._attr_native_value = float(s["pvcurr"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 3:
                                # Setup state
                                value = float(s["pvcurr"])

        return value

class ESolarInverterPW1(ESolarSensor):
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
        self._attr_unique_id = f"PW1_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} string 1 power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 1:
                                self._attr_native_value = float(s["pvpower"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 1:
                                # Setup state
                                value = float(s["pvpower"])

        return value

class ESolarInverterPW2(ESolarSensor):
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
        self._attr_unique_id = f"PW2_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} string 2 power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 2:
                                self._attr_native_value = float(s["pvpower"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 2:
                                # Setup state
                                value = float(s["pvpower"])
        return value

class ESolarInverterPW3(ESolarSensor):
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
        self._attr_unique_id = f"PW3_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} string 3 power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 3:
                                self._attr_native_value = float(s["pvpower"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == 3:
                                # Setup state
                                value = float(s["pvpower"])

        return value


class ESolarInverterGV1(ESolarSensor):
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
        self._attr_unique_id = f"GV1r_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_GRID_IMPORT
        self._attr_name = f"Inverter {inverter_sn} GV1r"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 1:
                                self._attr_native_value = float(s["gridVolt"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 1:
                                # Setup state
                                value = float(s["gridVolt"])

        return value


class ESolarInverterGV2(ESolarSensor):
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
        self._attr_unique_id = f"GV2s_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_GRID_IMPORT
        self._attr_name = f"Inverter {inverter_sn} GV2s"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 2:
                                self._attr_native_value = float(s["gridVolt"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 2:
                                # Setup state
                                value = float(s["gridVolt"])

        return value


class ESolarInverterGV3(ESolarSensor):
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
        self._attr_unique_id = f"GV3t_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_GRID_IMPORT
        self._attr_name = f"Inverter {inverter_sn} GV3t"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 3:
                                self._attr_native_value = float(s["gridVolt"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 3:
                                # Setup state
                                value = float(s["gridVolt"])

        return value


class ESolarInverterGC1(ESolarSensor):
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
        self._attr_unique_id = f"GC1s_{inverter_sn}" #typo :( correct: GC1r_

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_GRID_EXPORT
        self._attr_name = f"Inverter {inverter_sn} GC1r"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 1:
                                self._attr_native_value = float(s["gridCurr"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 1:
                                # Setup state
                                value = float(s["gridCurr"])

        return value


class ESolarInverterGC2(ESolarSensor):
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
        self._attr_unique_id = f"GC2s_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_GRID_EXPORT
        self._attr_name = f"Inverter {inverter_sn} GC2s"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 2:
                                self._attr_native_value = float(s["gridCurr"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 2:
                                # Setup state
                                value = float(s["gridCurr"])

        return value


class ESolarInverterGC3(ESolarSensor):
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
        self._attr_unique_id = f"GC3t_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_GRID_EXPORT
        self._attr_name = f"Inverter {inverter_sn} GC3t"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 3:
                                self._attr_native_value = float(s["gridCurr"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == 3:
                                # Setup state
                                value = float(s["gridCurr"])

        return value

class ESolarInverterTemperature(ESolarSensor):
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
        self._attr_native_value = None
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Temp_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self.inverter_sn = inverter_sn

        self._attr_icon = ICON_THERMOMETER
        self._attr_name = f"Inverter {inverter_sn} Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self.inverter_sn:
                            continue
                        if -200 < float(kit["raw"]["deviceTemp"]) < 200:
                            # Setup state
                            self._attr_native_value = float(kit["raw"]["deviceTemp"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            # Setup dynamic attributes
            if "devices" not in plant or plant["devices"] is None:
                continue
            for kit in plant["devices"]:
                if kit["deviceSn"] != self.inverter_sn:
                    continue
                if -200 < float(kit["raw"]["deviceTemp"]) < 200:
                    # Setup state
                    value = float(kit["raw"]["deviceTemp"])

        return value
