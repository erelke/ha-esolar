"""ESolar Cloud Platform data fetchers."""
import datetime
import time
import logging
import json
import hashlib
import os
import uuid
import requests
from dateutil.relativedelta import relativedelta
from .elekeeper import calc_signature, encrypt, generatkey, is_today, prepare_data_for_query
from .const import UNAVAILABLE_PLANTS

_LOGGER = logging.getLogger(__name__)

WEB_TIMEOUT = 30
END_USER_PLANT_LIST = None
WEB_PLANT_DATA: dict = {}
CAPTCHA_REQUIRED_MSG = (
    "SAJ login requires captcha verification. "
    "Log in at https://eop.saj-electric.com/ in a browser, then reload the integration."
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

SESSION_AUTH_ERROR_CODES = {401, 403}
SESSION_AUTH_KEYWORDS = (
    "token",
    "token expired",
    "unauthorized",
    "not logged",
    "please log",
    "please login",
    "login again",
    "session expired",
    "session invalid",
)


class SessionAuthError(Exception):
    """Raised when the SAJ API rejects the current session or token."""


BASIC_TEST = False
VERBOSE_DEBUG = False

if BASIC_TEST:
    from .esolar_static_test import (
        web_get_plant_static_h1_r5,
        get_esolar_data_static_file
    )


def portal_origin(region):
    """Return the Elekeeper portal origin for the region."""
    if region == "eu":
        return "https://eop.saj-electric.com"
    elif region == "in":
        return "https://iop.saj-electric.com"
    elif region == "cn":
        return "https://op.saj-electric.cn"
    else:
        raise ValueError("Region not set. Please run Configure again")


def base_url(region):
    """SAJ eSolar Helper Function - Returns the v1 API base URL for the region."""
    return portal_origin(region) + "/dev-api/api/v1"


def base_url_v2(region):
    """Return the SAJ Elekeeper v2 API base URL for the region."""
    return portal_origin(region) + "/dev-api/api/v2"

def dump(region, username, password):
    """ dumps the data for the region, username and password. Called from the CLI. """
    plant_info = get_esolar_data(region, username, password)

    with open('plant_info.json', 'w') as json_file:
        json.dump(plant_info, json_file, indent=4)
    return

def get_esolar_data(region, username, password, plant_list=None, use_pv_grid_attributes=True):
    """SAJ eSolar Data Update."""
    if BASIC_TEST:
        return get_esolar_data_static_file("saj_esolar_air_dusnake_2", plant_list)

    last_auth_error: SessionAuthError | None = None
    for attempt in range(2):
        force_login = attempt > 0
        try:
            return _fetch_esolar_data(
                region,
                username,
                password,
                plant_list,
                use_pv_grid_attributes,
                force_login=force_login,
            )
        except SessionAuthError as err:
            last_auth_error = err
            if attempt == 0:
                _LOGGER.warning(
                    "SAJ session rejected for %s, clearing tokens and re-authenticating: %s",
                    username,
                    err,
                )
                clear_user_tokens(username, password)
                _clear_plant_data_cache(username)
                continue
            break

    raise ValueError(
        f"Invalid authentication credentials: {last_auth_error}"
    ) from last_auth_error


def _clear_plant_data_cache(username: str) -> None:
    """Drop in-memory plant metadata cached for a user."""
    global WEB_PLANT_DATA
    if username in WEB_PLANT_DATA:
        del WEB_PLANT_DATA[username]


def _fetch_esolar_data(
    region,
    username,
    password,
    plant_list=None,
    use_pv_grid_attributes=True,
    *,
    force_login: bool = False,
):
    """Fetch SAJ plant data using the current or freshly obtained session."""
    global WEB_PLANT_DATA

    try:
        session = esolar_web_autenticate(
            region, username, password, force_login=force_login
        )
        plant_info = None
        if (
            not force_login
            and WEB_PLANT_DATA is not None
            and username in WEB_PLANT_DATA
            and WEB_PLANT_DATA[username] is not None
            and "plant_list" in WEB_PLANT_DATA[username]
            and "plant_info" in WEB_PLANT_DATA[username]
            and WEB_PLANT_DATA[username]["plant_list"] == plant_list
            and WEB_PLANT_DATA[username]["plant_info"] is not None
        ):
            plant_info = WEB_PLANT_DATA[username]["plant_info"]

        if plant_info is None:
            _LOGGER.debug("We don't have all plant_info, requesting")
            plant_info = web_get_plant(region, session, plant_list)
            unavailable = plant_info.get(UNAVAILABLE_PLANTS) or []
            if unavailable:
                _LOGGER.warning(
                    "Configured plant(s) no longer accessible for %s: %s",
                    username,
                    ", ".join(unavailable),
                )
            if not plant_info.get("plantList"):
                raise ValueError(
                    "No accessible plants configured: "
                    + ", ".join(unavailable or plant_list or [])
                )
            WEB_PLANT_DATA = {
                username: {"plant_list": plant_list, "plant_info": plant_info}
            }
        else:
            _LOGGER.debug(
                "We have plant data for %s/%s, using cached data",
                username,
                plant_list,
            )

        web_get_plant_details(region, session, plant_info)
        web_get_device_list(region, session, plant_info)
        web_get_sec_statistics(region, session, plant_info)
        web_get_plant_statistics(region, session, plant_info)
        web_get_plant_overview(region, session, plant_info)
        web_get_device_info(region, session, plant_info)
        web_get_plant_flow_data(region, session, plant_info)
        web_get_device_raw_data(region, session, plant_info)
        web_get_alarm_list(region, session, plant_info, 1)
        web_get_alarm_list(region, session, plant_info, 3)

        for plant in plant_info["plantList"]:
            try:
                if "hasBattery" in plant and plant["hasBattery"] == 1:
                    break
                for device in plant["devices"]:
                    stats = device.get("deviceStatisticsData") or {}
                    bat_pct = stats.get("batEnergyPercent")
                    device_bat_pct = device.get("batEnergyPercent")
                    if (
                        ("hasBattery" in device and device["hasBattery"] == 1)
                        or (bat_pct is not None and float(bat_pct) > 0)
                        or (
                            device_bat_pct is not None
                            and int(device_bat_pct) > 0
                        )
                    ):
                        device["hasBattery"] = 1
                        plant["hasBattery"] = 1
                        break
            except Exception as e:
                _LOGGER.error("We don't have a battery for %s: %s", username, e)
        web_get_batteries_data(region, session, plant_info)
        web_get_device_battery_data(region, session, plant_info)

        plant_info["status"] = "success"
        plant_info["stamp"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)
    except ValueError as errv:
        raise ValueError(errv) from errv

    return plant_info


def _v2_common_fields():
    """Common JSON fields used for SAJ v2 login and token requests."""
    return {
        "appProjectName": "elekeeper",
        "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
        "lang": "en",
        "timeStamp": int(time.time() * 1000),
        "clientId": "esolar-monitor-admin",
        "clientCode": "organization",
        "themeColor": "light",
    }


def _prepare_web_session(region):
    """Create a requests session with Elekeeper frontend-like headers."""
    session = requests.Session()
    origin = portal_origin(region)
    common = _v2_common_fields()
    session.headers.update(
        {
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en",
            "Origin": origin,
            "Referer": origin + "/",
            "Content-Language": "zh_CN",
            "lang": "en",
            "X-App-Project-Name": common["appProjectName"],
            "X-Client-Code": common["clientCode"],
            "X-Client-Date": common["clientDate"],
            "X-Lang": common["lang"],
            "X-Timestamp": str(common["timeStamp"]),
            "X-Theme-Color": common["themeColor"],
            "X-Trace-Id": uuid.uuid4().hex[:16],
        }
    )
    return session


def _v2_request_headers(common):
    """Per-request v2 headers that must stay in sync with the JSON body."""
    return {
        "Content-Type": "application/json;charset=utf-8",
        "X-App-Project-Name": common["appProjectName"],
        "X-Client-Code": common["clientCode"],
        "X-Client-Date": common["clientDate"],
        "X-Lang": common["lang"],
        "X-Timestamp": str(common["timeStamp"]),
        "X-Theme-Color": common["themeColor"],
        "X-Trace-Id": uuid.uuid4().hex[:16],
    }


def _post_v2(session, region, path, payload):
    """POST JSON to a SAJ v2 endpoint using Elekeeper frontend headers."""
    common = _v2_common_fields()
    return session.post(
        base_url_v2(region) + path,
        json=payload | common,
        headers=_v2_request_headers(common),
        timeout=WEB_TIMEOUT,
    )


def _is_session_auth_error(answer: dict) -> bool:
    """Return True when a SAJ API response indicates an invalid session or token."""
    err_code = answer.get("errCode", 0)
    if err_code == 0:
        return False

    err_msg = (answer.get("errMsg") or "").lower()
    if "captcha" in err_msg:
        return True
    if err_code in SESSION_AUTH_ERROR_CODES:
        return True
    if err_code == 10004 and any(
        keyword in err_msg for keyword in ("invalid", "password", "token", "login")
    ):
        return True
    return any(keyword in err_msg for keyword in SESSION_AUTH_KEYWORDS)


def _parse_api_data(
    answer: dict,
    context: str,
    *,
    required: bool = True,
    auth_critical: bool = False,
):
    """Validate a SAJ API response and return its data payload."""
    err_code = answer.get("errCode", 0)
    err_msg = answer.get("errMsg")

    if err_code != 0:
        if _is_session_auth_error(answer):
            if auth_critical or required:
                raise SessionAuthError(
                    f"SAJ session rejected for {context} "
                    f"(errCode={err_code}, errMsg={err_msg})"
                )
            _LOGGER.warning(
                "SAJ API auth-like response for %s (errCode=%s, errMsg=%s)",
                context,
                err_code,
                err_msg,
            )
            return None
        err_msg_lower = (err_msg or "").lower()
        if "captcha" in err_msg_lower:
            raise ValueError(CAPTCHA_REQUIRED_MSG)
        if required:
            raise ValueError(
                f"SAJ API error for {context} (errCode={err_code}, errMsg={err_msg})"
            )
        _LOGGER.warning(
            "SAJ API error for %s (errCode=%s, errMsg=%s)",
            context,
            err_code,
            err_msg,
        )
        return None

    data = answer.get("data")
    if data is None:
        if auth_critical:
            raise SessionAuthError(
                f"No data in SAJ response for {context} (session may be invalid)"
            )
        if required:
            _LOGGER.warning(
                "No data in SAJ response for %s (errCode=%s, errMsg=%s)",
                context,
                err_code,
                err_msg,
            )
        return None

    return data


def _session_from_token_answer(session, username, password, answer):
    """Store token data from a login/refresh response and return the session."""
    data = answer.get("data") or {}
    if "token" not in data or "expiresIn" not in data:
        _LOGGER.error("Token missing from answer: %s", answer)
        raise ValueError("Token not found in answer: " + json.dumps(answer))

    expires_in = int(data["expiresIn"])
    expires_at = int(time.time() + expires_in) - 9
    token_head = data.get("tokenHead") or "Bearer "
    authorization_token = token_head + data["token"]
    refresh_token = data.get("refreshToken")

    store_user_data(username, password, authorization_token, expires_at, refresh_token)
    session.headers.update({"Authorization": authorization_token})
    _LOGGER.debug(
        "Using token, expires in %s seconds (refresh token: %s)",
        int(expires_at - time.time()),
        "yes" if refresh_token else "no",
    )
    return session


def _raise_login_error(answer):
    """Raise a ValueError for a failed SAJ auth API response."""
    err_code = answer.get("errCode")
    err_msg = answer.get("errMsg") or "Unknown error"
    err_msg_lower = err_msg.lower()

    if err_code == 10004 or "invalid" in err_msg_lower or "password" in err_msg_lower:
        raise ValueError(f"Invalid authentication credentials: {err_msg}")
    if "captcha" in err_msg_lower:
        raise ValueError(CAPTCHA_REQUIRED_MSG)
    raise ValueError(f"Error message in answer: {err_msg}")


def _captcha_required(region, session, username):
    """Return True when SAJ requires captcha before password login."""
    try:
        response = _post_v2(
            session,
            region,
            "/sys/common/ali/getCaptchaInfo",
            {
                "type": "pwdLogin",
                "roleType": 1,
                "loginName": username,
            },
        )
        if response.status_code != 200:
            _LOGGER.debug("Captcha check unavailable, status %s", response.status_code)
            return False

        answer = response.json()
        if answer.get("errCode") != 0:
            _LOGGER.debug("Captcha check returned: %s", answer.get("errMsg"))
            return False

        info = answer.get("data") or {}
        return bool(info.get("sceneId") or info.get("prefix") or info.get("captchaUuid"))
    except Exception as err:
        _LOGGER.debug("Captcha check skipped: %s", err)
        return False


def _refresh_access_token(region, session, username, password, refresh_token):
    """Refresh the bearer token using a stored refresh token."""
    response = _post_v2(
        session,
        region,
        "/sys/user/refreshToken",
        {
            "refreshToken": refresh_token,
            "loginType": 1,
        },
    )
    response.raise_for_status()
    answer = response.json()

    if answer.get("errCode") != 0:
        _raise_login_error(answer)

    _LOGGER.debug("Refreshed SAJ access token for %s", username)
    return _session_from_token_answer(session, username, password, answer)


def _perform_login(region, session, username, password):
    """Perform a full SAJ v2 password login."""
    if _captcha_required(region, session, username):
        raise ValueError(CAPTCHA_REQUIRED_MSG)

    response = _post_v2(
        session,
        region,
        "/sys/user/login",
        {
            "username": username,
            "password": encrypt(password),
            "rememberMe": False,
            "loginType": 1,
        },
    )
    response.raise_for_status()
    answer = response.json()

    if answer.get("errCode") != 0:
        _LOGGER.error("Login failed: %s", answer.get("errMsg"))
        clear_user_tokens(username, password)
        _raise_login_error(answer)

    _LOGGER.debug("Performed SAJ password login for %s", username)
    return _session_from_token_answer(session, username, password, answer)


def esolar_web_autenticate(region, username, password, force_login=False):
    """Authenticate the user to the SAJ's WEB Portal."""
    if BASIC_TEST:
        return True

    try:
        session = _prepare_web_session(region)
        stored_data = read_user_data(username, password)

        if (
            not force_login
            and "error" not in stored_data
            and stored_data.get("token")
        ):
            authorization_expires = int(stored_data["expires"])
            dt = datetime.datetime.fromtimestamp(authorization_expires).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            _LOGGER.debug("Using disk cached token, expires at %s", dt)
            session.headers.update({"Authorization": stored_data["token"]})
            return session

        refresh_token = stored_data.get("refresh_token")
        if (
            not force_login
            and "error" not in stored_data
            and refresh_token
        ):
            _LOGGER.debug(
                "Access token expired, trying refresh token for %s", username
            )
            try:
                return _refresh_access_token(
                    region, session, username, password, refresh_token
                )
            except (ValueError, requests.exceptions.RequestException) as err:
                _LOGGER.warning("Token refresh failed for %s: %s", username, err)
                clear_user_tokens(username, password)

        if force_login:
            _LOGGER.debug("Forced re-login for %s", username)
        else:
            _LOGGER.debug("No valid token for %s, performing password login", username)
        return _perform_login(region, session, username, password)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def clear_user_tokens(username: str, password: str, filename="user_data.json"):
    """Remove cached SAJ tokens for a user."""
    store_user_data(username, password, None, None, None, filename=filename)


def store_user_data(username: str, password: str, token: str|None, expires: int|None, refresh_token: str|None = None, filename="user_data.json"):
    """Felhasználói adatokat tárol és frissít egy JSON fájlban, jelszó hash-eléssel."""
    file_path = os.path.join(os.path.dirname(__file__), filename)

    # Jelszó hash-elése
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    # Betöltjük az aktuális adatokat, ha a fájl létezik
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            try:
                user_data = json.load(file)
            except json.JSONDecodeError:
                user_data = {}  # Ha a fájl üres vagy hibás, létrehozzuk az üres adatstruktúrát
    else:
        user_data = {}

    # Frissítés vagy új bejegyzés létrehozása
    user_data[username] = {
        "password_hash": password_hash,
        "token": token,
        "expires": expires,
        "expires_hrs": (
            datetime.datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M:%S")
            if expires
            else None
        ),
        "refresh_token": refresh_token,
        "last_update": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Adatok mentése
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(user_data, file, indent=4)

def read_user_data(username: str, password: str, filename="user_data.json"):
    """Felhasználó hitelesítése és token visszaadása, ha még érvényes."""
    file_path = os.path.join(os.path.dirname(__file__), filename)

    # Ha a fájl nem létezik, nincs mit ellenőrizni
    if not os.path.exists(file_path):
        return {"error": "Nincs ilyen adatfájl."}

    # Fájl beolvasása
    with open(file_path, "r", encoding="utf-8") as file:
        try:
            user_data = json.load(file)
        except json.JSONDecodeError:
            return {"error": "Hibás JSON fájl."}

    # Ellenőrizzük, hogy a username létezik-e
    if username not in user_data:
        return {"error": "Érvénytelen felhasználónév."}

    stored_password_hash = user_data[username]["password_hash"]
    token = user_data[username]["token"]
    expires = user_data[username]["expires"]
    refresh_token = user_data[username]["refresh_token"] if "refresh_token" in user_data[username] else None

    # Jelszó ellenőrzése
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if password_hash != stored_password_hash:
        return {"error": "Helytelen jelszó."}

    current_time = int(time.time())
    if token and expires and expires > current_time:
        return {"token": token, "expires": expires, "refresh_token": refresh_token}

    if refresh_token:
        return {"refresh_token": refresh_token}

    return {"error": "A token lejárt."}


def web_get_plant(region, session, requested_plant_list=None):
    """Retrieve plants from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plants")

    if BASIC_TEST:
        return web_get_plant_static_h1_r5()

    response = _post_v2(
        session,
        region,
        "/monitor/plant/getEndUserPlantList",
        {
            "pageNo": 1,
            "pageSize": 500,
        },
    )
    response.raise_for_status()

    list_data = _parse_api_data(
        response.json(),
        "getEndUserPlantList",
        auth_critical=True,
    )

    if not isinstance(list_data, dict) or "list" not in list_data:
        raise ValueError(
            "Unexpected plant list response from SAJ API: missing list data"
        )

    plants = list_data["list"]

    if requested_plant_list is not None:
        output_plant_list = []
        found_names = []

        for plant in plants:
            if plant.get("plantName") in requested_plant_list:
                output_plant_list.append(plant)
                found_names.append(plant.get("plantName"))

        missing = [
            name for name in requested_plant_list
            if name not in found_names
        ]

        result = {"plantList": output_plant_list}
        if missing:
            result[UNAVAILABLE_PLANTS] = missing
        return result

    return {"plantList": plants}


def web_get_plant_details(region, session, plant_info):
    """Retrieve plant details from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plants")

    for plant in plant_info["plantList"]:
        response = _post_v2(
            session,
            region,
            "/monitor/plant/getOnePlantInfoV2",
            {
                "plantUid": plant["plantUid"],
            },
        )
        response.raise_for_status()

        detail_data = _parse_api_data(
            response.json(),
            f"getOnePlantInfoV2 for {plant.get('plantName')}",
            required=False,
        )

        if isinstance(detail_data, dict):
            plant.update(detail_data)


def web_get_plant_statistics(region, session, plant_info):
    """Retrieve plant energy statistics from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plant statistics")

    for plant in plant_info["plantList"]:
        if plant.get("type") == 2:
            continue

        device_sn = None

        if plant.get("deviceSn"):
            device_sn = plant.get("deviceSn")
        elif plant.get("deviceSnList"):
            device_sn = plant["deviceSnList"][0]

        if not device_sn:
            _LOGGER.debug(
                "Skipping plant statistics for %s: no device serial",
                plant.get("plantName"),
            )
            continue

        response = _post_v2(
            session,
            region,
            "/monitor/plantHome/getPlantEnergyStatistics",
            {
                "plantUid": plant["plantUid"],
                "sn": device_sn,
                "snType": 1,
            },
        )
        response.raise_for_status()

        stats_data = _parse_api_data(
            response.json(),
            f"getPlantEnergyStatistics for {plant.get('plantName')}",
            required=False,
        )

        if not isinstance(stats_data, dict):
            continue

        stats_data.pop("deviceSnList", None)
        stats_data.pop("moduleSnList", None)
        plant.update(stats_data)

        # Environmental totals returned by Elekeeper v2.
        for item in stats_data.get("environmentalInformation", []) or []:
            description = item.get("describe", "")
            value = item.get("value")

            if value is None:
                continue

            if "CO₂ emissions reduced" in description:
                plant["totalReduceCo2"] = value
            elif "Equivalent tree planting" in description:
                plant["totalPlantTreeNum"] = value
            elif "Standard coal saved" in description:
                plant["totalCoal"] = value

        # Income compatibility.
        for item in stats_data.get("webIncomeDataList", []) or []:
            if item.get("incomeKey") != "PV_INCOME":
                continue

            if item.get("incomeToday") is not None:
                plant["incomeToday"] = item["incomeToday"]
                plant["todayIncome"] = item["incomeToday"]

            if item.get("incomeTotal") is not None:
                plant["incomeTotal"] = item["incomeTotal"]
                plant["totalIncome"] = item["incomeTotal"]

        # Energy compatibility.
        for item in stats_data.get("energyDataList", []) or []:
            data_type = item.get("dataType")

            if data_type == "PV_ENERGY":
                if item.get("energy1Today") is not None:
                    plant["todayPvEnergy"] = item["energy1Today"]

                if item.get("energy1Total") is not None:
                    plant["totalPvEnergy"] = item["energy1Total"]

                if item.get("selfUsePercentage") is not None:
                    plant["selfUsePercentage"] = item["selfUsePercentage"]
                    plant["selfUsePercent"] = item["selfUsePercentage"]

            elif data_type == "LOAD_ENERGY":
                if item.get("energy1Today") is not None:
                    plant["todayLoadEnergy"] = item["energy1Today"]

                if item.get("energy1Total") is not None:
                    plant["totalLoadEnergy"] = item["energy1Total"]

            elif data_type == "BUY_AND_SELL":
                if item.get("energy1Today") is not None:
                    plant["todayBuyEnergy"] = item["energy1Today"]

                if item.get("energy1Total") is not None:
                    plant["totalBuyEnergy"] = item["energy1Total"]

                if item.get("energy2Today") is not None:
                    plant["todaySellEnergy"] = item["energy2Today"]

                if item.get("energy2Total") is not None:
                    plant["totalSellEnergy"] = item["energy2Total"]

            elif data_type == "CHARGE_AND_DISCHARGE":
                if item.get("energy1Today") is not None:
                    plant["todayChargeEnergy"] = item["energy1Today"]

                if item.get("energy1Total") is not None:
                    plant["totalChargeEnergy"] = item["energy1Total"]

                if item.get("energy2Today") is not None:
                    plant["todayDisChargeEnergy"] = item["energy2Today"]

                if item.get("energy2Total") is not None:
                    plant["totalDisChargeEnergy"] = item["energy2Total"]

        # Month/year chart statistics.
        chart_series_map = {
            "PV_PRODUCTION": "PvEnergy",
            "CONSUMPTION": "LoadEnergy",
            "IMPORT_ENERGY": "BuyEnergy",
            "EXPORT_ENERGY": "SellEnergy",
            "CHARGING_ENERGY": "BatChgEnergy",
            "DISCHARGE_ENERGY": "BatDischgEnergy",
        }

        today = datetime.date.today()

        chart_periods = (
            (
                "month",
                {
                    "chartDateType": 3,
                    "chartMonth": today.strftime("%Y-%m"),
                },
            ),
            (
                "year",
                {
                    "chartDateType": 4,
                    "chartYear": today.strftime("%Y"),
                },
            ),
        )

        for legacy_prefix, period_payload in chart_periods:
            chart_response = _post_v2(
                session,
                region,
                "/monitor/plant/chart/getCommonChartData",
                {
                    **period_payload,
                    "snType": 1,
                    "deviceSn": device_sn,
                    "commonChartType": 3,
                },
            )
            chart_response.raise_for_status()

            chart_data = _parse_api_data(
                chart_response.json(),
                f"getCommonChartData {legacy_prefix} for "
                f"{plant.get('plantName')}",
                required=False,
            )

            if not isinstance(chart_data, dict):
                continue

            for series in chart_data.get("yAxis", []) or []:
                suffix = chart_series_map.get(series.get("legendKey"))
                if suffix is None:
                    continue

                total = 0.0
                has_value = False

                for value in series.get("dataList", []) or []:
                    if value in (None, "", "--"):
                        continue

                    try:
                        total += float(value)
                        has_value = True
                    except (TypeError, ValueError):
                        continue

                if has_value:
                    plant[f"{legacy_prefix}{suffix}"] = round(total, 2)

        # Derive daily environmental values using SAJ's own total ratios.
        today_pv = plant.get("todayPvEnergy")
        total_pv = plant.get("totalPvEnergy")

        if today_pv is not None and total_pv not in (None, 0, 0.0):
            total_co2 = plant.get("totalReduceCo2")
            total_trees = plant.get("totalPlantTreeNum")
            total_coal = plant.get("totalCoal")

            if total_co2 is not None:
                plant["todayReduceCo2"] = round(
                    float(today_pv) * float(total_co2) / float(total_pv),
                    4,
                )

            if total_trees is not None:
                plant["todayPlantTreeNum"] = round(
                    float(today_pv) * float(total_trees) / float(total_pv),
                    4,
                )

            if total_coal is not None:
                plant["todayCoal"] = round(
                    float(today_pv) * float(total_coal) / float(total_pv),
                    4,
                )

def web_get_device_list(region, session, plant_info):
    """Retrieve devices from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain devices")

    def collect_device_sns(devices):
        """Collect serial numbers from the v2 device tree."""
        serials = []

        for device in devices or []:
            device_sn = device.get("deviceSn")
            if device_sn:
                serials.append(device_sn)

            serials.extend(
                collect_device_sns(device.get("children") or [])
            )

        return serials

    for plant in plant_info["plantList"]:
        response = _post_v2(
            session,
            region,
            "/monitor/plantDevice/listForWeb",
            {
                "plantUid": plant["plantUid"],
            },
        )
        response.raise_for_status()

        device_data = _parse_api_data(
            response.json(),
            f"listForWeb for {plant.get('plantName')}",
            required=False,
        )

        if not isinstance(device_data, list):
            continue

        plant["devices"] = device_data

        device_sn_list = plant.setdefault("deviceSnList", [])
        for device_sn in collect_device_sns(device_data):
            if device_sn not in device_sn_list:
                device_sn_list.append(device_sn)


def web_get_device_info(region, session, plant_info):
    """Retrieve inverter details from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain device info")

    for plant in plant_info["plantList"]:
        for device in plant.get("devices", []):
            device_sn = device.get("deviceSn")
            if not device_sn:
                continue

            response = _post_v2(
                session,
                region,
                "/monitor/device/baseInverterDetail",
                {
                    "deviceSn": device_sn,
                },
            )
            response.raise_for_status()

            detail_data = _parse_api_data(
                response.json(),
                f"baseInverterDetail for {device_sn}",
                required=False,
            )

            if isinstance(detail_data, dict):
                device.update(detail_data)

def web_get_device_raw_data(region, session, plant_info):
    """Retrieve platUid from the WEB Portal using web_authenticate."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plants raw data")

    try:
        for plant in plant_info["plantList"]:
            for device in plant["devices"]:
                if device.get("type", 0) != 0:
                    continue

                data = {
                    'appProjectName': 'elekeeper',
                    'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                    'lang': 'en',
                    'timeStamp': int(time.time() * 1000),
                    'random': generatkey(32),
                    'clientId': 'esolar-monitor-admin',
                }
                now = datetime.datetime.now()
                plus_one_hour_end = now.replace(minute=59, second=59) + datetime.timedelta(hours=1)
                yesterday = plus_one_hour_end - datetime.timedelta(days=1)
                payload = {
                    "deviceSn": device["deviceSn"],
                    "pageSize": 10,
                    "pageNo": 1,
                    "deviceType": 0,
                    'timeStr': yesterday.strftime("%Y-%m-%d %H:%M:%S"),
                    "startTime": yesterday.strftime("%Y-%m-%d %H:%M:%S"),
                    "endTime": plus_one_hour_end.strftime("%Y-%m-%d %H:%M:%S"),
                }

                signed = calc_signature(data)

                response = session.post(
                    base_url(region) + "/monitor/deviceData/findRawdataPageList",
                    data = payload | signed,
                    timeout=WEB_TIMEOUT
                )

                response.raise_for_status()

                if response.status_code != 200:
                    raise ValueError(f"Get device {device['deviceSn']} raw data error: {response.status_code}")

                raw = response.json()
                raw_data_payload = _parse_api_data(
                    raw,
                    f"findRawdataPageList for {device.get('deviceSn')}",
                    required=False,
                )
                if (
                    not isinstance(raw_data_payload, dict)
                    or "list" not in raw_data_payload
                    or len(raw_data_payload["list"]) == 0
                ):
                    continue

                raw_data = raw_data_payload["list"][0]
                add_data = {}
                keys = ["deviceTemp", "deviceTempStr", "backupTotalLoadPowerWatt", "isShowModuleSignal", "moduleSignal", "pVP", "pac"]
                for key in keys:
                    if key in raw_data:
                        add_data[key] = raw_data[key]
                    else:
                        add_data[key] = 0

                if "datetime" in raw_data:
                    add_data['raw_datetime'] = raw_data["datetime"]
                else:
                    add_data['raw_datetime'] = ''
                device.update(add_data)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)


def web_get_plant_overview(region, session, plant_info):
    """Retrieve plant overview from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plant overview")

    for plant in plant_info["plantList"]:
        if (
            plant.get("type") == 0
            and (
                plant.get("isInstallEms") == 1
                or plant.get("isInstallLoraMeter") == 1
            )
        ):
            continue

        device_sn = None

        if plant.get("deviceSn"):
            device_sn = plant.get("deviceSn")
        elif plant.get("deviceSnList"):
            device_sn = plant["deviceSnList"][0]

        if not device_sn:
            continue

        response = _post_v2(
            session,
            region,
            "/monitor/plantHome/getDeviceEnergyFlowDiagram",
            {
                "plantUid": plant["plantUid"],
                "sn": device_sn,
                "snType": 1,
            },
        )
        response.raise_for_status()

        overview_data = _parse_api_data(
            response.json(),
            f"getDeviceEnergyFlowDiagram for {plant.get('plantName')}",
            required=False,
        )

        if isinstance(overview_data, dict):
            plant.update(overview_data)

            # v1 compatibility: legacy dashboard sensor expects this spelling.
            if (
                plant.get("outPutDirection") is None
                and plant.get("outputDirection") is not None
            ):
                plant["outPutDirection"] = plant["outputDirection"]


def web_get_plant_flow_data(region, session, plant_info):
    """Retrieve live plant energy flow data from Elekeeper v2."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain flow data")

    for plant in plant_info["plantList"]:
        device_sn = None

        if plant.get("deviceSn"):
            device_sn = plant.get("deviceSn")
        elif plant.get("deviceSnList"):
            device_sn = plant["deviceSnList"][0]

        if not device_sn:
            continue

        response = _post_v2(
            session,
            region,
            "/monitor/plantHome/getDeviceEnergyFlowDiagram",
            {
                "plantUid": plant["plantUid"],
                "sn": device_sn,
                "snType": 1,
            },
        )
        response.raise_for_status()

        flow_data = _parse_api_data(
            response.json(),
            f"getDeviceEnergyFlowDiagram for {plant.get('plantName')}",
            required=False,
        )

        if isinstance(flow_data, dict):
            plant.update(flow_data)

            if (
                plant.get("outPutDirection") is None
                and plant.get("outputDirection") is not None
            ):
                plant["outPutDirection"] = plant["outputDirection"]

def _normalize_module_energy(energy_data, module_sn):
    """Map v2 meter/flow fields onto the module shape used by sensors."""
    if not isinstance(energy_data, dict):
        return None
    if energy_data.get("gridPower") is None:
        grid = energy_data.get("sysGridPowerwatt")
        if grid is None:
            grid = energy_data.get("gridPowerwatt")
        if grid is not None:
            energy_data["gridPower"] = grid
    energy_data.setdefault("moduleSn", module_sn)
    return energy_data


def _merge_plant_module(plant, module_sn, payload):
    """Insert or update a SEC/meter module on the plant."""
    if not payload:
        return
    if "modules" not in plant or plant["modules"] is None:
        plant["modules"] = []
    for plant_module in plant["modules"]:
        if plant_module.get("moduleSn") == module_sn:
            plant_module.update(payload)
            return
    plant["modules"].append(payload)


def _fetch_module_energy(region, session, plant, module_sn):
    """Fetch live meter power using current Elekeeper v2 APIs."""
    is_ems_plant = plant.get("type") == 0 and plant.get("isInstallEms") == 1
    is_meter_plant = plant.get("type") == 1 or (
        plant.get("type") == 0 and plant.get("isInstallMeter") != 0
    )

    if is_meter_plant and not is_ems_plant:
        response = _post_v2(
            session,
            region,
            "/monitor/plantHome/getDeviceEnergyFlowDiagram",
            {
                "plantUid": plant["plantUid"],
                "sn": module_sn,
                "snType": 2,
            },
        )
        context = f"getDeviceEnergyFlowDiagram for {plant.get('plantName')}"
    else:
        payload = {
            "plantUid": plant["plantUid"],
            "chartDateType": 1,
            "chartDay": datetime.date.today().strftime("%Y-%m-%d"),
        }
        prepare_data_for_query(plant, payload)
        response = _post_v2(
            session,
            region,
            "/monitor/plant/chart/getSelfUseEnergyData",
            payload,
        )
        context = f"getSelfUseEnergyData for {plant.get('plantName')}"

    response.raise_for_status()
    energy_data = _parse_api_data(response.json(), context, required=False)
    return _normalize_module_energy(energy_data, module_sn)


def web_get_sec_statistics(region, session, plant_info):
    """Retrieve SEC/EMS devices from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain sec devices")

    try:
        for plant in plant_info["plantList"]:
            if "isInstallMeter" in plant and plant["isInstallMeter"] == 1:
                data = {
                    "plantUid": plant["plantUid"],
                    'appProjectName': 'elekeeper',
                    'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                    'lang': 'en',
                    'timeStamp': int(time.time() * 1000),
                    'random': generatkey(32),
                    'clientId': 'esolar-monitor-admin',
                }

                signed = calc_signature(data)

                response = session.get(
                    base_url(region) + "/monitor/sec/plantSECModuleList",
                    params=signed,
                    timeout=WEB_TIMEOUT
                )

                response.raise_for_status()

                if response.status_code != 200:
                    raise ValueError(f"Get plant SECModuleList data error: {response.status_code}")

                answer = response.json()
                module_data = _parse_api_data(
                    answer,
                    f"plantSECModuleList for {plant.get('plantName')}",
                    required=False,
                )
                if module_data is not None and len(module_data) > 0:
                    for module in module_data:
                        if "moduleSn" in module and module["moduleSn"] is not None:
                            module_sn = module["moduleSn"]
                            _merge_plant_module(plant, module_sn, module)

                            if "moduleSnList" not in plant or plant["moduleSnList"] is None:
                                plant["moduleSnList"] = []
                            if module_sn not in plant["moduleSnList"]:
                                plant["moduleSnList"].append(module_sn)

                if "moduleSnList" in plant and plant["moduleSnList"] is not None and len(plant["moduleSnList"]) > 0:
                    for moduleSn in plant["moduleSnList"]:
                        energy_data = _fetch_module_energy(
                            region, session, plant, moduleSn
                        )
                        if energy_data is not None:
                            _merge_plant_module(plant, moduleSn, energy_data)


    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)


def web_get_batteries_data(region, session, plant_info):
    """Retrieve battery data from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain batteries")

    for plant in plant_info["plantList"]:
        if plant.get("hasBattery") != 1:
            continue

        devices = plant.get("devices") or []

        device = next(
            (
                item
                for item in devices
                if item.get("deviceType") == 1
                or item.get("type") == 1
            ),
            None,
        )

        if device is None:
            device = next(
                (item for item in devices if item.get("deviceSn")),
                None,
            )

        if device is None:
            continue

        device_sn = device.get("deviceSn")
        if not device_sn:
            continue

        response = _post_v2(
            session,
            region,
            "/monitor/device/getInverterBatteryEnergyDetailForApp",
            {
                "deviceSn": device_sn,
            },
        )
        response.raise_for_status()

        battery_data = _parse_api_data(
            response.json(),
            f"getInverterBatteryEnergyDetailForApp for {device_sn}",
            required=False,
        )

        if not isinstance(battery_data, dict):
            continue

        battery_data["batSn"] = device_sn
        battery_data.setdefault(
            "batModel",
            battery_data.get("batteryName"),
        )
        battery_data.setdefault("bmsSoftwareVersion", None)
        battery_data.setdefault("bmsHardwareVersion", None)
        battery_data.setdefault("bmsSn", None)

        plant["batteries"] = [battery_data]
        device.update(battery_data)

        statistics = device.setdefault("deviceStatisticsData", {})

        compatibility_keys = (
            "batEnergyPercent",
            "batCapacity",
            "batCurrent",
            "batPower",
            "batVoltage",
            "batTemperature",
            "todayBatChgEnergy",
            "todayBatDisEnergy",
            "totalBatChgEnergy",
            "totalBatDisEnergy",
            "usableBatCapacity",
            "batteryWorkTime",
            "batteryDirection",
            "runningState",
            "updateDate",
        )

        for key in compatibility_keys:
            if battery_data.get(key) is not None:
                statistics[key] = battery_data[key]

        if battery_data.get("batCapacity") is not None:
            statistics["batCapcity"] = battery_data["batCapacity"]
            statistics["batCapicity"] = battery_data["batCapacity"]

        statistics["totalLoadPowerwatt"] = (
            plant.get("totalLoadPowerwatt")
            if plant.get("totalLoadPowerwatt") is not None
            else plant.get("totalLoadPowerWatt")
        )

        if plant.get("gridDirection") is not None:
            statistics["gridDirection"] = plant["gridDirection"]

        if battery_data.get("batteryDirection") is not None:
            statistics["batteryDirection"] = battery_data["batteryDirection"]

def web_get_device_battery_data(region, session, plant_info):
    """Retrieve nuilt in battery data from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain battery data")

    try:
        for plant in plant_info["plantList"]:
            for device in plant["devices"]:
                if device.get("hasBattery",0) == 0 or device.get("type",0) != 2: #only for devices with builtin batteries
                    continue

                data = {
                    "deviceSn": device["deviceSn"],
                    'appProjectName': 'elekeeper',
                    'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                    'lang': 'en',
                    'timeStamp': int(time.time() * 1000),
                    'random': generatkey(32),
                    'clientId': 'esolar-monitor-admin',
                }

                signed = calc_signature(data)

                response = session.get(
                    base_url(region) + "/monitor/battery/getOneDeviceBatteryInfo",  #typo from SAJ
                    params = signed,
                    timeout=WEB_TIMEOUT
                )

                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError(f"Get plant {plant["plantName"]} battery list data error: {response.status_code}")

                answer = response.json()
                battery_info = _parse_api_data(
                    answer,
                    f"getOneDeviceBatteryInfo for {device.get('deviceSn')}",
                    required=False,
                )
                if battery_info is None:
                    continue
                if "baseBatteryBtnBeanList" in battery_info:
                    del battery_info["baseBatteryBtnBeanList"]
                if "batteries" in plant and plant["batteries"] is not None:
                    for battery in plant["batteries"]:
                        if battery["batSn"] == device["deviceSn"]:
                            battery.update(battery_info)
                else:
                    device.update(battery_info)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_ems_list(region, session, plant_info):
    """Retrieve a communication moduls list from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain ems")

    try:
        for plant in plant_info["plantList"]:
            data = {
                "plantUid": plant["plantUid"],
                "pageSize": 100,
                "pageNo": 1,
                "usePage": 1,
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }

            signed = calc_signature(data)

            response = session.get(
                base_url(region) + "/monitor/plant/ems/getEmsListByPlant",
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get device {plant['plantName']} deviceList error: {response.status_code}")

            answer = response.json()
            ems_data = _parse_api_data(
                answer,
                f"getEmsListByPlant for {plant.get('plantName')}",
                required=False,
            )
            if isinstance(ems_data, dict) and "list" in ems_data:
                ems_list = ems_data["list"]
            else:
                continue

            plant.update({"emsModules": ems_list})

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)


def web_get_alarm_list(region, session, plant_info, state: int = 3):
    """Retrieve plant alarms from the SAJ Elekeeper v2 API."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain alarms list")

    for plant in plant_info["plantList"]:
        plant["todayAlarmNum"] = plant.get("todayAlarmNum") or 0

        for device in plant.get("devices", []):
            device["todayAlarmNum"] = device.get("todayAlarmNum") or 0

        response = _post_v2(
            session,
            region,
            "/devicedata/alarm/device/userAlarmPage",
            {
                "plantUid": plant["plantUid"],
                "alarmCommonState": state,
                "pageNo": 1,
                "pageSize": 10,
            },
        )
        response.raise_for_status()

        answer_data = _parse_api_data(
            response.json(),
            f"userAlarmPage for {plant.get('plantName')}",
            required=False,
        )

        if not isinstance(answer_data, dict):
            continue

        alarm_list = answer_data.get("list") or []

        for alarm in alarm_list:
            alarm_start = alarm.get("alarmStartTime")

            if not alarm_start or not is_today(alarm_start):
                continue

            plant["todayAlarmNum"] = (
                plant.get("todayAlarmNum") or 0
            ) + 1

            alarm_device_sn = alarm.get("deviceSn")

            for device in plant.get("devices", []):
                if device.get("deviceSn") != alarm_device_sn:
                    continue

                device["todayAlarmNum"] = (
                    device.get("todayAlarmNum") or 0
                ) + 1

                device.setdefault("alarmList", [])

                alarm_copy = dict(alarm)
                alarm_copy.pop("deviceSn", None)
                alarm_copy.pop("deviceSnType", None)
                alarm_copy.pop("plantUid", None)

                device["alarmList"].append(alarm_copy)
                break
