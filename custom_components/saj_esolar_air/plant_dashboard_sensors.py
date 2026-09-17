"""Energy Dashboard oriented plant-level sensors for SAJ eSolar."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfPower
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ESolarCoordinator
from .const import DOMAIN, MANUFACTURER, PLANT_MODEL, PLANT_RUNNING_STATE_OFFLINE
from .sensor_helpers import offline_blocks_live_sensor

_LOGGER = logging.getLogger(__name__)

ICON_GRID = "mdi:transmission-tower"
ICON_GRID_IMPORT = "mdi:transmission-tower-import"
ICON_GRID_EXPORT = "mdi:transmission-tower-export"
ICON_BATTERY = "mdi:battery"
ICON_BATTERY_CHARGING = "mdi:battery-charging"
ICON_SOLAR = "mdi:solar-power"
ICON_HOME = "mdi:home-lightning-bolt"
ICON_TREE = "mdi:tree"
ICON_CO2 = "mdi:molecule-co2"
ICON_MODE = "mdi:cog"
ICON_ONLINE = "mdi:lan-connect"
ICON_STATUS = "mdi:check-circle-outline"
ICON_COAL = "mdi:barrel"
ICON_GENERATOR = "mdi:engine"
ICON_CHARGER = "mdi:ev-station"

GRID_DIRECTION_KEYS = {
    -1: "importing",
    0: "standby",
    1: "exporting",
}

BATTERY_DIRECTION_KEYS = {
    -1: "charging",
    0: "idle",
    1: "discharging",
}

INVERTER_STATUS_KEYS = {
    1: "normal",
    2: "alarm",
    3: "offline",
}


def plant_has_battery(plant: dict) -> bool:
    """Return True when the plant exposes battery-related data."""
    if plant.get("hasBattery") == 1:
        return True
    if plant.get("type") in (1, 3):
        return True
    for device in plant.get("devices") or []:
        if device.get("hasBattery") == 1:
            return True
        stats = device.get("deviceStatisticsData") or {}
        if stats.get("batEnergyPercent") is not None:
            return True
    return bool(plant.get("batteries"))


def _float_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            value = value.strip().rstrip("%").replace(",", ".")
            if not value or value in ("--", "N/A"):
                return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_device(plant: dict) -> dict:
    devices = [device for device in (plant.get("devices") or []) if isinstance(device, dict)]
    if not devices:
        return {}

    def score(device):
        model = f"{device.get('deviceModel') or ''} {device.get('deviceName') or ''}".lower()
        if "aio" in model:
            return -10
        is_inverter = device.get("deviceType") in (1, "1") or device.get("type") in (0, 1)
        online = 0 if device.get("deviceStatus") in (3, "3") else 2
        storage = 1 if device.get("type") == 1 or device.get("hasBattery") == 1 else 0
        return (2 if is_inverter else 0) + online + storage

    return max(devices, key=score)


def _battery_info(plant: dict) -> dict:
    device = _first_device(plant)
    stats = device.get("deviceStatisticsData") or {}
    merged = dict(stats)
    for key in (
        "usableBatCapacity",
        "batteryWorkTime",
        "userModeName",
        "batCapacity",
        "batCapcity",
        "batPower",
        "batCurrent",
        "batVoltage",
        "todayBatChgEnergy",
        "todayBatDisEnergy",
    ):
        if key in device and device[key] is not None:
            merged.setdefault(key, device[key])
        plant_val = plant.get(key)
        if plant_val not in (None, ""):
            merged[key] = plant_val
    if plant.get("batteries"):
        bat = plant["batteries"][0]
        for key in bat:
            merged.setdefault(key, bat[key])
    return merged


class ESolarPlantDashboardSensor(CoordinatorEntity[ESolarCoordinator], SensorEntity):
    """Base class for translated plant dashboard sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ESolarCoordinator,
        plant_name: str,
        plant_uid: str,
        translation_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._plant_name = plant_name
        self._plant_uid = plant_uid
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"plant_{plant_uid}_{translation_key}"

    def _plant_list(self) -> list[dict]:
        if not self.coordinator.data:
            return []
        return self.coordinator.data.get("plantList") or []

    def _offline_blocks_live_sensor(self, plant: dict) -> bool:
        return offline_blocks_live_sensor(self, plant)

    async def async_update(self) -> None:
        self.process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.process_data()
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._plant_uid)},
            manufacturer=MANUFACTURER,
            model=PLANT_MODEL,
            name=self._plant_name,
        )

    @property
    def native_value(self):
        return self._attr_native_value


class ESolarPlantGridPowerSensor(ESolarPlantDashboardSensor):
    """Signed grid power (positive import, negative export)."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_grid_power")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = ICON_GRID
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            power = _float_value(plant.get("sysGridPowerwatt"))
            if power is None:
                self._attr_available = False
                return
            direction = plant.get("gridDirection")
            if direction is not None and int(direction) == 1:
                power = -abs(power)
            self._attr_available = True
            self._attr_native_value = power
            return


class ESolarPlantGridPowerAbsoluteSensor(ESolarPlantDashboardSensor):
    """Absolute grid power."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_grid_power_absolute")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = ICON_GRID
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            power = _float_value(plant.get("sysGridPowerwatt"))
            if power is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = abs(power)
            return


class ESolarPlantBatteryPowerSensor(ESolarPlantDashboardSensor):
    """Signed battery power (positive discharge, negative charge)."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_battery_power")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = ICON_BATTERY_CHARGING
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if not plant_has_battery(plant):
                self._attr_available = False
                return
            if self._offline_blocks_live_sensor(plant):
                return
            info = _battery_info(plant)
            power = _float_value(plant.get("batPower", info.get("batPower")))
            if power is None:
                self._attr_available = False
                return
            direction = plant.get("batteryDirection")
            if direction is not None and int(direction) == -1:
                power = -abs(power)
            self._attr_available = True
            self._attr_native_value = power
            return


class ESolarPlantBatteryPowerAbsoluteSensor(ESolarPlantDashboardSensor):
    """Absolute battery power."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(
            coordinator, plant_name, plant_uid, "plant_battery_power_absolute"
        )
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = ICON_BATTERY_CHARGING
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if not plant_has_battery(plant):
                self._attr_available = False
                return
            if self._offline_blocks_live_sensor(plant):
                return
            info = _battery_info(plant)
            power = _float_value(plant.get("batPower", info.get("batPower")))
            if power is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = abs(power)
            return


class ESolarPlantPvPowerSensor(ESolarPlantDashboardSensor):
    """Current PV power."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_pv_power")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = ICON_SOLAR
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            power = _float_value(
                plant.get("totalPvPower", plant.get("nowPower", plant.get("powerNow")))
            )
            if power is None and plant.get("devices"):
                power = _float_value(_first_device(plant).get("powerNow"))
            if power is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = power
            return


class ESolarPlantLoadPowerSensor(ESolarPlantDashboardSensor):
    """Current load power."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_load_power")
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = ICON_HOME
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            power = _float_value(plant.get("totalLoadPowerwatt"))
            if power is None:
                stats = _first_device(plant).get("deviceStatisticsData") or {}
                power = _float_value(
                    stats.get("totalLoadPowerwatt") or stats.get("totalLoadPowerWatt")
                )
            if power is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = power
            return


class ESolarPlantSelfUseRateSensor(ESolarPlantDashboardSensor):
    """Self-consumption rate."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_self_use_rate")
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:home-percent"
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            rate = _float_value(plant.get("selfUseRate"))
            if rate is None:
                rate = _float_value(plant.get("selfUsePercent"))
            if rate is None:
                rate = _float_value(plant.get("selfUsePercentage"))
            if rate is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = rate
            return


class ESolarPlantUsableBatteryCapacitySensor(ESolarPlantDashboardSensor):
    """Usable battery capacity."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(
            coordinator, plant_name, plant_uid, "plant_usable_battery_capacity"
        )
        self._attr_device_class = SensorDeviceClass.ENERGY_STORAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        self._attr_icon = ICON_BATTERY
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if not plant_has_battery(plant):
                self._attr_available = False
                return
            info = _battery_info(plant)
            capacity = _float_value(
                info.get("usableBatCapacity")
                or plant.get("usableBatCapacity")
            )
            if capacity is None:
                packs = plant.get("batteries") or []
                total = 0.0
                counted = False
                for battery in packs:
                    soc = _float_value(battery.get("batSoc"))
                    model = str(battery.get("batModel") or "")
                    tokens = "".join(
                        ch if ch.isdigit() or ch == "." else " " for ch in model
                    ).split()
                    kwh = _float_value(
                        battery.get("batCapacity") or battery.get("batCapcity")
                    )
                    if kwh is None or kwh > 30:
                        kwh = None
                        for token in tokens:
                            if "." not in token:
                                continue
                            value = _float_value(token)
                            if value is not None and 0.5 <= value <= 30:
                                kwh = value
                                break
                        if kwh is None:
                            for token in tokens:
                                value = _float_value(token)
                                if value is not None and 3 <= value <= 30:
                                    kwh = value
                                    break
                    if kwh and soc is not None:
                        total += kwh * soc / 100.0
                        counted = True
                if counted:
                    capacity = round(total, 2)
            if capacity is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = capacity
            return


class ESolarPlantBatteryRemainingTimeSensor(ESolarPlantDashboardSensor):
    """Estimated battery runtime in hours."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(
            coordinator, plant_name, plant_uid, "plant_battery_remaining_time"
        )
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = "h"
        self._attr_icon = "mdi:timer-outline"
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if not plant_has_battery(plant):
                self._attr_available = False
                return
            info = _battery_info(plant)
            minutes = _float_value(
                info.get("batteryWorkTime") or plant.get("batteryWorkTime")
            )
            if minutes is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = round(minutes / 60, 1)
            return


class ESolarPlantOperatingModeSensor(ESolarPlantDashboardSensor):
    """Battery operating mode."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_operating_mode")
        self._attr_icon = ICON_MODE
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if not plant_has_battery(plant):
                self._attr_available = False
                return
            info = _battery_info(plant)
            mode = info.get("userModeName") or plant.get("userModeName")
            if not mode:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = mode
            return


class ESolarPlantDeviceOnlineSensor(ESolarPlantDashboardSensor):
    """Whether the plant is online."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_device_online")
        self._attr_icon = ICON_ONLINE
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            state = plant.get("runningState")
            if state is None:
                online = str(plant.get("isOnline", "")).upper() in ("Y", "1", "TRUE")
                self._attr_available = True
                self._attr_native_value = "online" if online else "offline"
                return
            self._attr_available = True
            self._attr_native_value = (
                "offline" if int(state) == PLANT_RUNNING_STATE_OFFLINE else "online"
            )
            return


class ESolarPlantDirectionSensor(ESolarPlantDashboardSensor):
    """Direction sensor with translated state keys."""

    def __init__(
        self,
        coordinator,
        plant_name,
        plant_uid,
        translation_key: str,
        plant_field: str,
        mapping: dict[int, str],
        icon: str,
    ) -> None:
        super().__init__(coordinator, plant_name, plant_uid, translation_key)
        self._plant_field = plant_field
        self._mapping = mapping
        self._attr_icon = icon
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            value = plant.get(self._plant_field)
            if value is None:
                self._attr_available = False
                return
            try:
                key = self._mapping.get(int(value), "unknown")
            except (TypeError, ValueError):
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = key
            return


class ESolarPlantPowerFieldSensor(ESolarPlantDashboardSensor):
    """Plant-level power field that is only created when the API has data."""

    def __init__(
        self,
        coordinator,
        plant_name,
        plant_uid,
        translation_key: str,
        plant_field: str,
        icon: str,
    ) -> None:
        super().__init__(coordinator, plant_name, plant_uid, translation_key)
        self._plant_field = plant_field
        self._attr_device_class = SensorDeviceClass.POWER
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = UnitOfPower.WATT
        self._attr_icon = icon
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            if self._offline_blocks_live_sensor(plant):
                return
            power = _float_value(plant.get(self._plant_field))
            if power is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = power
            return


class ESolarPlantDailyEnvironmentalSensor(ESolarPlantDashboardSensor):
    """Daily environmental impact sensor."""

    def __init__(
        self,
        coordinator,
        plant_name,
        plant_uid,
        translation_key: str,
        plant_field: str,
        unit: str | None,
        icon: str,
    ) -> None:
        super().__init__(coordinator, plant_name, plant_uid, translation_key)
        self._plant_field = plant_field
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        if translation_key.endswith("co2") or translation_key.endswith("coal"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:
            self._attr_state_class = SensorStateClass.TOTAL
        self._attr_native_value = None

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            value = _float_value(plant.get(self._plant_field))
            if value is None:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = value
            return


class ESolarPlantInverterStatusSensor(ESolarPlantDashboardSensor):
    """Inverter status with optional alarm attributes."""

    def __init__(self, coordinator, plant_name, plant_uid) -> None:
        super().__init__(coordinator, plant_name, plant_uid, "plant_inverter_status")
        self._attr_icon = ICON_STATUS
        self._attr_native_value = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    def process_data(self) -> None:
        for plant in self._plant_list():
            if plant["plantName"] != self._plant_name:
                continue
            preferred = _first_device(plant)
            status = plant.get("deviceStatus")
            if status is None:
                status = preferred.get("deviceStatus")
            try:
                status_int = int(status) if status is not None else None
            except (TypeError, ValueError):
                status_int = None
            if status_int not in INVERTER_STATUS_KEYS:
                name = str(
                    plant.get("runningStateName")
                    or preferred.get("deviceStatusName")
                    or ""
                ).strip().lower()
                mapped = {
                    "normal": "normal",
                    "alarm": "alarm",
                    "offline": "offline",
                    "fault": "alarm",
                }.get(name)
                if mapped:
                    self._attr_available = True
                    self._attr_native_value = mapped
                    self._attr_extra_state_attributes = {}
                    return
                running = plant.get("runningState")
                try:
                    status_int = int(running) if running is not None else None
                except (TypeError, ValueError):
                    status_int = None
            if status_int not in INVERTER_STATUS_KEYS:
                self._attr_available = False
                return
            self._attr_available = True
            self._attr_native_value = INVERTER_STATUS_KEYS.get(status_int, "unknown")
            self._attr_extra_state_attributes = {}
            if status_int == 2 or status_int == 3:
                for device in plant.get("devices") or []:
                    alarms = device.get("alarmList") or []
                    if alarms:
                        alarm = alarms[0]
                        self._attr_extra_state_attributes = {
                            "alarm_name": alarm.get("alarmName"),
                            "alarm_level": alarm.get("alarmLevelName"),
                            "alarm_start_time": alarm.get("alarmStartTime"),
                        }
                        break
            return


def create_plant_dashboard_sensors(
    coordinator: ESolarCoordinator,
    plant_name: str,
    plant_uid: str,
    plant: dict,
) -> list[SensorEntity]:
    """Create dashboard sensors appropriate for the plant type."""
    sensors: list[SensorEntity] = [
        ESolarPlantGridPowerSensor(coordinator, plant_name, plant_uid),
        ESolarPlantGridPowerAbsoluteSensor(coordinator, plant_name, plant_uid),
        ESolarPlantPvPowerSensor(coordinator, plant_name, plant_uid),
        ESolarPlantLoadPowerSensor(coordinator, plant_name, plant_uid),
        ESolarPlantSelfUseRateSensor(coordinator, plant_name, plant_uid),
        ESolarPlantDeviceOnlineSensor(coordinator, plant_name, plant_uid),
        ESolarPlantInverterStatusSensor(coordinator, plant_name, plant_uid),
        ESolarPlantDirectionSensor(
            coordinator,
            plant_name,
            plant_uid,
            "plant_pv_direction",
            "pvDirection",
            GRID_DIRECTION_KEYS,
            ICON_SOLAR,
        ),
        ESolarPlantDirectionSensor(
            coordinator,
            plant_name,
            plant_uid,
            "plant_grid_direction",
            "gridDirection",
            GRID_DIRECTION_KEYS,
            ICON_GRID,
        ),
        ESolarPlantDirectionSensor(
            coordinator,
            plant_name,
            plant_uid,
            "plant_output_direction",
            "outPutDirection",
            GRID_DIRECTION_KEYS,
            ICON_HOME,
        ),
        ESolarPlantDailyEnvironmentalSensor(
            coordinator,
            plant_name,
            plant_uid,
            "plant_daily_trees",
            "todayPlantTreeNum",
            None,
            ICON_TREE,
        ),
        ESolarPlantDailyEnvironmentalSensor(
            coordinator,
            plant_name,
            plant_uid,
            "plant_daily_co2",
            "todayReduceCo2",
            "t",
            ICON_CO2,
        ),
    ]
    coal = _float_value(plant.get("todayCoal"))
    if coal is not None and coal != 0:
        sensors.append(
            ESolarPlantDailyEnvironmentalSensor(
                coordinator,
                plant_name,
                plant_uid,
                "plant_daily_coal",
                "todayCoal",
                "t",
                ICON_COAL,
            )
        )
    if _float_value(plant.get("backupTotalLoadPowerWatt")) is not None:
        sensors.append(
            ESolarPlantPowerFieldSensor(
                coordinator,
                plant_name,
                plant_uid,
                "plant_backup_power",
                "backupTotalLoadPowerWatt",
                ICON_HOME,
            )
        )
    gen_power = _float_value(plant.get("genPowerwatt"))
    has_gen = plant.get("hasGen") == 1 or (gen_power is not None and gen_power != 0)
    if has_gen:
        sensors.append(
            ESolarPlantPowerFieldSensor(
                coordinator,
                plant_name,
                plant_uid,
                "plant_generator_power",
                "genPowerwatt",
                ICON_GENERATOR,
            )
        )
        if plant.get("genDirection") is not None:
            sensors.append(
                ESolarPlantDirectionSensor(
                    coordinator,
                    plant_name,
                    plant_uid,
                    "plant_generator_direction",
                    "genDirection",
                    GRID_DIRECTION_KEYS,
                    ICON_GENERATOR,
                )
            )
    charger_power = _float_value(plant.get("chargePower"))
    has_charger = plant.get("hasCharger") == 1 or (
        charger_power is not None and charger_power != 0
    )
    if has_charger:
        sensors.append(
            ESolarPlantPowerFieldSensor(
                coordinator,
                plant_name,
                plant_uid,
                "plant_charger_power",
                "chargePower",
                ICON_CHARGER,
            )
        )
        if plant.get("chargerDirection") is not None:
            sensors.append(
                ESolarPlantDirectionSensor(
                    coordinator,
                    plant_name,
                    plant_uid,
                    "plant_charger_direction",
                    "chargerDirection",
                    BATTERY_DIRECTION_KEYS,
                    ICON_CHARGER,
                )
            )

    if plant_has_battery(plant):
        sensors.extend(
            [
                ESolarPlantBatteryPowerSensor(coordinator, plant_name, plant_uid),
                ESolarPlantBatteryPowerAbsoluteSensor(
                    coordinator, plant_name, plant_uid
                ),
                ESolarPlantUsableBatteryCapacitySensor(
                    coordinator, plant_name, plant_uid
                ),
                ESolarPlantBatteryRemainingTimeSensor(
                    coordinator, plant_name, plant_uid
                ),
                ESolarPlantOperatingModeSensor(coordinator, plant_name, plant_uid),
                ESolarPlantDirectionSensor(
                    coordinator,
                    plant_name,
                    plant_uid,
                    "plant_battery_direction",
                    "batteryDirection",
                    BATTERY_DIRECTION_KEYS,
                    ICON_BATTERY,
                ),
            ]
        )

    return sensors
