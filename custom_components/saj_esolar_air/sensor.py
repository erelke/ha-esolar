"""Support for ESolar sensors."""
from __future__ import annotations
import datetime
from datetime import timedelta, datetime
import pytz
import logging
from .elekeeper import extract_number, split_camel_case, extract_date

_LOGGER = logging.getLogger(__name__)


def _safe_process_data(entity) -> None:
    """Apply sensor updates without crashing on missing v2 fields."""
    try:
        entity.process_data()
    except (KeyError, TypeError, ValueError) as err:
        _LOGGER.debug(
            "Incomplete SAJ payload for %s: %s",
            getattr(entity, "entity_id", entity.__class__.__name__),
            err,
        )
        entity._attr_available = False
        entity._attr_native_value = None


def _kit_stats(kit: dict | None) -> dict:
    stats = (kit or {}).get("deviceStatisticsData")
    return stats if isinstance(stats, dict) else {}


def _first_number(*values):
    for value in values:
        if value in (None, "", "--"):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _grid_phase_defs(device: dict) -> list[dict]:
    """Return grid phases from live data, or a model-based fallback."""
    grid_list = _kit_stats(device).get("gridList") or device.get("gridList") or []
    if isinstance(grid_list, list) and grid_list:
        return grid_list
    model = f"{device.get('deviceModel') or ''} {device.get('deviceName') or ''}".upper()
    count = 3 if any(token in model for token in ("-T2", "-T3", " T2", " T3")) else 1
    return [{"gridNo": index} for index in range(1, count + 1)]


def _pv_string_defs(device: dict) -> list[dict]:
    """Return PV strings from live data, or two MPPT inputs."""
    pv_list = _kit_stats(device).get("pvList") or []
    if isinstance(pv_list, list) and pv_list:
        return pv_list
    return [{"pvNo": 1}, {"pvNo": 2}]

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
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
    P_TODAY_ALARM_NUM, ALARM_LIST,
    P_GRID_AC1,
    P_GRID_AC2,
    P_GRID_AC3, I_TODAY, I_YESTERDAY, I_MONTH, I_LAST_MONTH, I_TOTAL, EH_TODAY, EH_TOTAL, I_PC,
    B_TODAY_CHARGE_E,
    B_TODAY_DISCHARGE_E,
    B_TOTAL_CHARGE_E,
    B_TOTAL_DISCHARGE_E, DEVICE_MODEL, METER_MODEL, MODULE_SN, MODULE_SIGN,
    PLANT_RUNNING_STATE_OFFLINE,
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
ICON_CURRENT_DC = "mdi:current-dc"
ICON_CURRENT_AC = "mdi:current-ac"
ICON_WIFI = "mdi:wifi"
ICON_STATUS = "mdi:check-circle-outline"

from .sensor_helpers import offline_blocks_live_sensor

_LIVE_BATTERY_PROPS = frozenset({
    "batSoc", "batTemperature", "batPower", "batCurrent", "batVoltage",
})


def is_float_and_not_int(num):
    return isinstance(num, float) and not isinstance(num, int)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the eSolar sensor."""
    from .plant_dashboard_sensors import create_plant_dashboard_sensors

    coordinator: ESolarCoordinator = hass.data[DOMAIN][entry.entry_id]
    plant_entities: list[ESolarPlant] = []
    device_entities: list[ESolarDevice] = []
    meter_entities: list[ESolarMeter] = []
    bat_entities: list[ESolarBattery] = []
    esolar_data: dict = coordinator.data
    my_plants = entry.options.get(CONF_MONITORED_SITES)
    use_inverter_sensors = entry.options.get(CONF_INVERTER_SENSORS, True)
    use_pv_grid_attributes = entry.options.get(CONF_PV_GRID_DATA, True)

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
            # Plant type enum:
            #  0 - On-grid - plant with PV inverter only (device type: 0, On-grid inverter)
            #  1 - Energy Storage - Plant with PV inverter and external battery (device type: 1, Storage inverter)
            #  2 - ???
            #  3 - AC Coupling - Plant with PV inverter with builtin battery (device type: 2, AC Coupling Inverter)
            
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


            plant_entities.extend(
                create_plant_dashboard_sensors(
                    coordinator, plant["plantName"], plant["plantUid"], plant
                )
            )

            has_battery = (
                plant.get("hasBattery") == 1
                or bool(plant.get("batteries"))
                or any(
                    (device.get("deviceStatisticsData") or {}).get("batEnergyPercent") is not None
                    for device in plant.get("devices", [])
                )
            )

            if has_battery:
                sources = ["todayBuyEnergy", "todayChargeEnergy", "todayDisChargeEnergy", "todayLoadEnergy", "todaySellEnergy",
                           "totalBuyEnergy", "totalChargeEnergy", "totalDisChargeEnergy", "totalLoadEnergy", "totalSellEnergy",
                           "yearBuyEnergy", "yearBatChgEnergy", "yearBatDischgEnergy", "yearLoadEnergy", "yearSellEnergy",
                           "monthBuyEnergy", "monthBatChgEnergy", "monthBatDischgEnergy", "monthLoadEnergy", "monthSellEnergy",
                           ]

                plant_entities.append(
                    ESolarSensorPlantBatterySoC(
                        coordinator, plant["plantName"], plant["plantUid"]
                    )
                )

            elif plant["type"] in [0,1] and "isInstallMeter" in plant and plant["isInstallMeter"] == 1:
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


            _LOGGER.warning(
                "Plant %s inverter_sensors=%s deviceSnList=%s",
                plant["plantName"],
                use_inverter_sensors,
                plant.get("deviceSnList"),
            )
            if use_inverter_sensors:
                for device in plant.get("deviceSnList") or []:
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
                            for pv in _pv_string_defs(kit):
                                pv_no = pv.get("pvNo")
                                if pv_no is None:
                                    continue
                                device_entities.append(
                                    ESolarInverterPV( coordinator, plant["plantName"], plant["plantUid"], device, pv_no)
                                )
                                device_entities.append(
                                    ESolarInverterPC(coordinator, plant["plantName"], plant["plantUid"], device, pv_no)
                                )
                                device_entities.append(
                                    ESolarInverterPW(coordinator, plant["plantName"], plant["plantUid"], device, pv_no)
                                )
                            if kit.get("deviceTemp", 0) != 0 or kit.get("deviceType") == 1:
                                device_entities.append(
                                    ESolarInverterTemperature(coordinator, plant["plantName"], plant["plantUid"], device)
                                )

                    device_entities.append(
                        ESolarInverterEnergyToday(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
                        ESolarInverterEnergyMonth(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
                        ESolarSensorInverterTodayAlarmNum(coordinator, plant["plantName"], plant["plantUid"], device)
                    )
                    device_entities.append(
                        ESolarSensorInverterPeakPower( coordinator, plant["plantName"], plant["plantUid"], device)
                    )

            if use_inverter_sensors and has_battery:
                for device_sn in plant.get("deviceSnList") or []:
                    for device in plant["devices"]:
                        if device["deviceSn"] == device_sn:
                            device_stats = device.get("deviceStatisticsData") or {}
                            device_has_battery = (
                                device.get("hasBattery") == 1
                                or device_stats.get("batEnergyPercent") is not None
                                or device.get("batEnergyPercent") is not None
                            )
                            if device_has_battery:
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
                for device_sn in plant.get("deviceSnList") or []:
                    for device in plant.get("devices") or []:
                        if device["deviceSn"] == device_sn:
                            _LOGGER.debug(
                                "Plant %s %s gridList=%s pvList=%s",
                                plant["plantName"],
                                device_sn,
                                _kit_stats(device).get("gridList"),
                                _kit_stats(device).get("pvList"),
                            )
                            for grid in _grid_phase_defs(device):
                                grid_no = grid.get("gridNo")
                                if grid_no is None:
                                    continue
                                device_entities.append(
                                    ESolarInverterGV(coordinator, plant["plantName"], plant["plantUid"], device_sn, grid_no)
                                )
                                device_entities.append(
                                    ESolarInverterGC(coordinator, plant["plantName"], plant["plantUid"], device_sn, grid_no)
                                )
                            device_entities.append(
                                ESolarInverterGridPowerWatt(coordinator, plant["plantName"], plant["plantUid"], device_sn)
                            )

            if "modules" in plant and plant["modules"] is not None:
                for module in plant["modules"]:
                    if "moduleSn" in module and module["moduleSn"] is not None:
                        _LOGGER.debug(
                            "Setting up module sensors for %s and module %s",
                            plant["plantName"],
                            module["moduleSn"],
                        )
                        meter_entities.extend(
                            _create_module_sensors(coordinator, plant, module)
                        )

            if "batteries" in plant and plant["batteries"] is not None:
                for battery_index, battery in enumerate(plant["batteries"]):
                    if "batSn" in battery and battery["batSn"] is not None:
                        bat_label = battery_index + 1
                        _LOGGER.debug(
                            "Setting up ESolarSensorBatteryEntities for %s and battery %s",
                            plant["plantName"],
                            battery["batSn"],
                        )
                        bat_entities.append(
                            ESolarSensorBatteryEntity(
                                coordinator,
                                plant["plantName"],
                                plant["plantUid"],
                                battery["batSn"],
                                "batSoc",
                                1,
                                battery_index=bat_label,
                            )
                        )
                        bat_entities.append(
                            ESolarSensorBatteryEntity(
                                coordinator,
                                plant["plantName"],
                                plant["plantUid"],
                                battery["batSn"],
                                "batTemperature",
                                battery_index=bat_label,
                            )
                        )
                        if battery.get("type", 1) == 2:
                            _LOGGER.debug(
                                "Setting up ESolarSensorBatteryEntities for %s and builtin battery %s",
                                plant["plantName"],
                                battery["batSn"],
                            )
                            for prop in (
                                "batVoltage",
                                "batCurrent",
                                "batPower",
                                "todayBatChgEnergy",
                                "todayBatDisEnergy",
                                "totalBatChgEnergy",
                                "totalBatDisEnergy",
                            ):
                                bat_entities.append(
                                    ESolarSensorBatteryEntity(
                                        coordinator,
                                        plant["plantName"],
                                        plant["plantUid"],
                                        battery["batSn"],
                                        prop,
                                        battery_index=bat_label,
                                    )
                                )
                        else:
                            bat_entities.append(
                                ESolarSensorBatteryEntity(
                                    coordinator,
                                    plant["plantName"],
                                    plant["plantUid"],
                                    battery["batSn"],
                                    "batSoh",
                                    battery_index=bat_label,
                                )
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

        self._device_name: None | str = f"Plant {plant_name}"
        self._device_model: None | str = PLANT_MODEL

    def _offline_blocks_live_sensor(
        self,
        plant: dict,
        device: dict | None = None,
        *,
        report_zero: bool = False,
    ) -> bool:
        """Mark sensor unavailable when the plant or inverter is offline."""
        return offline_blocks_live_sensor(
            self, plant, device, report_zero=report_zero
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""
        plant_no = None
        plant_id = None
        plant_owner = None
        plant_owner_email = None

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                plant_no = plant.get("plantNo")
                plant_id = plant.get("plantId") or plant.get("plantUid")
                plant_owner = plant.get("ownerName")
                plant_owner_email = plant.get("ownerEmail")

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._plant_name,
            identifiers={(DOMAIN, self._plant_uid)},
        )
        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        _safe_process_data(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _safe_process_data(self)
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

        self._device_name: None | str = f"Inverter {inverter_sn}"
        self._device_model: None | str = DEVICE_MODEL
        self._hw_version: None | str = None
        self._sw_version: None | str = None
        self._device_pc: None | str = None

    def _offline_blocks_live_sensor(
        self,
        plant: dict,
        device: dict | None = None,
        *,
        report_zero: bool = False,
    ) -> bool:
        """Mark sensor unavailable when the plant or inverter is offline."""
        return offline_blocks_live_sensor(
            self, plant, device, report_zero=report_zero
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "devices" in plant and plant["devices"] is not None:
                    for device in plant["devices"]:
                        if device["deviceSn"] == self._inverter_sn:
                            self._device_model = device.get("deviceModel") or device.get("inverterModel")
                            self._hw_version = (
                                device.get("masterMCUFw")
                                or device.get("masterMcuFw")
                                or device.get("masterControlFw")
                            )
                            self._sw_version = device.get("displayFw") or device.get("softwareVersion")
                            self._device_pc = device.get("devicePc")

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._inverter_sn,
            hw_version=self._hw_version,
            sw_version=self._sw_version,
            via_device=(DOMAIN, self._plant_uid),
            identifiers={
                (DOMAIN, f"{self._plant_uid}_{self._inverter_sn}"),
            },
        )
        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        _safe_process_data(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _safe_process_data(self)
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value


class ESolarMeter(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        module_sn=None,
        module_role=None,
        module_name=None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._module_sn = module_sn
        self._module_role = module_role or "meter"
        self._module_key = f"{module_sn}_{self._module_role}"

        self._device_name: None | str = module_name or f"Meter {module_sn}"
        self._device_model: None | str = METER_MODEL
        self._sw_version: None | str = None
        self._hw_version: None | str = None

    def _offline_blocks_live_sensor(
        self,
        plant: dict,
        device: dict | None = None,
        *,
        report_zero: bool = False,
    ) -> bool:
        """Mark sensor unavailable when the plant or inverter is offline."""
        return offline_blocks_live_sensor(
            self, plant, device, report_zero=report_zero
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "modules" in plant and plant["modules"] is not None:
                    for module in plant["modules"]:
                        same_sn = module.get("moduleSn") == self._module_sn
                        same_role = (module.get("moduleRole") or "meter") == self._module_role
                        if same_sn and same_role:
                            self._device_model = module.get("moduleModel")
                            self._sw_version = module.get("moduleFw")
                            self._hw_version = module.get("hardwareVersion")
                            if module.get("moduleName"):
                                self._device_name = module["moduleName"]
                            break

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._module_sn,
            sw_version=self._sw_version,
            hw_version=self._hw_version,
            via_device=(DOMAIN, self._plant_uid),
            identifiers={
                (DOMAIN, f"{self._plant_uid}_meter_{self._module_key}"),
            },
        )

        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        _safe_process_data(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _safe_process_data(self)
        self.async_write_ha_state()

    @property
    def native_value(self):
        """Return sensor state."""
        return self._attr_native_value


class ESolarBattery(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Representation of a generic ESolar sensor."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, bat_sn = None, battery_index: int = 1) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._coordinator = coordinator
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._bat_sn = bat_sn
        self._battery_index = battery_index

        self._device_name: None | str = f"{plant_name} Battery {battery_index}"
        self._device_model: None | str = METER_MODEL
        self._sw_version: None | str = None
        self._hw_version: None | str = None

    def _offline_blocks_live_sensor(
        self,
        plant: dict,
        device: dict | None = None,
        *,
        report_zero: bool = False,
    ) -> bool:
        """Mark sensor unavailable when the plant or inverter is offline."""
        return offline_blocks_live_sensor(
            self, plant, device, report_zero=report_zero
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device_info of the device."""

        bms_sn = None
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if "batteries" in plant and plant["batteries"] is not None:
                    for battery in plant["batteries"]:
                        if battery.get("batSn") == self._bat_sn:
                            self._device_model = battery.get("batModel")
                            self._sw_version = battery.get("bmsSoftwareVersion")
                            self._hw_version = battery.get("bmsHardwareVersion")
                            bms_sn = battery.get("bmsSn")
                            break

        device_info = DeviceInfo(
            manufacturer=MANUFACTURER,
            model=self._device_model,
            name=self._device_name,
            serial_number=self._bat_sn,
            sw_version=self._sw_version,
            hw_version=self._hw_version,
            via_device=(DOMAIN, self._plant_uid),
            identifiers={
                (DOMAIN, f"{self._plant_uid}_battery_{self._bat_sn}"),
            },
        )

        return device_info

    async def async_update(self) -> None:
        """Get the latest data and update states."""
        _safe_process_data(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _safe_process_data(self)
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
                            self._device_name = ems["emsModuleName"] if ems["emsModuleName"] is not None and ems["emsModuleName"] != '--' else f"EMS {ems['emsModuleSn']}" or None
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
        _safe_process_data(self)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _safe_process_data(self)
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
                self._attr_extra_state_attributes[P_CO2] = plant.get("totalReduceCo2")
                self._attr_extra_state_attributes[P_COAL] = plant.get("totalCoal")
                self._attr_extra_state_attributes[P_TREES] = plant.get("totalPlantTreeNum")
                self._attr_extra_state_attributes[P_YCO2] = plant.get("yearReduceCo2")
                self._attr_extra_state_attributes[P_YCOAL] = plant.get("yearCoal")
                self._attr_extra_state_attributes[P_YTREES] = plant.get("yearPlantTreeNum")
                self._attr_extra_state_attributes[P_LATITUDE] = plant.get("latitude")
                self._attr_extra_state_attributes[P_LONGITUDE] = plant.get("longitude")
                self._attr_extra_state_attributes[P_PIC] = plant.get("plantLogo")
                self._attr_extra_state_attributes[P_ADR] = plant.get("fullAddress")
                self._attr_extra_state_attributes[P_FIRST_ONLINE] = plant.get("createDate")
                self._attr_extra_state_attributes[P_NO] = plant.get("plantNo")
                self._attr_extra_state_attributes[P_ID] = plant.get("plantId") or plant.get("plantUid")
                self._attr_extra_state_attributes[P_OWNER_NAME] = plant.get("ownerName")
                self._attr_extra_state_attributes[P_OWNER_EMAIL] = plant.get("ownerEmail")
                self._attr_extra_state_attributes[S_POWER] = plant.get("systemPower")

                # Setup state
                if plant.get("runningState") == 1:
                    self._attr_native_value = "Normal"
                elif plant.get("runningState") == 2:
                    self._attr_native_value = "Alarm"
                elif plant.get("runningState") == 3:
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
                total_income = plant.get("totalIncome")
                if total_income in (None, "--", ""):
                    total_income = plant.get("incomeTotal")
                self._attr_extra_state_attributes[I_TOTAL] = total_income

                total_pv = plant.get("totalPvEnergy")
                total_energy = plant.get("totalEnergy")

                if total_pv not in (None, "--", ""):
                    self._attr_available = True
                    self._attr_native_value = float(total_pv)
                elif total_energy not in (None, "--", ""):
                    self._attr_available = True
                    self._attr_native_value = float(total_energy)
                else:
                    self._attr_available = False
                    self._attr_native_value = None


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
                today_income = plant.get("todayIncome")
                if today_income in (None, "--", ""):
                    today_income = plant.get("incomeToday")

                self._attr_extra_state_attributes[I_TODAY] = today_income
                self._attr_extra_state_attributes[I_YESTERDAY] = plant.get("yesterdayIncome")

                # Setup state
                today_pv = plant.get("todayPvEnergy")
                if today_pv not in (None, "--", ""):
                    self._attr_available = True
                    self._attr_native_value = float(today_pv)
                else:
                    self._attr_available = False
                    self._attr_native_value = None


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
                month_pv = plant.get("monthPvEnergy")

                if month_pv in (None, "--", ""):
                    self._attr_available = False
                    self._attr_native_value = None
                    return

                self._attr_available = True
                self._attr_native_value = float(month_pv)

                month_income = plant.get("incomeMonth")
                if month_income is None:
                    month_income = plant.get("monthIncome")

                self._attr_extra_state_attributes[I_MONTH] = month_income
                self._attr_extra_state_attributes[I_LAST_MONTH] = plant.get(
                    "incomeLastMonth"
                )


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
                year_pv = plant.get("yearPvEnergy")

                if year_pv in (None, "--", ""):
                    self._attr_available = False
                    self._attr_native_value = None
                    return

                self._attr_available = True
                self._attr_native_value = float(year_pv)


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
                if self._offline_blocks_live_sensor(plant):
                    return
                # Setup static attributes
                api_peak = plant.get("peakPower")
                live = []
                for value in (
                    plant.get("nowPower"),
                    plant.get("powerNow"),
                    plant.get("totalPvPower"),
                ):
                    if value not in (None, "", "--"):
                        try:
                            live.append(float(value))
                        except (TypeError, ValueError):
                            pass
                for device in plant.get("devices") or []:
                    stats = device.get("deviceStatisticsData") or {}
                    for value in (
                        stats.get("powerNow"),
                        device.get("pvPower"),
                        stats.get("peakPower"),
                        device.get("peakPower"),
                    ):
                        if value not in (None, "", "--"):
                            try:
                                live.append(float(value))
                            except (TypeError, ValueError):
                                pass
                live_max = max(live) if live else None
                today = datetime.now().date()
                session_peak = (
                    self._attr_native_value
                    if self._last_updated is not None
                    and self._last_updated.date() == today
                    else None
                )
                candidates = []
                if api_peak not in (None, "", "--"):
                    candidates.append(float(api_peak))
                if live_max not in (None, "", "--") and float(live_max) > 0:
                    candidates.append(float(live_max))
                if session_peak not in (None, "", "--"):
                    candidates.append(float(session_peak))
                if not candidates:
                    self._attr_available = False
                    self._attr_native_value = None
                else:
                    peak_power = max(candidates)
                    self._attr_available = True
                    self._attr_native_value = peak_power
                    self._last_updated = datetime.now()


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
                timezone = None
                if "timeZone" in plant and plant["timeZone"] is not None:
                    timezone = plant["timeZone"]

                if "dataTime" in plant and plant["dataTime"] is not None:
                    self._attr_native_value = extract_date(plant["dataTime"], timezone)
                elif self._attr_native_value is None and "updateDate" in plant and plant["updateDate"] is not None:
                    self._attr_native_value = extract_date(plant["updateDate"], timezone)
                elif self._attr_native_value is None and "dataTime" in plant["devices"][0] and plant["devices"][0]["deviceStatisticsData"]["dataTime"] is not None:
                    self._attr_native_value = extract_date(plant["devices"][0]["deviceStatisticsData"]["dataTime"], timezone)
                elif self._attr_native_value is None and "updateDate" in plant["devices"][0] and plant["devices"][0]["deviceStatisticsData"]["updateDate"] is not None:
                    self._attr_native_value = extract_date(plant["devices"][0]["deviceStatisticsData"]["updateDate"], timezone)


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
                    for device in plant.get("devices") or []:
                        if "todayEquivalentHours" in device and device["todayEquivalentHours"] is not None and float(device["todayEquivalentHours"]) > 0.0:
                            total_hours += float(device["todayEquivalentHours"])
                    if total_hours > 0.0:
                        self._attr_native_value = total_hours
                    else:
                        capacity = _first_number(plant.get("systemPower"), plant.get("systempower"))
                        energy = _first_number(plant.get("todayPvEnergy"), plant.get("todayElectricity"))
                        if capacity and capacity > 0 and energy is not None:
                            self._attr_native_value = round(energy / capacity, 2)
                        else:
                            self._attr_native_value = 0.0


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
                if self._offline_blocks_live_sensor(plant):
                    return
                # Setup static attributes
                self._attr_available = True
                # Setup state
                if self._last_updated is not None and self._last_updated.date() == datetime.now().date():
                    peak_power = self._attr_native_value or self.coordinator.hass.states.get(self._attr_unique_id) or float(0.0)
                else:
                    peak_power = float(0.0)
                for kit in plant["devices"]:
                    if kit.get("deviceSn") != self._inverter_sn:
                        continue
                    stats = _kit_stats(kit)
                    power_now = _first_number(
                        stats.get("powerNow"),
                        kit.get("pvPower"),
                        kit.get("pac"),
                    )
                    if power_now is None:
                        continue
                    peak_power = max(peak_power, power_now)
                    if self._attr_native_value != float(peak_power):
                        self._last_updated = datetime.now()
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
            P_TODAY_ALARM_NUM : None,
            ALARM_LIST : None,
        }

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                # Setup static attributes
                self._attr_available = True
                self._attr_extra_state_attributes[P_TODAY_ALARM_NUM] = plant["todayAlarmNum"] if "todayAlarmNum" in plant else 0

                if "devices" not in plant or plant["devices"] is None:
                    continue
                for kit in plant["devices"]:
                    if kit["deviceSn"] == self._inverter_sn:
                        # Setup state
                        self._attr_native_value = kit["todayAlarmNum"] if "todayAlarmNum" in kit else 0
                        self._attr_extra_state_attributes[ALARM_LIST] = kit["alarmList"] if "alarmList" in kit else []


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
                        total_pv = _first_number(
                            _kit_stats(kit).get("totalPvEnergy"),
                            kit.get("totalPvEnergy"),
                            plant.get("totalPvEnergy"),
                        )
                        if total_pv is None:
                            self._attr_available = False
                            self._attr_native_value = None
                        else:
                            self._attr_native_value = total_pv


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
                    if kit.get("deviceSn") != self._inverter_sn:
                        continue
                    today_pv = _first_number(
                        _kit_stats(kit).get("todayPvEnergy"),
                        kit.get("todayPvEnergy"),
                        plant.get("todayPvEnergy"),
                    )
                    if today_pv is None:
                        self._attr_available = False
                        self._attr_native_value = None
                    else:
                        self._attr_available = True
                        self._attr_native_value = today_pv


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
                    if kit.get("deviceSn") != self._inverter_sn:
                        continue
                    month_pv = _first_number(
                        _kit_stats(kit).get("monthPvEnergy"),
                        kit.get("monthPvEnergy"),
                        plant.get("monthPvEnergy"),
                    )
                    if month_pv is None:
                        self._attr_available = False
                        self._attr_native_value = None
                    else:
                        self._attr_available = True
                        self._attr_native_value = month_pv


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
                if self._offline_blocks_live_sensor(plant):
                    return
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit.get("deviceSn") != self._inverter_sn:
                            continue
                        stats = _kit_stats(kit)
                        power_now = _first_number(
                            stats.get("powerNow"),
                            kit.get("pvPower"),
                            kit.get("pac"),
                        )
                        if power_now is None:
                            self._attr_available = False
                            self._attr_native_value = None
                            continue
                        self._attr_available = True
                        self._attr_native_value = power_now
                        child = (kit.get("children") or [{}])[0] or {}
                        self._attr_extra_state_attributes[P_DPC] = kit.get("devicePc")
                        self._attr_extra_state_attributes[P_DEVICE_TYPE] = kit.get("deviceType")
                        self._attr_extra_state_attributes[P_DISPLAY_FW] = kit.get("displayFw")
                        self._attr_extra_state_attributes[P_INSTALL_NAME] = kit.get("installName")
                        self._attr_extra_state_attributes[P_MASTER_MCU_FW] = (
                            kit.get("masterMCUFw")
                            or kit.get("masterMcuFw")
                            or kit.get("masterControlFw")
                        )
                        self._attr_extra_state_attributes[P_MODULE_FW] = (
                            kit.get("moduleFw") or child.get("softwareVersion")
                        )
                        self._attr_extra_state_attributes[P_MODULE_PC] = kit.get("modulePc")
                        self._attr_extra_state_attributes[P_MODULE_SN] = (
                            kit.get("moduleSn") or child.get("deviceSn")
                        )


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
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant, report_zero=True):
                return
            if "devices" not in plant or plant["devices"] is None:
                self._attr_available = False
                self._attr_native_value = None
                return
            for kit in plant["devices"]:
                if kit["deviceSn"] != self._inverter_sn:
                    continue
                if self._offline_blocks_live_sensor(plant, kit, report_zero=True):
                    return
                self._attr_available = True
                pv_list = (kit.get("deviceStatisticsData") or {}).get("pvList") or []
                for s in pv_list:
                    if s["pvNo"] == self._pv_string:
                        self._attr_native_value = float(s["pvvolt"])
                        return
                self._attr_available = False
                self._attr_native_value = None
                return


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

        self._attr_icon = ICON_CURRENT_DC
        self._attr_name = f"Inverter {inverter_sn} PC{pv_string}"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if self._offline_blocks_live_sensor(plant):
                    return
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
                if self._offline_blocks_live_sensor(plant):
                    return
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        for s in kit["deviceStatisticsData"]["pvList"]:
                            if s["pvNo"] == self._pv_string:
                                pv_power = float(s["pvpower"])
                                pv_power_calc = float(s["pvcurr"]) * float(s["pvvolt"])
                                self._attr_native_value = pv_power if pv_power != 0 else pv_power_calc


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
                if self._offline_blocks_live_sensor(plant):
                    return
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        grid_list = _kit_stats(kit).get("gridList") or []
                        grid_power_watt = 0.0
                        has_grid = False
                        for s in grid_list:
                            if s.get("gridPowerwatt") is None:
                                continue
                            has_grid = True
                            grid_power_watt += float(s["gridPowerwatt"])
                            if s.get("gridName") in [P_GRID_AC1, P_GRID_AC2, P_GRID_AC3]:
                                self._attr_extra_state_attributes[s["gridName"]] = s["gridPowerwatt"]
                        plant_grid = _first_number(plant.get("sysGridPowerwatt"))
                        if has_grid:
                            self._attr_native_value = grid_power_watt
                        elif plant_grid is not None:
                            self._attr_native_value = plant_grid
                        else:
                            self._attr_available = False
                            self._attr_native_value = None


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
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant, report_zero=True):
                return
            if "devices" not in plant or plant["devices"] is None:
                self._attr_available = False
                self._attr_native_value = None
                return
            for kit in plant["devices"]:
                if kit["deviceSn"] != self._inverter_sn:
                    continue
                if self._offline_blocks_live_sensor(plant, kit, report_zero=True):
                    return
                self._attr_available = True
                grid_list = (kit.get("deviceStatisticsData") or {}).get("gridList") or []
                for s in grid_list:
                    if s["gridNo"] == self._phase:
                        self._attr_native_value = float(s["gridVolt"])
                        return
                self._attr_available = False
                self._attr_native_value = None
                return


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
        self._attr_icon = ICON_CURRENT_AC
        self._attr_name = f"Inverter {inverter_sn} GC{phase}{letter}"
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        self._attr_device_class = SensorDeviceClass.CURRENT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] == self._plant_name:
                if self._offline_blocks_live_sensor(plant):
                    return
                # Setup static attributes
                self._attr_available = True
                if "devices" in plant and plant["devices"] is not None:
                    for kit in plant["devices"]:
                        if kit["deviceSn"] != self._inverter_sn:
                            continue
                        grid_list = _kit_stats(kit).get("gridList") or []
                        for s in grid_list:
                            if s.get("gridNo") == self._phase and s.get("gridCurr") is not None:
                                self._attr_native_value = float(s["gridCurr"])
                                return
                        self._attr_available = False
                        self._attr_native_value = None


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
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant, report_zero=True):
                return
            if "devices" not in plant or plant["devices"] is None:
                self._attr_available = False
                self._attr_native_value = None
                return
            for kit in plant["devices"]:
                if kit["deviceSn"] != self._inverter_sn:
                    continue
                if self._offline_blocks_live_sensor(plant, kit, report_zero=True):
                    return
                if "deviceTemp" not in kit:
                    self._attr_available = False
                    self._attr_native_value = None
                    return
                temp = float(kit["deviceTemp"])
                if -200 < temp < 200:
                    self._attr_available = True
                    self._attr_native_value = temp
                    return
                self._attr_available = False
                self._attr_native_value = None
                return


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
            B_GRID_DIRECT: None,
            B_DIRECTION: None
        }

    def process_data(self):
        installed = float(0)
        available = float(0)
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            # Setup static attributes
            self._attr_available = True
            self._attr_extra_state_attributes[P_NAME] = plant["plantName"]
            self._attr_extra_state_attributes[P_UID] = plant["plantUid"]

            # Setup state
            has_soc = False
            plant_pct = None
            try:
                raw_pct = plant.get("batEnergyPercent")
                if raw_pct is not None:
                    plant_pct = float(str(raw_pct).replace("%", ""))
            except (TypeError, ValueError):
                plant_pct = None
            if plant_pct is not None:
                self._attr_native_value = plant_pct
                has_soc = True

            for kit in plant.get("devices") or []:
                if has_soc:
                    break
                if "deviceStatisticsData" not in kit:
                    continue

                stats = kit["deviceStatisticsData"]
                bat_capacity = 0.0
                if stats.get("batCapacity") is not None and float(stats["batCapacity"]) > 0:
                    bat_capacity = float(stats["batCapacity"])
                elif stats.get("batCapcity") is not None and float(stats["batCapcity"]) > 0:
                    bat_capacity = float(stats["batCapcity"])
                elif stats.get("batCapicity") is not None and float(stats["batCapicity"]) > 0:
                    bat_capacity = float(stats["batCapicity"])

                installed += bat_capacity
                bat_pct = stats.get("batEnergyPercent")
                if bat_pct is not None:
                    has_soc = True
                    available += bat_capacity * float(bat_pct)

            if not has_soc:
                pack_socs = []
                for battery in plant.get("batteries") or []:
                    try:
                        soc = float(str(battery.get("batSoc") or "").replace("%", ""))
                    except (TypeError, ValueError):
                        continue
                    pack_socs.append(soc)
                if pack_socs:
                    self._attr_native_value = round(sum(pack_socs) / len(pack_socs), 1)
                    has_soc = True

            if has_soc and self._attr_native_value is None and installed > 0:
                self._attr_native_value = float(available / installed)
            elif not has_soc:
                self._attr_available = False

            if "gridDirection" in plant and plant["gridDirection"] is not None:
                if plant["gridDirection"] == 1:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = B_EXPORT
                elif plant["gridDirection"] == -1:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = B_IMPORT
                else:
                    self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN

            if "batteryDirection" in plant and plant["batteryDirection"] is not None:
                if plant["batteryDirection"] == 0:
                    self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_STB
                elif plant["batteryDirection"] == 1:
                    self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_DIS
                elif plant["batteryDirection"] == -1:
                    self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_CH
                else:
                    self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN


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

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            # Setup static attributes
            self._attr_available = True
            self._attr_extra_state_attributes[P_NAME] = plant["plantName"]
            self._attr_extra_state_attributes[P_UID] = plant["plantUid"]
            if "devices" not in plant or plant["devices"] is None:
                continue
            for kit in plant["devices"]:
                if kit["deviceSn"] == self._inverter_sn:
                    stats = kit.get("deviceStatisticsData") or {}
                    bat_pct = stats.get("batEnergyPercent")
                    if bat_pct is None:
                        self._attr_available = False
                        return
                    self._attr_native_value = float(bat_pct)

                    self._attr_extra_state_attributes[I_MODEL] = kit.get("deviceType")
                    self._attr_extra_state_attributes[I_SN] = kit.get("deviceSn")
                    self._attr_extra_state_attributes[B_CAPACITY] = stats.get("batCapcity")
                    self._attr_extra_state_attributes[B_CURRENT] = stats.get("batCurrent")
                    self._attr_extra_state_attributes[B_POWER] = stats.get("batPower")
                    self._attr_extra_state_attributes[B_T_LOAD] = stats.get("totalLoadPowerwatt")
                    for dest, src in (
                        (B_TODAY_CHARGE_E, "todayBatChgEnergy"),
                        (B_TODAY_DISCHARGE_E, "todayBatDisEnergy"),
                        (B_TOTAL_CHARGE_E, "totalBatChgEnergy"),
                        (B_TOTAL_DISCHARGE_E, "totalBatDisEnergy"),
                    ):
                        raw = stats.get(src)
                        self._attr_extra_state_attributes[dest] = (
                            float(raw) * 1000 if raw is not None else None
                        )
                    # self._attr_extra_state_attributes[B_H_LOAD] = plant["homeLoadPower"] # ???
                    if "backupTotalLoadPowerWatt" in stats and stats["backupTotalLoadPowerWatt"] is not None:
                        self._attr_extra_state_attributes[B_B_LOAD] = stats["backupTotalLoadPowerWatt"]
                    elif "backupTotalLoadPowerWatt" in kit and kit["backupTotalLoadPowerWatt"] is not None:
                        self._attr_extra_state_attributes[B_B_LOAD] = kit["backupTotalLoadPowerWatt"]
                    else:
                        self._attr_extra_state_attributes[B_B_LOAD] = None

                    if "batteryDirection" in kit and kit["batteryDirection"] is not None:
                        if kit["batteryDirection"] == 0:
                            self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_STB
                        elif kit["batteryDirection"] == 1:
                            self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_DIS
                        elif kit["batteryDirection"] == -1:
                            self._attr_extra_state_attributes[B_DIRECTION] = B_DIR_CH
                        else:
                            self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN
                    else:
                        self._attr_extra_state_attributes[B_DIRECTION] = P_UNKNOWN

                    grid_dir = stats.get("gridDirection")
                    if grid_dir is not None:
                        if grid_dir == 1:
                            self._attr_extra_state_attributes[B_GRID_DIRECT] = B_EXPORT
                        elif grid_dir == -1:
                            self._attr_extra_state_attributes[B_GRID_DIRECT] = B_IMPORT
                        elif grid_dir == 0:
                            self._attr_extra_state_attributes[B_GRID_DIRECT] = B_DIR_STB
                        else:
                            self._attr_extra_state_attributes[B_GRID_DIRECT] = P_UNKNOWN
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

            self._attr_extra_state_attributes[PV_POWER] = plant.get("totalPvPower")

            if "pvDirection" in plant and plant["pvDirection"] is not None:
                if plant["pvDirection"] == 1:
                    self._attr_extra_state_attributes[PV_DIRECTION] = B_EXPORT
                elif plant["pvDirection"] == -1:
                    self._attr_extra_state_attributes[PV_DIRECTION] = B_IMPORT
                else:
                    self._attr_extra_state_attributes[PV_DIRECTION] = P_UNKNOWN
            else:
                self._attr_extra_state_attributes[PV_DIRECTION] = P_UNKNOWN

            self._attr_extra_state_attributes[S_POWER] = plant.get("solarPower")


_COMM_MODULE_ROLES = frozenset({"aio", "wifi", "sec", "module"})
_METER_MODULE_ROLES = frozenset({"grid_meter", "pv_meter"})
_LIVE_MODULE_PROPS = frozenset({
    "gridPower",
    "totalLoadPower",
    "signalStrength",
    "signalStrengthValue",
    "volt1",
    "volt2",
    "volt3",
    "curr1",
    "curr2",
    "curr3",
    "power1",
    "power2",
    "power3",
    "freq1",
    "freq2",
    "freq3",
    "powerFactor1",
    "powerFactor2",
    "powerFactor3",
    "impEp",
    "expEp",
    "todayImpEp",
    "todayExpEp",
})


def _create_module_sensors(coordinator, plant, module):
    """Create status/signal sensors for comm modules and phase sensors for meters."""
    entities = []
    plant_name = plant["plantName"]
    plant_uid = plant["plantUid"]
    module_sn = module["moduleSn"]
    module_role = module.get("moduleRole")
    module_name = module.get("moduleName")
    device_type = module.get("deviceType")

    def add_prop(prop):
        entities.append(
            ESolarSensorModuleEntity(
                coordinator,
                plant_name,
                plant_uid,
                module_sn,
                prop,
                module_role=module_role,
                module_name=module_name,
            )
        )

    add_prop("deviceStatusName")
    add_prop("updateDate")

    is_comm = device_type == 2 or module_role in _COMM_MODULE_ROLES
    is_meter = device_type == 4 or module_role in _METER_MODULE_ROLES

    if is_comm:
        add_prop("signalStrength")
        add_prop("signalStrengthValue")
        if module_role == "sec" or module.get("gridPower") is not None:
            entities.append(
                ESolarSensorMeterPower(
                    coordinator,
                    plant_name,
                    plant_uid,
                    module_sn,
                    module_role=module_role,
                    module_name=module_name,
                )
            )
        if module_role == "sec" or module.get("totalLoadPower") is not None:
            add_prop("totalLoadPower")

    if is_meter:
        entities.append(
            ESolarSensorMeterPower(
                coordinator,
                plant_name,
                plant_uid,
                module_sn,
                module_role=module_role,
                module_name=module_name,
            )
        )
        for phase in (1, 2, 3):
            volt = module.get(f"volt{phase}")
            curr = module.get(f"curr{phase}")
            active = False
            try:
                active = phase == 1 or float(volt or 0) or float(curr or 0)
            except (TypeError, ValueError):
                active = phase == 1
            if not active:
                continue
            add_prop(f"volt{phase}")
            add_prop(f"curr{phase}")
            add_prop(f"power{phase}")
            if module.get(f"powerFactor{phase}") is not None:
                add_prop(f"powerFactor{phase}")
        add_prop("freq1")
        add_prop("impEp")
        add_prop("expEp")
        add_prop("todayImpEp")
        add_prop("todayExpEp")

    return entities


class ESolarSensorMeterPower(ESolarMeter):
    """Representation of an eSolar sensor for the plant."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        module_sn,
        module_role=None,
        module_name=None,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(
            coordinator=coordinator,
            plant_name=plant_name,
            plant_uid=plant_uid,
            module_sn=module_sn,
            module_role=module_role,
            module_name=module_name,
        )

        self._attr_extra_state_attributes = {}
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Solar_Meter_{self._module_key}_grid_power"

        self._attr_icon = ICON_POWER
        if self._module_role == "pv_meter":
            self._attr_name = f"{self._device_name} PV Power"
        else:
            self._attr_name = f"{self._device_name} Grid Power"
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_value = None

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            if "modules" in plant and plant["modules"] is not None:
                for plant_module in plant["modules"]:
                    same_sn = plant_module.get("moduleSn") == self._module_sn
                    same_role = (plant_module.get("moduleRole") or "meter") == self._module_role
                    if not (same_sn and same_role):
                        continue
                    if plant_module.get("gridPower") is not None:
                        self._attr_available = True
                        self._attr_native_value = float(plant_module["gridPower"])
                    copy = plant_module.copy()
                    to_remove = ["deviceSnList", "moduleFw", "moduleModel", "moduleSn", "plantName", "plantUid"]
                    for key in to_remove:
                        if key in copy:
                            del copy[key]
                    self._attr_extra_state_attributes = copy
                    return


class ESolarSensorModuleEntity(ESolarMeter):
    """Representation of a communication-module or meter channel sensor."""

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name,
        plant_uid,
        module_sn,
        prop,
        module_role=None,
        module_name=None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator,
            plant_name=plant_name,
            plant_uid=plant_uid,
            module_sn=module_sn,
            module_role=module_role,
            module_name=module_name,
        )

        self._attr_extra_state_attributes = {}
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._property = prop
        self._attr_unique_id = f"Solar_Meter_{self._module_key}_{prop}"
        self._attr_native_value = None
        self._attr_name = f"{self._device_name} {self._module_prop_name(prop)}"

        if prop == "deviceStatusName":
            self._attr_icon = ICON_STATUS
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop == "updateDate":
            self._attr_icon = ICON_UPDATE
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop == "signalStrength":
            self._attr_icon = ICON_WIFI
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop == "signalStrengthValue":
            self._attr_icon = ICON_WIFI
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop in {"impEp", "expEp", "todayImpEp", "todayExpEp"}:
            self._attr_icon = ICON_METER
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = (
                SensorStateClass.TOTAL
                if prop.startswith("today")
                else SensorStateClass.TOTAL_INCREASING
            )
        elif prop.startswith("powerFactor"):
            self._attr_icon = ICON_TRIANGLE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop == "totalLoadPower" or prop.startswith("power"):
            self._attr_icon = ICON_POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif prop.startswith("volt"):
            self._attr_icon = ICON_LIGHTNING
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif prop.startswith("curr"):
            self._attr_icon = ICON_CURRENT_AC
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif prop.startswith("freq"):
            self._attr_icon = ICON_UPDATE
            self._attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
            self._attr_device_class = SensorDeviceClass.FREQUENCY
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @staticmethod
    def _module_prop_name(prop: str) -> str:
        phase_names = {
            "volt1": "L1 Voltage",
            "volt2": "L2 Voltage",
            "volt3": "L3 Voltage",
            "curr1": "L1 Current",
            "curr2": "L2 Current",
            "curr3": "L3 Current",
            "power1": "L1 Power",
            "power2": "L2 Power",
            "power3": "L3 Power",
            "freq1": "Frequency",
            "deviceStatusName": "Status",
            "updateDate": "Last Update",
            "signalStrength": "Signal Strength",
            "signalStrengthValue": "Signal Quality",
            "totalLoadPower": "Load Power",
            "impEp": "Import Energy",
            "expEp": "Export Energy",
            "todayImpEp": "Today Import Energy",
            "todayExpEp": "Today Export Energy",
            "powerFactor1": "L1 Power Factor",
            "powerFactor2": "L2 Power Factor",
            "powerFactor3": "L3 Power Factor",
        }
        if prop in phase_names:
            return phase_names[prop]
        return split_camel_case(prop)

    def _module_value(self, plant_module: dict, plant: dict):
        if self._property == "deviceStatusName":
            value = plant_module.get("deviceStatusName") or plant_module.get("moduleStatusName")
            if value in (None, "", "--"):
                return None
            return str(value)
        if self._property == "signalStrengthValue":
            value = plant_module.get("signalStrengthValue")
            if value in (None, "", "--"):
                return None
            return str(value)
        if self._property == "updateDate":
            timezone = plant.get("timeZone")
            for key in ("updateDate", "dataUpdateTime", "accessTime"):
                raw = plant_module.get(key)
                if raw in (None, ""):
                    continue
                parsed = extract_date(str(raw), timezone)
                if parsed is not None:
                    return parsed
            return None
        if self._property == "freq1":
            return _first_number(
                plant_module.get("freq1"),
                plant_module.get("freq2"),
                plant_module.get("freq3"),
            )
        if self._property == "signalStrength":
            return _first_number(
                plant_module.get("signalStrength"),
                plant_module.get("moduleSignal"),
            )
        value = plant_module.get(self._property)
        if value in (None, "", "--"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if self._property in _LIVE_MODULE_PROPS and self._offline_blocks_live_sensor(plant):
                return
            for plant_module in plant.get("modules") or []:
                same_sn = plant_module.get("moduleSn") == self._module_sn
                same_role = (plant_module.get("moduleRole") or "meter") == self._module_role
                if not (same_sn and same_role):
                    continue
                value = self._module_value(plant_module, plant)
                if value is not None:
                    self._attr_available = True
                    self._attr_native_value = value
                if self._property == "deviceStatusName":
                    extras = {}
                    for key in (
                        "modulePc",
                        "hardwareVersion",
                        "moduleFw",
                        "boundDeviceSn",
                        "aliasName",
                        "ccid",
                    ):
                        if plant_module.get(key) not in (None, "", "--"):
                            extras[key] = plant_module[key]
                    binds = plant_module.get("moduleBindDeviceDetailList")
                    if isinstance(binds, list) and binds:
                        extras["boundDevices"] = [
                            f"{item.get('deviceModel') or ''} {item.get('sn') or ''}".strip()
                            for item in binds
                            if isinstance(item, dict)
                        ]
                    if extras:
                        self._attr_extra_state_attributes = extras
                return


class ESolarSensorBatteryEntity(ESolarBattery):
    """Representation of an eSolar sensor for the battery."""

    def __init__(self, coordinator: ESolarCoordinator, plant_name, plant_uid, bat_sn, prop, add_attributes = None, battery_index: int = 1 ) -> None:
        """Initialize the sensor."""

        super().__init__(
            coordinator=coordinator, plant_name=plant_name, plant_uid=plant_uid, bat_sn=bat_sn, battery_index=battery_index
        )

        self._attr_extra_state_attributes = {}
        self._last_updated: datetime.datetime | None = None
        self._attr_available = False
        self._attr_unique_id = f"Solar_battery_{self._bat_sn}_{prop}"
        self._property = prop

        self._attr_name = f"Battery {self._bat_sn} {split_camel_case(prop)}"
        self._attr_native_value = None
        self._add_attributes = add_attributes

        self._attr_state_class = SensorStateClass.MEASUREMENT

        if prop == 'batSoc':
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.BATTERY
        elif prop == 'batTemperature':
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop == 'batPower':
            self._attr_icon = ICON_POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop.endswith('Energy'):
            self._attr_icon = ICON_METER
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_state_class = SensorStateClass.TOTAL
        elif prop == "batCurrent":
            self._attr_icon = ICON_CURRENT_DC
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif prop == "batVoltage":
            self._attr_icon = ICON_LIGHTNING
            self._attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
            self._attr_device_class = SensorDeviceClass.VOLTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    def process_data(self):
        for plant in self._coordinator.data["plantList"]:
            if plant["plantName"] != self._plant_name:
                continue
            if (
                self._property in _LIVE_BATTERY_PROPS
                and self._offline_blocks_live_sensor(plant)
            ):
                return
            if "batteries" in plant and plant["batteries"] is not None:
                for battery in plant["batteries"]:
                    if battery['batSn'] == self._bat_sn:
                        if self._property in battery and battery[self._property] is not None:
                            # Setup static attributes
                            self._attr_available = True
                            # Setup state
                            if self._property == 'batSoh':
                                if battery.get("type", 1) == 2:
                                    self._attr_native_value = battery.get(self._property)
                                else:
                                    raw = float(extract_number(battery[self._property]))
                                    self._attr_native_value = min(
                                        100.0, max(0.0, 100.0 - raw)
                                    )
                            elif isinstance(battery[self._property], float):
                                self._attr_native_value = battery[self._property]
                            else:
                                self._attr_native_value = float(
                                    extract_number(battery[self._property])
                                )

                            if self._property == "batTemperature" and "unitOfTemperature" in battery and battery["unitOfTemperature"] is not None:
                                if battery["unitOfTemperature"] == "℃" or battery["unitOfTemperature"] == "C":
                                    self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
                                elif battery["unitOfTemperature"] == "°F" or battery["unitOfTemperature"] == "C":
                                    self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
                                elif battery["unitOfTemperature"] == "K":
                                    self._attr_native_unit_of_measurement = UnitOfTemperature.KELVIN
                            if self._property == 'batSoc':
                                self._attr_native_value = min(
                                    100.0, max(0.0, self._attr_native_value)
                                )

                        if self._add_attributes is not None:
                            copy = battery.copy()
                            to_remove = ["deviceSn", "batSn", "bmsHardwareVersion", "bmsSoftwareVersion", "plantName", "plantUid", "batSoc", "batTemperature",
                                         "solutioUrl", "todayBatChgEnergy", "todayBatDisEnergy", "totalBatChgEnergy", "totalBatDisEnergy", "showBatSoc", "showBatteryNum",
                                         "showGroupNum", "showHeating", "showNewBatteryFlag", "enableBindPlant", "aiSavingSwitch", "EnableShowBatteryClusterRealDataBtn",
                                         "EnableShowBatteryRealDataBtn", "EnableShowSingleVoltageBtn", "EnableShowWarranty", "IsHistory", "IsContainCluster", "IsHighVolt"]
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
