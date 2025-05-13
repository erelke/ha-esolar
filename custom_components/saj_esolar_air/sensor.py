"""Support for ESolar sensors."""
from __future__ import annotations
import datetime
from datetime import timedelta, datetime
import pytz
import logging
from .elekeeper import extract_number, split_camel_case, extract_date
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import ESolarCoordinator
from .const import (
    CONF_INVERTER_SENSORS,
    CONF_MONITORED_SITES,
    CONF_PV_GRID_DATA,
    DOMAIN,
    MANUFACTURER,
    P_CO2, P_COAL, P_TREES,
    P_YCO2, P_YCOAL, P_YTREES,
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
    P_GRID_AC3, I_TODAY, I_YESTERDAY, I_MONTH, I_LAST_MONTH, I_TOTAL, EH_TODAY, EH_TOTAL, I_PC,
    B_TODAY_CHARGE_E,
    B_TODAY_DISCHARGE_E,
    B_TOTAL_CHARGE_E,
    B_TOTAL_DISCHARGE_E, DEVICE_MODEL, METER_MODEL, MODULE_SN, MODULE_SIGN
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

_LOGGER = logging.getLogger(__name__)

def is_float_and_not_int(num):
    return isinstance(num, float) and not isinstance(num, int)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eSolar sensor."""
    coordinator: ESolarCoordinator = hass.data[DOMAIN][entry.entry_id]
    plant_entities: list[ESolarPlant] = []
    device_entities: list[ESolarDevice] = []
    meter_entities: list[ESolarMeter] = []
    bat_entities: list[ESolarBattery] = []
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
            plant_entities.append(
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
                plant_entities.append(
                    ESolarSensorPlantTotalEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                plant_entities.append(
                    ESolarSensorPlantTodayEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                plant_entities.append(
                    ESolarSensorPlantMonthEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                plant_entities.append(
                    ESolarSensorPlantYearEnergy( coordinator, plant["plantName"], plant["plantUid"] )
                )
                plant_entities.append(
                    ESolarSensorPlantPeakPower( coordinator, plant["plantName"], plant["plantUid"] )
                )
                plant_entities.append(
                    ESolarSensorPlantLastUploadTime( coordinator, plant["plantName"], plant["plantUid"] )
                )
                plant_entities.append(
                    ESolarSensorPlantTodayEquivalentHours( coordinator, plant["plantName"], plant["plantUid"] )
                )


            if plant["type"] in [1,2,3] and (("hasBattery" in plant and plant["hasBattery"] == 1) or "hasBattery" not in plant):
                sources = ["todayBuyEnergy", "todayChargeEnergy", "todayDisChargeEnergy", "todayLoadEnergy", "todaySellEnergy",
                           "totalBuyEnergy", "totalChargeEnergy", "totalDisChargeEnergy", "totalLoadEnergy", "totalSellEnergy",
                           "yearBuyEnergy", "yearBatChgEnergy", "yearBatDischgEnergy", "yearLoadEnergy", "yearSellEnergy",
                           "monthBuyEnergy", "monthBatChgEnergy", "monthBatDischgEnergy", "monthLoadEnergy", "monthSellEnergy",
                           ]

                _LOGGER.debug(
                    "Setting up ESolarSensorPlantBatterySoC sensor for %s",
                    plant["plantName"],
                )
                plant_entities.append(
                    ESolarSensorPlantBatterySoC(
                        coordinator, plant["plantName"], plant["plantUid"]
                    )
                )

            elif plant["type"] in [0,1,2] and "isInstallMeter" in plant and plant["isInstallMeter"] == 1:
                sources = ["todayBuyEnergy", "todayLoadEnergy", "todaySellEnergy",
                           "totalBuyEnergy", "totalLoadEnergy", "totalSellEnergy",
                           "yearBuyEnergy", "yearLoadEnergy", "yearSellEnergy",
                           "monthBuyEnergy", "monthLoadEnergy", "monthSellEnergy",
                           ]
            else:
                # Their value is the same as *PvEnergy if we don't have meter
                # sources = ["todaySellEnergy", "totalSellEnergy", "yearSellEnergy", "monthSellEnergy"]
                sources = []


            for source in sources:
                if source in plant and plant[source] is not None and is_float_and_not_int(plant[source]):
                    _LOGGER.debug(
                        "Setting up ESolarSensorPlantEnergy-%s sensors for %s",
                        source,
                        plant["plantName"],
                    )
                    plant_entities.append(
                        ESolarSensorPlantEnergy(
                            coordinator, plant["plantName"], plant["plantUid"], source
                        )
                    )


            if use_inverter_sensors and plant["type"] in [0,1,2]:
                for device in plant["deviceSnList"]:
                    _LOGGER.debug(
                        "Setting up ESolarInverterEnergyTotal sensor for %s and device %s",
                        plant["plantName"],
                        device,
                    )
                    device_entities.append(
                        ESolarInverterEnergyTotal( coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    _LOGGER.debug(
                        "Setting up ESolarInverterPower sensor for %s and device %s",
                        plant["plantName"],
                        device,
                    )
                    device_entities.append(
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
                                    device_entities.append(
                                        ESolarInverterPV( coordinator, plant["plantName"], plant["plantUid"], device, pv['pvNo'])
                                    )
                                    device_entities.append(
                                        ESolarInverterPC(coordinator, plant["plantName"], plant["plantUid"], device, pv['pvNo'])
                                    )
                                    device_entities.append(
                                        ESolarInverterPW(coordinator, plant["plantName"], plant["plantUid"], device, pv['pvNo'])
                                    )

                    device_entities.append(
                        ESolarInverterEnergyToday(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
                        ESolarInverterEnergyMonth(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
                        ESolarInverterTemperature(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
                        ESolarSensorInverterTodayAlarmNum(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
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
                                device_entities.append(
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
                                    device_entities.append(
                                        ESolarInverterGV(coordinator, plant["plantName"], plant["plantUid"], device_sn, grid["gridNo"])
                                    )
                                    device_entities.append(
                                        ESolarInverterGC(coordinator, plant["plantName"], plant["plantUid"], device_sn, grid["gridNo"])
                                    )
                            device_entities.append(
                                ESolarInverterGridPowerWatt(coordinator, plant["plantName"], plant["plantUid"], device_sn)
                            )

            if "modules" in plant and plant["modules"] is not None:
                for module in plant["modules"]:
                    if "moduleSn" in module and module["moduleSn"] is not None:
                        _LOGGER.debug(
                            "Setting up ESolarSensorMeterPower-power for %s and module %s",
                            plant["plantName"],
                            module["moduleSn"],
                        )
                        meter_entities.append(
                            ESolarSensorMeterPower( coordinator, plant["plantName"], plant["plantUid"], module["moduleSn"])
                        )

            if "batteries" in plant and plant["batteries"] is not None:
                for battery in plant["batteries"]:
                    if "batSn" in battery and battery["batSn"] is not None:
                        _LOGGER.debug(
                            "Setting up ESolarSensorBatteryEntities for %s and battery %s",
                            plant["plantName"],
                            battery["batSn"],
                        )
                        bat_entities.append(
                            ESolarSensorBatteryEntity( coordinator, plant["plantName"], plant["plantUid"], battery["batSn"], "batSoc", 1)
                        )
                        bat_entities.append(
                            ESolarSensorBatteryEntity( coordinator, plant["plantName"], plant["plantUid"], battery["batSn"], "batTemperature")
                        )
                        bat_entities.append(
                            ESolarSensorBatteryEntity( coordinator, plant["plantName"], plant["plantUid"], battery["batSn"], "batSoh")
                        )

    async_add_entities(plant_entities, True)
    async_add_entities(device_entities, True)
    async_add_entities(meter_entities, True)
    async_add_entities(bat_entities, True)


class ESolarPlant(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar Plant device / sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid

        self._device_name: None | str = plant_name
        self._device_model: None | str = PLANT_MODEL

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
            serial_number = plant_no,
            identifiers={
                (P_NO, plant_no),
                (P_ID, plant_id),
                (P_OWNER_NAME, plant_owner),
                (P_OWNER_EMAIL, plant_owner_email),
                (P_UID, self._plant_uid)
            }
        )
        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        self.process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.process_data()
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value


class ESolarDevice(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn = None) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._inverter_sn = inverter_sn

        self._device_name: None | str = inverter_sn
        self._device_model: None | str = DEVICE_MODEL
        self._hw_version: None | str = None
        self._sw_version: None | str = None
        self._device_pc: None | str = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "devices" in plant and plant["devices"] is not None:
                    for device in plant["devices"]:
                        if device["deviceSn"] == self._inverter_sn:
                            self._device_model = device["deviceModel"] or None
                            self._hw_version = device["masterMCUFw"] or None
                            self._sw_version = device["displayFw"] or None
                            self._device_name = device["aliases"] or device["deviceSn"] or None
                            self._device_pc = device["devicePc"] or None

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._inverter_sn,
            hw_version=self._hw_version,
            sw_version=self._sw_version,
            identifiers={
                (I_SN, self._inverter_sn),
                (I_PC, self._device_pc),
            }
        )
        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        self.process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.process_data()
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value


class ESolarMeter(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, module_sn = None) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._module_sn = module_sn

        self._device_name: None | str = module_sn
        self._device_model: None | str = METER_MODEL
        self._sw_version: None | str = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "modules" in plant and plant["modules"] is not None:
                    for module in plant["modules"]:
                        if module["moduleSn"] == self._module_sn:
                            self._device_model = module["moduleModel"] or None
                            self._sw_version = module["moduleFw"] or None
                            break

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._module_sn,
            sw_version=self._sw_version,
            identifiers={
                (MODULE_SN, self._module_sn),
            }
        )

        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        self.process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.process_data()
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value


class ESolarBattery(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, bat_sn = None) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._bat_sn = bat_sn

        self._device_name: None | str = bat_sn
        self._device_model: None | str = METER_MODEL
        self._sw_version: None | str = None
        self._hw_version: None | str = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        bms_sn = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "batteries" in plant and plant["batteries"] is not None:
                    for battery in plant["batteries"]:
                        if battery["batSn"] == self._bat_sn:
                            self._device_model = battery["batModel"] or None
                            self._sw_version = battery["bmsSoftwareVersion"] or None
                            self._hw_version = battery["bmsHardwareVersion"] or None
                            bms_sn = battery["bmsSn"] or None
                            break

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._bat_sn,
            sw_version=self._sw_version,
            hw_version=self._hw_version,
            identifiers={
                (MODULE_SN, self._bat_sn),
                ('BMS_SN', bms_sn),
            }
        )

        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        self.process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.process_data()
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value

#unused yet
class ESolarEMS(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, ems_sn = None) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._ems_sn = ems_sn

        self._device_name: None | str = ems_sn
        self._device_model: None | str = METER_MODEL
        self._sw_version: None | str = None
        self._hw_version: None | str = None
        self._pc: None | str = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "emsModules" in plant and plant["emsModules"] is not None:
                    for ems in plant["emsModules"]:
                        if ems["emsModuleSn"] == self._ems_sn:
                            self._device_name = ems["emsModuleName"] if ems["emsModuleName"] is not None and ems["emsModuleName"] != '--' else ems["emsModuleSn"] or None
                            self._device_model = ems["emsModel"] or None
                            self._sw_version = ems["firmwareVersion"] or None
                            self._hw_version = ems["hardwareVersion"] or None
                            self._pc = ems["emsModulePc"] or None
                            break

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._bat_sn,
            sw_version=self._sw_version,
            hw_version=self._hw_version,
            identifiers={
                (MODULE_SN, self._ems_sn),
                ('PC', self._pc),
            }
        )

        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        self.process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.process_data()
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value


class ESolarSensorPlant(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, use_pv_grid_attributes) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._use_pv_grid_attributes = use_pv_grid_attributes
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_{plant_uid}"

        self._attr_icon = ICON_PANEL
        self._attr_name = f"Plant {self._plant_name} Status"
        self._attr_native_value = None

        self._attr_extra_state_attributes = {
            P_UID: None,
            P_CO2: None,
            P_COAL: None,
            P_TREES: None,
            P_YCO2: None,
            P_YCOAL: None,
            P_YTREES: None,
            P_LATITUDE: None,
            P_LONGITUDE: None,
            P_PIC: None,
            P_ADR: None,
            P_FIRST_ONLINE: None,
            P_OWNER_NAME: None,
            P_OWNER_EMAIL: None,
            P_NO: None,
            P_ID: None,
            S_POWER: None,
        }

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # if self._use_pv_grid_attributes:
                #     self._attr_extra_state_attributes['Original data'] = plant

                self._attr_extra_state_attributes[P_UID] = plant["plantUid"]
                self._attr_extra_state_attributes[P_CO2] = plant["totalReduceCo2"]
                self._attr_extra_state_attributes[P_COAL] = plant["totalCoal"]
                self._attr_extra_state_attributes[P_TREES] = plant["totalPlantTreeNum"]
                self._attr_extra_state_attributes[P_YCO2] = plant["yearReduceCo2"]
                self._attr_extra_state_attributes[P_YCOAL] = plant["yearCoal"]
                self._attr_extra_state_attributes[P_YTREES] = plant["yearPlantTreeNum"]
                self._attr_extra_state_attributes[P_LATITUDE] = plant["latitude"]
                self._attr_extra_state_attributes[P_LONGITUDE] = plant["longitude"]
                self._attr_extra_state_attributes[P_PIC] = plant["plantLogo"]
                self._attr_extra_state_attributes[P_ADR] = plant["fullAddress"]
                self._attr_extra_state_attributes[P_FIRST_ONLINE] = plant["createDate"]
                self._attr_extra_state_attributes[P_NO] = plant["plantNo"]
                self._attr_extra_state_attributes[P_ID] = plant["plantId"]
                self._attr_extra_state_attributes[P_OWNER_NAME] = plant['ownerName']
                self._attr_extra_state_attributes[P_OWNER_EMAIL] = plant['ownerEmail']
                self._attr_extra_state_attributes[S_POWER] = plant['systemPower']

                # Setup state
                if plant["runningState"] == 1:
                    self._attr_native_value = "Normal"
                elif plant["runningState"] == 2:
                    self._attr_native_value = "Alarm"
                elif plant["runningState"] == 3:
                    self._attr_native_value = "Offline"
                else:
                    self._attr_native_value = None


class ESolarSensorPlantTotalEnergy(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}"

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Energy Total "
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            I_TOTAL: None,
        }

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[I_TOTAL] = plant["totalIncome"] if (
                        "totalIncome" in plant and plant["totalIncome"] is not None and float(
                    plant["totalIncome"]) > 0) else plant["incomeTotal"]

                # Setup state
                if float(plant["totalPvEnergy"]) > 0.0:
                    self._attr_native_value = float(plant["totalPvEnergy"])
                elif  float(plant["totalEnergy"]) > 0.0:
                    self._attr_native_value = float(plant["totalEnergy"])
                else:
                    self._attr_available = False


class ESolarSensorPlantTodayEnergy(ESolarPlant):
    """Representation of a Saj eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}_today"

        self._attr_icon = ICON_METER
        self._attr_name = f"Plant {self._plant_name} Energy Today "
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

        self._attr_extra_state_attributes = {
            I_TODAY: None,
            I_YESTERDAY: None,
        }

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:

                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[I_TODAY] = plant["todayIncome"] if ("todayIcome" in plant and plant["todayIncome"] is not None and float(plant["todayIncome"]) > 0) else plant["incomeToday"]
                self._attr_extra_state_attributes[I_YESTERDAY] = plant["yesterdayIncome"]
                # Setup state
                self._attr_native_value = float(plant["todayPvEnergy"])


class ESolarSensorPlantMonthEnergy(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}_month"

        self._attr_icon = ICON_METER
        self._attr_name = f"Plant {self._plant_name} Energy Month"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

        self._attr_extra_state_attributes = {
            I_MONTH: None,
            I_LAST_MONTH: None,
        }

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[I_MONTH] = plant["incomeMonth"] if ("incomeMonth" in plant and plant["incomeMonth"] is not None and float(plant["incomeMonth"]) > 0) else plant["monthIncome"]
                self._attr_extra_state_attributes[I_LAST_MONTH] = plant["incomeLastMonth"]
                # Setup state
                self._attr_native_value = float(plant["monthPvEnergy"])


class ESolarSensorPlantYearEnergy(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_{plant_uid}_year"

        self._attr_icon = ICON_METER
        self._attr_name = f"Plant {self._plant_name} Energy Year"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = float(plant["yearPvEnergy"])


class ESolarSensorPlantPeakPower(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_peakpower_{plant_uid}"

        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} Peak Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                self._attr_native_value = float(plant["peakPower"])


class ESolarSensorPlantLastUploadTime(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_lastUploadTime_{plant_uid}"

        self._attr_icon = ICON_UPDATE
        self._attr_name = f"Plant {self._plant_name} last Upload Time"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_native_value = None

    def process_data(self):
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


class ESolarSensorPlantTodayEquivalentHours(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_todayEquivalentHours_{plant_uid}"

        self._attr_icon = ICON_UPDATE
        self._attr_name = f"Plant {self._plant_name} today Equivalent Hours"
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_unit_of_measurement = 'h'
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if "todayEquivalentHours" in plant and plant["todayEquivalentHours"] is not None and float(plant["todayEquivalentHours"]) > 0.0:
                    self._attr_native_value = float(plant["todayEquivalentHours"])
                else:
                    total_hours = 0.0
                    for device in plant["devices"]:
                        if "todayEquivalentHours" in device and device["todayEquivalentHours"] is not None and float(device["todayEquivalentHours"]) > 0.0:
                            total_hours += float(device["todayEquivalentHours"])
                    self._attr_native_value = total_hours


class ESolarSensorInverterPeakPower(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"Inverter_{self._inverter_sn}_peakpower"

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {self._inverter_sn} Peak Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None
        self._previous_value = None

    def process_data(self):
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



class ESolarSensorInverterTodayAlarmNum(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, inverter_sn) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"inverter_{inverter_sn}_todayAlarmNum"

        self._attr_icon = ICON_ALARM
        self._attr_name = f"Inverter {inverter_sn} Today Alarm Num"
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_native_value = 0

        self._attr_extra_state_attributes = {
            P_TODAY_ALARM_NUM : None
        }

    def process_data(self):
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


class ESolarInverterEnergyTotal(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} Energy Total"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            EH_TODAY: None,
            EH_TOTAL: None,
            MODULE_SIGN: None,
        }

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        self._attr_available = True
                        self._attr_extra_state_attributes[EH_TODAY] = kit["todayEquivalentHours"] if (
                                    "todayEquivalentHours" in kit and kit["todayEquivalentHours"] is not None and float(
                                kit["todayEquivalentHours"]) > 0) else None
                        self._attr_extra_state_attributes[EH_TOTAL] = kit["totalEquivalentHours"] if (
                                    "totalEquivalentHours" in kit and kit["totalEquivalentHours"] is not None and float(
                                kit["totalEquivalentHours"]) > 0) else None
                        self._attr_extra_state_attributes[MODULE_SIGN] = kit["moduleSignal"] if (
                                "moduleSignal" in kit and kit["moduleSignal"] is not None) else None
                        # Setup state
                        self._attr_native_value = float(kit["deviceStatisticsData"]["totalPvEnergy"])


class ESolarInverterEnergyToday(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._attr_icon = ICON_METER
        self._attr_name = f"Inverter {inverter_sn} Energy Today"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self._inverter_sn:
                        continue
                    # Setup state
                    self._attr_native_value = float(kit["deviceStatisticsData"]["todayPvEnergy"])


class ESolarInverterEnergyMonth(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._attr_icon = ICON_METER
        self._attr_name = f"Inverter {inverter_sn} Energy Month"
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if kit["deviceSn"] != self._inverter_sn:
                        continue
                    # Setup state
                    self._attr_native_value = float(kit["deviceStatisticsData"]["monthPvEnergy"])


class ESolarInverterPower(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

    def process_data(self):
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


class ESolarInverterPV(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._pv_string = pv_string

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PV{pv_string}"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
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


class ESolarInverterPC(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._pv_string = pv_string

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} PC{pv_string}"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
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


class ESolarInverterPW(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._pv_string = pv_string

        self._attr_icon = ICON_POWER
        self._attr_name = f"Inverter {inverter_sn} string {pv_string} power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
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


class ESolarInverterGridPowerWatt(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Grid_Power_watt_{inverter_sn}"

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

    def process_data(self):
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


class ESolarInverterGV(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._phase = phase
        self._attr_icon = ICON_GRID_IMPORT
        self._attr_name = f"Inverter {inverter_sn} GV{phase}{letter}"
        self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
        self._attr_device_class = SensorDeviceClass.VOLTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
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


class ESolarInverterGC(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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

        self._phase = phase
        self._attr_icon = ICON_GRID_EXPORT
        self._attr_name = f"Inverter {inverter_sn} GC{phase}{letter}"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
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


class ESolarInverterTemperature(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        inverter_sn
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, inverter_sn=inverter_sn
        )
        self._attr_native_value = None
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Temp_{inverter_sn}"

        self._attr_icon = ICON_THERMOMETER
        self._attr_name = f"Inverter {inverter_sn} Temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        if 'deviceTemp' in kit and -200 < float(kit["deviceTemp"]) < 200:
                            # Setup state
                            self._attr_native_value = float(kit["deviceTemp"])


class ESolarSensorPlantEnergy(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, source) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_{plant_uid}_{source}"

        self._source = source
        self._attr_icon = ICON_POWER
        self._attr_name = f"Plant {self._plant_name} "+split_camel_case(source)
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_device_class = SensorDeviceClass.ENERGY
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if self._source in plant and plant[self._source] is not None:
                    self._attr_native_value = float(plant[self._source])


class ESolarSensorPlantBatterySoC(ESolarPlant):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid
        )
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False

        self._attr_unique_id = f"plantUid_energy_battery_soc_{plant_uid}"

        self._attr_name = f"Plant {self._plant_name} State Of Charge"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None
        self._attr_extra_state_attributes = {
            P_NAME: None,
            P_UID: None,
            B_GRID_DIRECT: None
        }

    def process_data(self):
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
                elif "batCapicity" in kit["deviceStatisticsData"] and kit["deviceStatisticsData"]["batCapicity"] is not None and float(kit["deviceStatisticsData"]["batCapicity"]) > 0:
                    bat_capacity = float(kit["deviceStatisticsData"]["batCapicity"])

                installed += bat_capacity
                available += float( bat_capacity * kit["deviceStatisticsData"]["batEnergyPercent"])

            if installed > 0:
                self._attr_native_value = float(available / installed)

            if "gridDirection" in plant and plant["gridDirection"] is not None:
                if plant["gridDirection"] == 1:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = B_EXPORT
                elif plant["gridDirection"] == -1:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = B_IMPORT
                else:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN


class ESolarInverterBatterySoC(ESolarDevice):
    """Representation of an eSolar sensor for the plant."""

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
            B_TODAY_DISCHARGE_E: None,
            B_TOTAL_CHARGE_E: None,
            B_TOTAL_DISCHARGE_E: None,
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
                if kit["deviceSn"] == self._inverter_sn:
                    self._attr_native_value = float(kit["deviceStatisticsData"]["batEnergyPercent"])

                    self._attr_extra_state_attributes[I_MODEL] = kit["deviceType"]
                    self._attr_extra_state_attributes[I_SN] = kit["deviceSn"]
                    self._attr_extra_state_attributes[B_CAPACITY] = kit["deviceStatisticsData"]["batCapcity"]
                    self._attr_extra_state_attributes[B_CURRENT] = kit["deviceStatisticsData"]["batCurrent"]
                    self._attr_extra_state_attributes[B_POWER] = kit["deviceStatisticsData"]["batPower"]
                    self._attr_extra_state_attributes[B_T_LOAD] = kit["deviceStatisticsData"]["totalLoadPowerwatt"]
                    self._attr_extra_state_attributes[B_TODAY_CHARGE_E] = float(
                        kit["deviceStatisticsData"]["todayBatChgEnergy"]) * 1000
                    self._attr_extra_state_attributes[B_TODAY_DISCHARGE_E] = float(
                        kit["deviceStatisticsData"]["todayBatDisEnergy"]) * 1000
                    self._attr_extra_state_attributes[B_TOTAL_CHARGE_E] = float(
                        kit["deviceStatisticsData"]["totalBatChgEnergy"]) * 1000
                    self._attr_extra_state_attributes[B_TOTAL_DISCHARGE_E] = float(
                        kit["deviceStatisticsData"]["totalBatDisEnergy"]) * 1000
                    # self._attr_extra_state_attributes[B_H_LOAD] = plant["homeLoadPower"] # ???
                    if "backupTotalLoadPowerWatt" in kit["deviceStatisticsData"] and kit["deviceStatisticsData"]["backupTotalLoadPowerWatt"] is not None:
                        self._attr_extra_state_attributes[B_B_LOAD] = kit["deviceStatisticsData"]["backupTotalLoadPowerWatt"]
                    elif "backupTotalLoadPowerWatt" in kit and kit["backupTotalLoadPowerWatt"] is not None:
                        self._attr_extra_state_attributes[B_B_LOAD] = kit["backupTotalLoadPowerWatt"]
                    else:
                        self._attr_extra_state_attributes[B_B_LOAD] = None

                    if kit["batteryDirection"] == 0:
                        self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_STB
                    elif kit["batteryDirection"] == 1:
                        self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_DIS
                    elif kit["batteryDirection"] == -1:
                        self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_CH
                    else:
                        self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN

                    if kit["deviceStatisticsData"]["gridDirection"] == 1:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = B_EXPORT
                    elif kit["deviceStatisticsData"]["gridDirection"] == -1:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = B_IMPORT
                    elif kit["deviceStatisticsData"]["gridDirection"] == 0:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = B_DIR_STB
                    else:
                        self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN

            grid_power_watt = 0.0
            if "sysGridPowerwatt" in plant and plant["sysGridPowerwatt"] is not None:
                grid_power_watt = float(plant["sysGridPowerwatt"])
            if grid_power_watt == 0.0 and "devices" in plant and plant["devices"] is not None:
                for kit in plant["devices"]:
                    if "gridList" in kit and kit["gridList"] is not None:
                        for grid in kit["gridList"]:
                            if grid['gridPowerwatt'] is not None:
                                grid_power_watt += float(grid['gridPowerwatt'])
            self._attr_extra_state_attributes[G_POWER] = grid_power_watt

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


class ESolarSensorMeterPower(ESolarMeter):
    """Representation of an eSolar sensor for the plant."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, module_sn ) -> None:
        """Initialize the sensor."""

        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, module_sn=module_sn
        )

        self._attr_extra_state_attributes = {}
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Solar_Meter_{self._module_sn}_grid_power"

        self._attr_icon = ICON_POWER
        self._attr_name = f"Solar Meter {self._module_sn} Grid Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "modules" in plant and plant["modules"] is not None:
                for plant_module in plant["modules"]:
                    if plant_module['moduleSn'] == self._module_sn and "gridPower" in plant_module and plant_module["gridPower"] is not None:
                        # Setup static attributes
                        self._attr_available = True
                        # Setup state
                        self._attr_native_value = float(plant_module["gridPower"])

                    copy = plant_module.copy()
                    to_remove = ["deviceSnList", "moduleFw", "moduleModel", "moduleSn", "plantName", "plantUid"]
                    for key in to_remove:
                        if key in copy:
                            del copy[key]

                    self._attr_extra_state_attributes = copy


class ESolarSensorBatteryEntity(ESolarBattery):
    """Representation of an eSolar sensor for the battery."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, bat_sn, prop, add_attributes = None ) -> None:
        """Initialize the sensor."""

        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, bat_sn=bat_sn
        )

        self._attr_extra_state_attributes = {}
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Solar_battery_{self._bat_sn}_{prop}"
        self._property = prop

        self._attr_name = f"Solar battery {self._bat_sn} {split_camel_case(prop)}"
        self._attr_native_value = None
        self._add_attributes = add_attributes

        self._attr_state_class = SensorStateClass.MEASUREMENT

        if prop == 'batSoh' or prop == 'batSoc':
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.BATTERY
        elif prop == 'batTemperature':
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "batteries" in plant and plant["batteries"] is not None:
                for battery in plant["batteries"]:
                    if battery['batSn'] == self._bat_sn:
                        if self._property in battery and battery[self._property] is not None:
                            # Setup static attributes
                            self._attr_available = True
                            # Setup state
                            self._attr_native_value = float(extract_number(battery[self._property])) * (100 if self._property == 'batSoh' else 1)
                            if self._property == "batTemperature" and "unitOfTemperature" in battery and battery["unitOfTemperature"] is not None:
                                if battery["unitOfTemperature"] == "℃" or battery["unitOfTemperature"] == "C":
                                    self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                                elif battery["unitOfTemperature"] == "°F" or battery["unitOfTemperature"] == "C":
                                    self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
                                elif battery["unitOfTemperature"] == "K":
                                    self._attr_native_unit_of_measurement = UnitOfTemperature.KELVIN

                        if self._add_attributes is not None:
                            copy = battery.copy()
                            to_remove = ["deviceSn", "batSn", "bmsHardwareVersion", "bmsSoftwareVersion", "plantName", "plantUid", "batSoc", "batTemperature", "batSoh"]
                            for key in to_remove:
                                if key in copy:
                                    del copy[key]

                            self._attr_extra_state_attributes = copy


#unused yet
class ESolarSensorEMSEntity(ESolarEMS):
    """Representation of an eSolar sensor for the communication module."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, ems_sn, prop, add_attributes = None ) -> None:
        """Initialize the sensor."""

        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, ems_sn=ems_sn
        )

        self._attr_extra_state_attributes = {}
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Solar_ems_{self._ems_sn}_{prop}"
        self._property = prop

        self._attr_name = f"Solar EMS {self._ems_sn} {split_camel_case(prop)}"
        self._attr_native_value = None
        self._add_attributes = add_attributes

        self._attr_state_class = SensorStateClass.MEASUREMENT

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if "emsModules" in plant and plant["emsModules"] is not None:
                for ems in plant["emsModules"]:
                    if ems['emsModuleSn'] == self._ems_sn:
                        if self._property in ems and ems[self._property] is not None:
                            # Setup static attributes
                            self._attr_available = True
                            # Setup state
                            self._attr_native_value = float(extract_number(ems[self._property]))

                        if self._add_attributes is not None:
                            copy = ems.copy()
                            to_remove = ["deviceSn", "emsModel", "emsModulePc", "emsModuleSn", "firmwareVersion", "hardwareVersion", "plantName", "plantUid"]
                            for key in to_remove:
                                if key in copy:
                                    del copy[key]

                            self._attr_extra_state_attributes = copy
