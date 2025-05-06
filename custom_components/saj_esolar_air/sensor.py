"""Support for ESolar sensors."""
from __future__ import annotations
import time
import datetime
from datetime import timedelta, datetime
import re
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
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import ESolarCoordinator
from .const import (
    B_TODAY_CHARGE_E,
    B_TODAY_DISCHARGE_E,
    B_TOTAL_CHARGE_E,
    B_TOTAL_DISCHARGE_E,
    CONF_INVERTER_SENSORS,
    CONF_MONITORED_SITES,
    CONF_PV_GRID_DATA,
    DOMAIN,
    MANUFACTURER,
    P_CO2,
    P_TREES,
    P_UID,
    PLANT_MODEL,
    P_ADR,
    P_LATITUDE,
    P_LONGITUDE,
    P_PIC,
    P_DPC,
    P_DEVICE_TYPE,
    P_DISPLAY_FW,
    P_INSTALL_NAME,
    P_FIRST_ONLINE,
    P_MASTER_MCU_FW,
    P_MODULE_FW,
    P_MODULE_PC,
    P_MODULE_SN,
    P_OWNER_NAME,
    P_OWNER_EMAIL,
    P_NO,
    P_ID,
    P_NAME,
    I_MODEL,
    I_SN,
    B_CAPACITY,
    B_CURRENT,
    B_POWER,
    B_DIRECTION,
    G_POWER,
    B_GRID_DIRECT,
    IO_POWER,
    IO_DIRECTION,
    PV_POWER,
    PV_DIRECTION,
    B_T_LOAD,
    B_H_LOAD,
    B_B_LOAD,
    S_POWER,
    B_DIR_STB,
    B_DIR_DIS,
    B_DIR_CH,
    P_UNKNOWN,
    B_EXPORT,
    B_IMPORT,
    P_TODAY_ALARM_NUM,
    P_GRID_AC1,
    P_GRID_AC2,
    P_GRID_AC3,
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
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)

def is_float_and_not_int(num):
    return isinstance(num, float) and not isinstance(num, int)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eSolar sensor."""
    coordinator: ESolarCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[ESolarSensor] = []
    esolar_data: dict = coordinator.data
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
                ESolarSensorPlant(coordinator, plant["plantName"], plant["plantUid"], use_pv_grid_attributes)
            )
            # Type enum:
            #  0 - plant with PV inverter only
            #  1 - Plant with PV inverter and battery
            #  2 - ???
            #  3 - Plant with battery only
            
            if plant["type"] in [0,1,2]:
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
                entities.append(
                    ESolarSensorPlantTodayEquivalentHours( coordinator, plant["plantName"], plant["plantUid"] )
                )

            # if plant["type"] in [1,2,3] and (("hasBattery" in plant and plant["hasBattery"] == 1) or "hasBattery" not in plant):
            #     sources = ["todayBuyEnergy", "todayChargeEnergy", "todayDisChargeEnergy", "todayLoadEnergy", "todaySellEnergy",
            #                "totalBuyEnergy", "totalChargeEnergy", "totalDisChargeEnergy", "totalLoadEnergy", "totalSellEnergy",
            #                "yearBuyEnergy", "yearBatChgEnergy", "yearBatDischgEnergy", "yearLoadEnergy", "yearSellEnergy",
            #                "monthBuyEnergy", "monthBatChgEnergy", "monthBatDischgEnergy", "monthLoadEnergy", "monthSellEnergy",
            #                ]

            #     _LOGGER.debug(
            #         "Setting up ESolarSensorPlantBattery sensors for %s",
            #         plant["plantName"],
            #     )
            #     for source in sources:
            #         if source in plant and plant[source] is not None and is_float_and_not_int(plant[source]):
            #             entities.append(
            #                 ESolarSensorPlantEnergy(
            #                     coordinator, plant["plantName"], plant["plantUid"], source
            #                 )
            #             )

            #     _LOGGER.debug(
            #         "Setting up ESolarSensorPlantBatterySoC sensor for %s",
            #         plant["plantName"],
            #     )
            #     entities.append(
            #         ESolarSensorPlantBatterySoC(
            #             coordinator, plant["plantName"], plant["plantUid"]
            #         )
            #     )

            if use_inverter_sensors and plant["type"] in [0,1,2]:
                for device in plant["deviceSnList"]:
                    _LOGGER.debug(
                        "Setting up ESolarInverterEnergyTotal sensor for %s and device %s",
                        plant["plantName"],
                        device,
                    )
                    entities.append(
                        ESolarInverterEnergyTotal( coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverterPower sensor for %s and device %s",
                        plant["plantName"],
                        device,
                    )
                    entities.append(
                        ESolarInverterPower( coordinator, plant["plantName"], plant["plantUid"], device, use_pv_grid_attributes)
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverter other sensors for %s and device %s",
                        plant["plantName"],
                        device,
                    )

                    for kit in plant["devices"]:
                        if kit["deviceSn"] == device:
                            if "pvList" in kit["deviceStatisticsData"]:
                                for pv in kit["deviceStatisticsData"]["pvList"]:
                                    entities.append(
                                        ESolarInverterPV( coordinator, plant["plantName"], plant["plantUid"], device, pv['pvNo'])
                                    )
                                    entities.append(
                                        ESolarInverterPC(coordinator, plant["plantName"], plant["plantUid"], device, pv['pvNo'])
                                    )
                                    entities.append(
                                        ESolarInverterPW(coordinator, plant["plantName"], plant["plantUid"], device, pv['pvNo'])
                                    )

                    entities.append(
                        ESolarInverterEnergyToday(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    entities.append(
                        ESolarInverterEnergyMonth(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    entities.append(
                        ESolarInverterTemperature(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    entities.append(
                        ESolarSensorInverterTodayAlarmNum(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    entities.append(
                        ESolarSensorInverterPeakPower( coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    
            if use_inverter_sensors and plant["type"] in [1,2,3] :
                for device_sn in plant["deviceSnList"]:
                    for device in plant["devices"]:
                        if device["deviceSn"] == device_sn:
                            if ("hasBattery" in device and device["hasBattery"] == 1) or "hasBattery" not in device:
                                _LOGGER.debug(
                                    "Setting up ESolarInverterBatterySoC sensor for %s and device %s.",
                                    plant["plantName"],
                                    device_sn,
                                )
                                entities.append(
                                    ESolarInverterBatterySoC(
                                        coordinator,
                                        plant["plantName"],
                                        plant["plantUid"],
                                        device_sn,
                                    )
                                )

            if use_pv_grid_attributes: # in all types
                for device_sn in plant["deviceSnList"]:
                    for device in plant["devices"]:
                        if device["deviceSn"] == device_sn:
                            if "gridList" in device["deviceStatisticsData"]:
                                for grid in device["deviceStatisticsData"]["gridList"]:
                                    entities.append(
                                        ESolarInverterGV(coordinator, plant["plantName"], plant["plantUid"], device_sn, grid["gridNo"])
                                    )
                                    entities.append(
                                        ESolarInverterGC(coordinator, plant["plantName"], plant["plantUid"], device_sn, grid["gridNo"])
                                    )
                            entities.append(
                                ESolarInverterGridPowerWatt(coordinator, plant["plantName"], plant["plantUid"], device_sn)
                            )
    async_add_entities(entities, True)


class ESolarSensor(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn = None) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._inverter_sn = inverter_sn

        self._device_name: None | str = None
        self._device_model: None | str = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""
        plant_no = None
        plant_id = None
        plant_owner = None
        plant_owner_email = None

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                plant_no = plant["plantNo"]
                plant_id = plant["plantId"]
                plant_owner = plant["ownerName"]
                plant_owner_email = plant["ownerEmail"]

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            identifiers={
                (DOMAIN, self._plant_name),
                (P_NO, plant_no),
                (P_ID, plant_id),
                (P_OWNER_NAME, plant_owner),
                (P_OWNER_EMAIL, plant_owner_email)
            }
        )
        return device_info


class ESolarSensorPlant(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, use_pv_grid_attributes) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._use_pv_grid_attributes = use_pv_grid_attributes
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_PANEL
        self._attr_name = f"Plant {self._plant_name} Status"
        self._attr_native_value = None

        self._attr_extra_state_attributes = {
            P_UID: None,
            P_CO2: None,
            P_TREES: None,
            P_LATITUDE: None,
            P_LONGITUDE: None,
            P_PIC: None,
            P_ADR: None,
            P_FIRST_ONLINE: None,
            P_OWNER_NAME: None,
            P_OWNER_EMAIL: None,
            P_NO: None,
            P_ID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # if self._use_pv_grid_attributes:
                #     self._attr_extra_state_attributes['Original data'] = plant

                self._attr_extra_state_attributes[P_UID] = plant["plantUid"]
                self._attr_extra_state_attributes[P_CO2] = plant["totalReduceCo2"]
                self._attr_extra_state_attributes[P_TREES] = plant["totalPlantTreeNum"]
                self._attr_extra_state_attributes[P_LATITUDE] = plant["latitude"]
                self._attr_extra_state_attributes[P_LONGITUDE] = plant["longitude"]
                self._attr_extra_state_attributes[P_PIC] = plant["plantLogo"]
                self._attr_extra_state_attributes[P_ADR] = plant["fullAddress"]
                self._attr_extra_state_attributes[P_FIRST_ONLINE] = plant["createDate"]
                self._attr_extra_state_attributes[P_NO] = plant["plantNo"]
                self._attr_extra_state_attributes[P_ID] = plant["plantId"]
                self._attr_extra_state_attributes[P_OWNER_NAME] = plant['ownerName']
                self._attr_extra_state_attributes[P_OWNER_EMAIL] = plant['ownerEmail']

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
                # Set up dynamic attributes
                # if self._use_pv_grid_attributes:
                #     self._attr_extra_state_attributes['Original data'] = plant
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
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True

                # Setup state
                if float(plant["totalPvEnergy"]) > 0.0:
                    self._attr_native_value = float(plant["totalPvEnergy"])
                elif  float(plant["totalEnergy"]) > 0.0:
                    self._attr_native_value = float(plant["totalEnergy"])
                else:
                    self._attr_available = False

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                if float(plant["totalPvEnergy"]) > 0.0:
                    value = float(plant["totalPvEnergy"])
                elif float(plant["totalEnergy"]) > 0.0:
                    value = float(plant["totalEnergy"])

        return value

class ESolarSensorPlantTodayEnergy(ESolarSensor):
    """Representation of a Saj eSolar sensor for the plant."""

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
        self._attr_native_value = None

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
        self._attr_native_value = None

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
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if "isParallel" in plant and plant["isParallel"] == 1:
                    self._attr_native_value = float(plant["yearPvEnergy"])
                else:
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
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = float(plant["peakPower"])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                value = float(plant["peakPower"])

        return value


def extract_date(date_str):
    try:
        date_obj = datetime.strptime(date_str + " " + time.strftime('%z'),"%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        try:
            date_obj =  datetime.strptime(date_str + " " + time.strftime('%z'), "%d/%m/%Y %H:%M:%S %z")
        except ValueError:
            return None

    # Az aktuális időpont meghatározása
    now = datetime.now(date_obj.tzinfo)  # Az időzónát megtartjuk

    # Határok: Egy évvel ezelőtti dátum és egy nappal előre engedett időpont
    one_year_ago = now - timedelta(days=365)
    one_day_ahead = now + timedelta(days=1)

    # Ellenőrzés
    if one_year_ago <= date_obj <= one_day_ahead:
        return date_obj
    else:
        print("Érvénytelen dátum: "+date_str)
        return None


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
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if "dataTime" in plant and plant["dataTime"] is not None:
                    self._attr_native_value = extract_date(plant["dataTime"])

                if self._attr_native_value is None and "updateDate" in plant and plant["updateDate"] is not None:
                    self._attr_native_value = extract_date(plant["updateDate"])

                if self._attr_native_value is None and "dataTime" in plant["devices"][0] and plant["devices"][0]["deviceStatisticsData"]["dataTime"] is not None:
                    self._attr_native_value = extract_date(plant["devices"][0]["deviceStatisticsData"]["dataTime"])

                if self._attr_native_value is None and "updateDate" in plant["devices"][0] and plant["devices"][0]["deviceStatisticsData"]["updateDate"] is not None:
                    self._attr_native_value = extract_date(plant["devices"][0]["deviceStatisticsData"]["updateDate"])


    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                if "dataTime" in plant and plant["dataTime"] is not None:
                    value = extract_date(plant["dataTime"])

                if value is None and "updateDate" in plant and plant["updateDate"] is not None:
                    value = extract_date(plant["updateDate"])

                if value is None and "dataTime" in plant["devices"][0] and plant["devices"][0]["deviceStatisticsData"]["dataTime"] is not None:
                    value = extract_date(plant["devices"][0]["deviceStatisticsData"]["dataTime"])

                if value is None and "updateDate" in plant["devices"][0] and plant["devices"][0]["updateDate"] is not None:
                    value = extract_date(plant["devices"][0]["deviceStatisticsData"]["updateDate"])

        return value

class ESolarSensorPlantTodayEquivalentHours(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_todayEquivalentHours_{plant_uid}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_UPDATE
        self._attr_name = f"Plant {self._plant_name} today Equivalent Hours"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = 'h'
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if "todayEquivalentHours" and plant["todayEquivalentHours"] is not None and float(plant["todayEquivalentHours"]) > 0.0:
                    self._attr_native_value = float(plant["todayEquivalentHours"])
                else:
                    total_hours = 0.0
                    for device in plant["devices"]:
                        if "todayEquivalentHours" in device and device["todayEquivalentHours"] is not None and float(device["todayEquivalentHours"]) > 0.0:
                            total_hours += float(device["todayEquivalentHours"])
                    self._attr_native_value = total_hours

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                if "todayEquivalentHours" and plant["todayEquivalentHours"] is not None and float(
                        plant["todayEquivalentHours"]) > 0.0:
                    value = float(plant["todayEquivalentHours"])
                else:
                    total_hours = 0.0
                    for device in plant["devices"]:
                        if "todayEquivalentHours" in device and device["todayEquivalentHours"] is not None and float(
                                device["todayEquivalentHours"]) > 0.0:
                            total_hours += float(device["todayEquivalentHours"])
                    value = total_hours

        return value


class ESolarSensorInverterPeakPower(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"Inverter_{self._inverter_sn}_peakpower"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {self._inverter_sn} Peak Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None
        self._previous_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if plant["type"] == 0:
                    peak_power = self._attr_native_value or self.coordinator.hass.states.get(self._attr_unique_id) or float(0.0)
                    for kit in plant["devices"]:
                        if (kit['deviceSn'] == self._inverter_sn
                                and kit['deviceStatisticsData'] is not None
                                and kit['deviceStatisticsData']['powerNow'] is not None):
                            peak_power = max(peak_power, float(kit['deviceStatisticsData']['powerNow']))
                    self._attr_native_value = float(peak_power)

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        return self._attr_native_value


class ESolarSensorInverterTodayAlarmNum(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}_todayAlarmNum"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_ALARM
        self._attr_name = f"Inverter {inverter_sn} Today Alarm Num"
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_value = 0

        self._attr_extra_state_attributes = {
            P_TODAY_ALARM_NUM : None
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_TODAY_ALARM_NUM] = plant["todayAlarmNum"]

                if "devices" not in plant or plant["devices"] is None:
                    continue
                for kit in plant["devices"]:
                    if kit["deviceSn"] == self._inverter_sn:
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
                for kit in plant["devices"]:
                    if kit["deviceSn"] == self._inverter_sn:
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
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}_energy_total"
        self._inverter_sn = inverter_sn

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
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        self._attr_available = True
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
                    if kit["deviceSn"] != self._inverter_sn:
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
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}_today"
        self._inverter_sn = inverter_sn

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Inverter {inverter_sn} Energy Today"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self._inverter_sn:
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
                    if kit["deviceSn"] != self._inverter_sn:
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
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}_month"
        self._inverter_sn = inverter_sn

        self._device_name = plant_name
        self._device_model = PLANT_MODEL

        self._attr_icon = ICON_METER
        self._attr_name = f"Inverter {inverter_sn} Energy Month"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self._inverter_sn:
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
                    if kit["deviceSn"] != self._inverter_sn:
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
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self.use_pv_grid_attributes = use_pv_grid_attributes
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"PW_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None

        self._attr_extra_state_attributes = {
            P_DPC: None,
            P_DEVICE_TYPE: None,
            P_DISPLAY_FW: None,
            P_INSTALL_NAME: None,
            P_MASTER_MCU_FW: None,
            P_MODULE_FW: None,
            P_MODULE_PC: None,
            P_MODULE_SN: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        # Setup state
                        self._attr_native_value = float(kit["deviceStatisticsData"]["powerNow"])
                        self._attr_extra_state_attributes[P_DPC] = kit['devicePc']
                        self._attr_extra_state_attributes[P_DEVICE_TYPE] = kit['deviceType']
                        self._attr_extra_state_attributes[P_DISPLAY_FW] = kit['displayFw']
                        self._attr_extra_state_attributes[P_INSTALL_NAME] = kit['installName']
                        self._attr_extra_state_attributes[P_MASTER_MCU_FW] = kit['masterMCUFw']
                        self._attr_extra_state_attributes[P_MODULE_FW] = kit['moduleFw']
                        self._attr_extra_state_attributes[P_MODULE_PC] = kit['modulePc']
                        self._attr_extra_state_attributes[P_MODULE_SN] = kit['moduleSn']

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
                    if kit["deviceSn"] != self._inverter_sn:
                        continue
                    # Setup state
                    value = float(kit["deviceStatisticsData"]["powerNow"])

        return value


class ESolarInverterPV(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
        pv_string
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"PV{pv_string}_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn
        self._pv_string = pv_string

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PV{pv_string}"
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
                                value = float(s["pvvolt"])

        return value

class ESolarInverterPC(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
        pv_string
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"PC{pv_string}_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn
        self._pv_string = pv_string

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PC{pv_string}"
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
                                # Setup state
                                value = float(s["pvcurr"])

        return value

class ESolarInverterPW(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
        pv_string
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"PW{pv_string}_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn
        self._pv_string = pv_string

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} string {pv_string} power"
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
                                # Setup state
                                value = float(s["pvpower"])

        return value

class ESolarInverterGridPowerWatt(ESolarSensor):
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
        self._attr_unique_id = f"Grid_Power_watt_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} grid power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

        self._attr_extra_state_attributes = {
            P_GRID_AC1: None,
            P_GRID_AC2: None,
            P_GRID_AC3: None
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        grid_power_watt = 0
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s['gridPowerwatt'] is not None:
                                grid_power_watt += float(s['gridPowerwatt'])
                                if "gridName" in s and s["gridName"] is not None:
                                    if s["gridName"] in [P_GRID_AC1, P_GRID_AC2, P_GRID_AC3]:
                                        self._attr_extra_state_attributes[ s["gridName"] ] = s['gridPowerwatt']
                        self._attr_native_value = grid_power_watt

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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        grid_power_watt = 0
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s['gridPowerwatt'] is not None:
                                grid_power_watt += float(s['gridPowerwatt'])
                                if "gridName" in s and s["gridName"] is not None:
                                    if s["gridName"] in [P_GRID_AC1, P_GRID_AC2, P_GRID_AC3]:
                                        self._attr_extra_state_attributes[s["gridName"]] = s['gridPowerwatt']
                        value = grid_power_watt

        return value


class ESolarInverterGV(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
        phase
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        letters = ["r", "s", "t"]
        letter= ''
        if 1 <= phase <= 3:
            letter= letters[phase-1]

        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"GV{phase}{letter}_{inverter_sn}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn
        self._phase = phase

        self._attr_icon = ICON_GRID_IMPORT
        self._attr_name = f"Inverter {inverter_sn} GV{phase}{letter}"
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == self._phase:
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == self._phase:
                                # Setup state
                                value = float(s["gridVolt"])

        return value

class ESolarInverterGC(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn,
        phase
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        letters = ["r", "s", "t"]
        letter = ''
        if 1 <= phase <= 3:
            letter = letters[phase - 1]

        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"GC{phase}{letter}_{inverter_sn}" #typo :( correct: GC1r_

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._inverter_sn = inverter_sn
        self._phase = phase

        self._attr_icon = ICON_GRID_EXPORT
        self._attr_name = f"Inverter {inverter_sn} GC{phase}{letter}"
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == self._phase:
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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["gridList"]:
                            if s["gridNo"] == self._phase:
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
        self._inverter_sn = inverter_sn

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
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        if 'raw' in kit and 'deviceTemp' in kit['raw'] and -200 < float(kit["raw"]["deviceTemp"]) < 200:
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
                if kit["deviceSn"] != self._inverter_sn:
                    continue
                if 'raw' in kit and 'deviceTemp' in kit['raw'] and  -200 < float(kit["raw"]["deviceTemp"]) < 200:
                    # Setup state
                    value = float(kit["raw"]["deviceTemp"])

        return value


### Battery entities
def split_camel_case(s):
    # Ha az első karakter kisbetű, akkor hozzáadjuk külön
    s = s[0].upper() + s[1:] if s else s
    words = re.findall(r'[A-Z][a-z]*|[a-z]+', s)  # Felbontás kis- és nagybetűkre
    return ' '.join(word.capitalize() for word in words)


class ESolarSensorPlantEnergy(ESolarSensor):
    """Representation of a eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, source) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_{plant_uid}_{source}"

        self._device_name = plant_name
        self._device_model = PLANT_MODEL
        self._source = source

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} "+split_camel_case(source)
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

                # Setup state
                if self._source in plant and plant[self._source] is not None:
                    self._attr_native_value = float(plant[self._source])

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup state
                if self._source in plant and plant[self._source] is not None:
                    value = float(plant[self._source])

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
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        installed = float(0)
        available = float(0)
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            # Setup static attributes
            self._attr_available = True
            self._attr_extra_state_attributes[P_NAME] = plant["plantName"]
            self._attr_extra_state_attributes[P_UID] = plant["plantUid"]

            # Setup state
            for kit in plant["devices"]:
                if "deviceStatisticsData" not in kit:
                    continue

                bat_capacity = 0.0
                if "batCapacity" in kit["deviceStatisticsData"] and kit["deviceStatisticsData"]["batCapacity"] is not None and float(kit["deviceStatisticsData"]["batCapacity"]) > 0:
                    bat_capacity = float(kit["deviceStatisticsData"]["batCapacity"])
                elif "batCapcity" in kit["deviceStatisticsData"] and kit["deviceStatisticsData"]["batCapcity"] is not None and float(kit["deviceStatisticsData"]["batCapcity"]) > 0:
                    bat_capacity = float(kit["deviceStatisticsData"]["batCapcity"])

                installed += bat_capacity
                available += float( bat_capacity * kit["deviceStatisticsData"]["batEnergyPercent"])

            if installed > 0:
                self._attr_native_value = float(available / installed)

    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        value = None
        installed = float(0)
        available = float(0)
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            # Setup state
            for kit in plant["devices"]:
                if "deviceStatisticsData" not in kit:
                    continue

                bat_capacity = 0.0
                if "batCapacity" in kit["deviceStatisticsData"] and kit["deviceStatisticsData"][
                    "batCapacity"] is not None and float(kit["deviceStatisticsData"]["batCapacity"]) > 0:
                    bat_capacity = float(kit["deviceStatisticsData"]["batCapacity"])
                elif "batCapcity" in kit["deviceStatisticsData"] and kit["deviceStatisticsData"][
                    "batCapcity"] is not None and float(kit["deviceStatisticsData"]["batCapcity"]) > 0:
                    bat_capacity = float(kit["deviceStatisticsData"]["batCapcity"])

                installed += bat_capacity
                available += float(bat_capacity * kit["deviceStatisticsData"]["batEnergyPercent"])

            if installed > 0:
                value = float(available / installed)

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
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
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
            B_TODAY_CHARGE_E: None,
            B_TODAY_DISCHARGE_E : None,
            B_TOTAL_CHARGE_E: None,
            B_TOTAL_DISCHARGE_E : None,
        }

    async def async_update(self) -> None:
        """Get the latest data and updates the states."""
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            # Setup static attributes
            self._attr_available = True
            self._attr_extra_state_attributes[P_NAME] = plant["plantName"]
            self._attr_extra_state_attributes[P_UID] = plant["plantUid"]
            if "devices" not in plant or plant["devices"] is None:
                continue
            for kit in plant["devices"]:
                if kit["deviceSn"] == self.inverter_sn:
                    self._attr_extra_state_attributes[I_MODEL] = kit["deviceType"]
                    self._attr_extra_state_attributes[I_SN] = kit["deviceSn"]
                    self._attr_extra_state_attributes[B_CAPACITY] = kit["deviceStatisticsData"]["batCapcity"]
                    self._attr_native_value = float(kit["deviceStatisticsData"]["batEnergyPercent"])


    @property
    def native_value(self) -> float | None:
        """Return sensor state."""
        # Setup state
        value = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" not in plant or plant["devices"] is None:
                continue
            for kit in plant["devices"]:
                if kit["deviceSn"] == self.inverter_sn:
                    value = float(kit["deviceStatisticsData"]["batEnergyPercent"])

                    # Setup dynamic attributes
                    self._attr_extra_state_attributes[B_CURRENT] = kit["deviceStatisticsData"]["batCurrent"]
                    self._attr_extra_state_attributes[B_POWER] = kit["deviceStatisticsData"]["batPower"]
                    self._attr_extra_state_attributes[B_T_LOAD] = kit["deviceStatisticsData"]["totalLoadPowerwatt"]
                    self._attr_extra_state_attributes[B_TODAY_CHARGE_E] = float(kit["deviceStatisticsData"]["todayBatChgEnergy"]) * 1000
                    self._attr_extra_state_attributes[B_TODAY_DISCHARGE_E] = float(kit["deviceStatisticsData"]["todayBatDisEnergy"]) * 1000
                    self._attr_extra_state_attributes[B_TOTAL_CHARGE_E] = float(kit["deviceStatisticsData"]["totalBatChgEnergy"]) * 1000
                    self._attr_extra_state_attributes[B_TOTAL_CHARGE_E] = float(kit["deviceStatisticsData"]["totalBatDisEnergy"]) * 1000
                    # self._attr_extra_state_attributes[B_H_LOAD] = plant["homeLoadPower"] # ???
                    if "backupTotalLoadPowerWatt" in kit and kit["backupTotalLoadPowerWatt"] is not None:
                        self._attr_extra_state_attributes[B_B_LOAD] = kit["deviceStatisticsData"]["backupTotalLoadPowerWatt"]
                    elif "backupTotalLoadPowerWatt" in kit["raw"] and kit["raw"]["backupTotalLoadPowerWatt"] is not None:
                        self._attr_extra_state_attributes[B_B_LOAD] = kit["raw"]["backupTotalLoadPowerWatt"]
                    else:
                        self._attr_extra_state_attributes[B_B_LOAD] = None


            if plant["batteryDirection"] == 0:
                self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_STB
            elif plant["batteryDirection"] == 1:
                self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_DIS
            elif plant["batteryDirection"] == -1:
                self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_CH
            else:
                self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN

            grid_power_watt = 0
            if plant["devices"] is not None:
                for kit in plant["devices"]:
                    if "gridList" in kit and kit["gridList"] is not None:
                        for grid in kit["gridList"]:
                            if grid['gridPowerwatt'] is not None:
                                grid_power_watt += float(grid['gridPowerwatt'])
            self._attr_extra_state_attributes[G_POWER] = grid_power_watt

            if "gridDirection" in plant and plant["gridDirection"] is not None:
                if plant["gridDirection"] == 1:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = B_EXPORT
                elif plant["gridDirection"] == -1:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = B_IMPORT
                else:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN

            # ???
            # self._attr_extra_state_attributes[IO_POWER] = kit[
            #     "storeDevicePower"
            # ]["inputOutputPower"]

            if "outPutDirection" in plant and plant["outPutDirection"] is not None:
                if plant["outPutDirection"] == 1:
                    self._attr_extra_state_attributes[IO_DIRECTION] = B_EXPORT
                elif plant["outPutDirection"] == -1:
                    self._attr_extra_state_attributes[IO_DIRECTION] = B_IMPORT
                else:
                    self._attr_extra_state_attributes[IO_DIRECTION] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[IO_DIRECTION] = P_UNKNOWN

            self._attr_extra_state_attributes[PV_POWER] = plant["totalPvPower"]

            if "pvDirection" in plant and plant["pvDirection"] is not None:
                if plant["pvDirection"] == 1:
                    self._attr_extra_state_attributes[PV_DIRECTION] = B_EXPORT
                elif plant["pvDirection"] == -1:
                    self._attr_extra_state_attributes[PV_DIRECTION] = B_IMPORT
                else:
                    self._attr_extra_state_attributes[PV_DIRECTION] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[PV_DIRECTION] = P_UNKNOWN

            self._attr_extra_state_attributes[S_POWER] = plant["solarPower"]

        return value