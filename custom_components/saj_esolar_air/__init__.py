"""The eSolar integration."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any, TypedDict, cast

import requests

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_MONITORED_SITES, CONF_PV_GRID_DATA, CONF_UPDATE_INTERVAL, DOMAIN
from .esolar import get_esolar_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


class ESolarStoreFindRawdataPageList(TypedDict):
    """API response for findRawdataPageList."""

    nowPrower: float
    rOutPowerWattStr: str
    batPower: float
    rBackupPowerWatt: float
    pV3StrCurr1Str: str
    timeStart: str
    pV4Curr: float
    currSelfConsumePowerStr: str
    rOutVolt: float
    totalPVEnergy: float
    tOutVolt: float
    createTimeStr: str
    deviceType: int
    pV4StrCurr2Str: str
    pv3SeriesCurrent: str
    rGridFreqStr: str
    totalBatDisEnergy: float
    tOutFreqStr: str
    sGridPowerWattStr: str
    totalBatChgEnergy: float
    isAdmin: str
    pV1StrCurr4: float
    pV1StrCurr3: float
    pV1StrCurr2: float
    pV1StrCurr1: float
    pv2SeriesCurrent: str
    POP: float
    RST: int
    pvInputMode: str
    rGridFreq: float
    sGridFreqStr: str
    sGridVoltStr: str
    tOutPowerVAStr: str
    pV4VoltStr: str
    batEnergyPercent: float
    backupTotalLoadPowerWatt: float
    tableStoreTimeEnd: str
    tOutVoltStr: str
    rGridVoltStr: str
    batVoltStr: str
    tGridCurrStr: str
    rGridCurr: float
    rOutFreqStr: str
    userId: str
    partitionName: str
    sGridVolt: float
    pV3PowerStr: str
    tOnGridOutVolt: float
    tGridPowerWattStr: str
    pV2StrCurr4Str: str
    ctPVPowerWattStr: str
    pV4StrCurr3Str: str
    tOutPowerWatt: float
    pV3Power: float
    pV1CurrStr: str
    pV2CurrStr: str
    pV4CurrStr: str
    onLineStr: str
    pV2Power: float
    todayBatDisEnergy: float
    pac: float
    officeId: str
    rOutPowerWatt: float
    pacStr: str
    powernow: float
    ctPvCurr: float
    tGridVoltStr: str
    powerNower: str
    pvChannelList: list[Any]
    pv1SeriesCurrent: str
    pV1Power: float
    pV4Volt: float
    pV3StrCurr2Str: str
    deviceTempStr: str
    rOutCurr: float
    tOutCurr: float
    todayFeedInEnergyStr: str
    totalPVEnergyStr: str
    pV3Curr: float
    sOnGridOutPowerWatt: float
    tGridFreqStr: str
    todayBatChgEnergy: float
    pV1StrCurr1Str: str
    tGridFreq: float
    totalFeedInEnergy: float
    sOutPowerVAStr: str
    gridDirection: int
    batCurrStr: str
    powerNow: float
    rOutPowerVA: float
    kitType: str
    pV1VoltStr: str
    todayLoadEnergy: float
    sOutPowerWattStr: str
    pV4StrCurr1: float
    sGridPowerVA: float
    pV4StrCurr2: float
    pV4StrCurr3: float
    pV4StrCurr4: float
    sOutPowerVA: float
    batType: str
    pV3Volt: float
    rGridPowerVAStr: str
    tGridPowerVAStr: str
    tGridCurr: float
    rOnGridOutFreq: float
    pV4StrCurr4Str: str
    tOutFreq: float
    todayPVEnergy: float
    tGridPowerWatt: float
    sGridPowerVAStr: str
    tOutCurrStr: str
    ctPvCurrStr: str
    pV2Curr: float
    totalLoadEnergy: float
    pV2PowerStr: str
    datetimeStr: str
    powernower: str
    PVP: float
    rGridCurrStr: str
    totalLoadPowerWattStr: str
    pV1StrCurr2Str: str
    nowProwerStr: str
    totalLoadEnergyStr: str
    sOutVolt: float
    ctGridPowerWattStr: str
    rGridPowerVA: float
    index: int
    tGridVolt: float
    todayFeedInEnergy: float
    totalBatChgEnergyStr: str
    tOnGridOutPowerWatt: float
    pV3VoltStr: str
    batPowerStr: str
    pV2Volt: float
    deviceSn: str
    todayPVEnergyStr: str
    pV3StrCurr3Str: str
    rGridPowerWattStr: str
    batCapicity: str
    sGridCurrStr: str
    sOutCurrStr: str
    pV2StrCurr2: float
    timeEnd: str
    pV2StrCurr1: float
    pV2StrCurr3Str: str
    tOutPowerWattStr: str
    tOutPowerVA: float
    pV2StrCurr4: float
    pV2StrCurr3: float
    rOutFreq: float
    plantuid: str
    endUser: str
    totalSellEnergy: float
    sGridPowerWatt: float
    pV1StrCurr3Str: str
    rOnGridOutVolt: float
    totalSellEnergyStr: str
    deviceModel: str
    batVolt: float
    todaySellEnergy: float
    totalFeedInEnergyStr: str
    sOutVoltStr: str
    timeStr: str
    pV3CurrStr: str
    pV1Curr: float
    sOutPowerWatt: float
    pV3StrCurr1: float
    pV3StrCurr2: float
    rOnGridOutPowerWatt: float
    pV3StrCurr3: float
    pV3StrCurr4: float
    pv4SeriesCurrent: str
    kitSN: str
    pV2StrCurr1Str: str
    pV4Power: float
    todaySellEnergyStr: str
    sOutFreq: float
    sGridCurr: float
    typeStr: str
    rGridVolt: float
    rOutPowerVAStr: str
    rOutCurrStr: str
    pV4PowerStr: str
    userUid: str
    pV2StrCurr2Str: str
    pV4StrCurr1Str: str
    ctGridPowerWatt: float
    deviceTemp: float
    pV2VoltStr: str
    sOutFreqStr: str
    batCurr: float
    totalBatDisEnergyStr: str
    pV1PowerStr: str
    batEnergyPercentStr: str
    pV1StrCurr4Str: str
    ctPVPowerWatt: float
    totalLoadPowerWatt: float
    todaySelfConsumpEnergy: float
    rOutVoltStr: str
    todayLoadEnergyStr: str
    rGridPowerWatt: float
    sOutCurr: float
    pV3StrCurr4Str: str
    sGridFreq: float
    tGridPowerVA: float
    meterAStatus: int
    pV1Volt: float
    sOnGridOutVolt: float
    todaySelfConsumpEnergyStr: str
    plantName: str


class ESolarStoreDevicePower(TypedDict):
    """API response for storeDevicePower."""

    pvPower: float
    gridPower: float
    inputOutputPower: float
    batteryPower: float
    totalLoadPower: float
    homeLoadPower: float
    backupLoadPower: float
    solarPower: float
    batCurr: float
    batEnergyPercent: float
    runningState: int
    isOnline: int
    isAlarm: int
    mark: int
    batCapcity: float
    batCapcityStr: str
    hasMeter: bool
    hasBattery: bool
    pvDirection: int
    gridDirection: int
    batteryDirection: int
    outPutDirection: int
    dataTime: int
    updateDate: int


class ESolarKitList(TypedDict):
    """API response for kitList."""

    invType: str
    kitType: str
    monthSellEnergyStr: str
    todaySellEnergy: float
    kitSn: str
    updateDateStr: str
    ifShowAFCI: int
    powernower: str
    mastermcufw: str
    type: int
    devicetype: str
    onLineStr: str
    displayfw: str
    devicepc: str
    powernow: float
    isShowBattery: int
    owner: str
    todaySellEnergyStr: str
    index: int
    monthSellEnergy: float
    devicesn: str
    userId: str
    onLine: int
    slavemcufw: str
    isModuleExpire: int
    totalSellEnergy: float
    totalSellEnergyStr: str
    isShowHighVoltBat: int
    isHistory: int
    mark: int
    plantName: str
    dataTimeStr: str
    findRawdataPageList: ESolarStoreFindRawdataPageList
    storeDevicePower: ESolarStoreDevicePower
    status: str


class ESolarBeanList(TypedDict):
    """API response for beanList."""

    pvElec: float
    useElec: float
    buyElec: float
    sellElec: float
    chargeElec: float
    dischargeElec: float
    buyRate: str
    sellRate: str
    selfConsumedRate1: str
    selfConsumedRate2: str
    selfConsumedEnergy1: float
    selfConsumedEnergy2: float
    plantTreeNum: float
    reduceCo2: float
    dataTime: None | int
    devicesn: str


class ESolarPlantDetail(TypedDict):
    """API response for platDetail."""

    type: int
    runningState: int
    nowPower: float
    todayElectricity: float
    monthElectricity: float
    yearElectricity: float
    totalElectricity: float
    totalConsumpElec: None | float
    totalBuyElec: None | float
    totalSellElec: None | float
    selfUseRate: None | str
    income: None | float
    todayGridIncome: None | float
    devOnlineNum: int
    devTotalNum: int
    totalPlantTreeNum: float
    totalReduceCo2: float
    todayAlarmNum: None | int
    lastUploadTime: str
    userType: int
    snList: list[str]
    energyCompareYearList: list[str]


class ESolarPeakList(TypedDict):
    """API response for peakList."""

    devicesn: str
    peakPower: float


class ESolarPlantList(TypedDict):
    """API response for plantList."""

    plantUid: str
    plantName: str
    systempower: float
    currency: str
    type: int
    installername: str
    countryCode: str
    country: str
    province: str
    city: str
    county: str
    foreignRemark: str
    address: str
    latitude: float
    longitude: float
    createDateStr: str
    isOnline: str
    runningState: int
    nowPower: float
    todayElectricity: float
    totalElectricity: float
    enableEdit: str
    enableDelete: str
    enableVisitor: str
    isFavorite: str
    isRename: int
    isMulBind: int
    isTimeError: int
    plantDetail: ESolarPlantDetail
    status: str
    peakList: None | list[ESolarPeakList]
    kitList: None | list[ESolarKitList]
    beanList: None | list[ESolarBeanList]
    devices: dict

class ESolarResponse(TypedDict):
    """API response."""

    plantList: list[ESolarPlantList]


async def update_listener(hass, entry):
    """Handle options update."""
    _LOGGER.debug(entry.options)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up eSolar from a config entry."""
    coordinator = ESolarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class ESolarCoordinator(DataUpdateCoordinator[ESolarResponse]):
    """Data update coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=CONF_UPDATE_INTERVAL),
            # update_interval=timedelta(seconds=20),
        )
        self._entry = entry
        self.temp = 3

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
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except ESolarError as err:
            raise UpdateFailed(str(err)) from err

        return data


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
    plants = options.get(CONF_MONITORED_SITES)
    use_pv_grid_attributes = options.get(CONF_PV_GRID_DATA)

    try:
        _LOGGER.debug(
            "Fetching data with username %s, for plants %s with pv attributes set to %s",
            username,
            plants,
            use_pv_grid_attributes,
        )
        plant_info = get_esolar_data(username, password, plants, use_pv_grid_attributes)

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
