"""ESolar Cloud Platform data fetchers."""
import datetime
import time
import logging
import json
import hashlib
import os
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


def base_url(region):
    """SAJ eSolar Helper Function - Returns the base URL for the region."""
    if region == "eu":
        return "https://eop.saj-electric.com/dev-api/api/v1"
    elif region == "in":
        return "https://iop.saj-electric.com/dev-api/api/v1"
    elif region == "cn":
        return "https://op.saj-electric.cn/dev-api/api/v1"
    else:
        raise ValueError("Region not set. Please run Configure again")

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


def _login_sign_data():
    """Common signed fields used for SAJ v1 login requests."""
    return {
        "appProjectName": "elekeeper",
        "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
        "lang": "en",
        "timeStamp": int(time.time() * 1000),
        "random": generatkey(32),
        "clientId": "esolar-monitor-admin",
    }


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
        signed = calc_signature(_login_sign_data())
        post_data = signed | {
            "type": "pwdLogin",
            "roleType": 1,
            "loginName": username,
        }
        response = session.post(
            base_url(region) + "/sys/common/ali/getCaptchaInfo",
            data=post_data,
            timeout=WEB_TIMEOUT,
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
    data = {
        "refreshToken": refresh_token,
        "appProjectName": "elekeeper",
        "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
        "lang": "en",
        "timeStamp": int(time.time() * 1000),
        "random": generatkey(32),
    }
    signed = calc_signature(data)
    response = session.post(
        base_url(region) + "/sys/refreshToken",
        data=signed,
        timeout=WEB_TIMEOUT,
    )
    response.raise_for_status()
    answer = response.json()

    if answer.get("errCode") != 0:
        _raise_login_error(answer)

    _LOGGER.debug("Refreshed SAJ access token for %s", username)
    return _session_from_token_answer(session, username, password, answer)


def _perform_login(region, session, username, password):
    """Perform a full SAJ v1 password login."""
    if _captcha_required(region, session, username):
        raise ValueError(CAPTCHA_REQUIRED_MSG)

    signed = calc_signature(_login_sign_data())
    login_data = {
        "username": username,
        "password": encrypt(password),
        "rememberMe": "false",
        "loginType": 1,
    }
    response = session.post(
        base_url(region) + "/sys/login",
        data=signed | login_data,
        timeout=WEB_TIMEOUT,
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
        session = requests.Session()
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
    """Retrieve the plantUid from WEB Portal using web_authenticate."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plants")

    if BASIC_TEST:
        return web_get_plant_static_h1_r5()

    try:
        output_plant_list = []
        data = {
            "pageNo": 1,
            "pageSize": 500,
            'appProjectName': 'elekeeper',
            'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
            'lang': 'en',
            'timeStamp': int(time.time() * 1000),
            'random': generatkey(32),
            'clientId': 'esolar-monitor-admin',
        }

        signed = calc_signature(data)

        response = session.get(
            base_url(region) + "/monitor/plant/getEndUserPlantList",
            params=signed,
            timeout=WEB_TIMEOUT,
        )

        response.raise_for_status()

        if response.status_code != 200:
            raise ValueError(f"Get plant error: {response.status_code}")

        plant_list = response.json()
        list_data = _parse_api_data(
            plant_list,
            "getEndUserPlantList",
            auth_critical=True,
        )
        if not isinstance(list_data, dict) or "list" not in list_data:
            raise ValueError(
                "Unexpected plant list response from SAJ API: missing list data"
            )

        if requested_plant_list is not None:
            found_names: list[str] = []
            for plant in list_data["list"]:
                if plant["plantName"] in requested_plant_list:
                    output_plant_list.append(plant)
                    found_names.append(plant["plantName"])
            missing = [name for name in requested_plant_list if name not in found_names]
            result = {"plantList": output_plant_list}
            if missing:
                result[UNAVAILABLE_PLANTS] = missing
            return result

        return {"plantList": list_data["list"]}

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_plant_details(region, session, plant_info):
    """Retrieve plantUid from the WEB Portal using web_authenticate."""
    if session is None:
        raise ValueError("Missing session identifier trying to obain plants")

    try:
        for plant in plant_info["plantList"]:
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
                base_url(region) + "/monitor/plant/getOnePlantInfo", #/monitor/site/getPlantDetailInfo
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get plant detail error: {response.status_code}")

            plant_detail = response.json()
            detail_data = _parse_api_data(
                plant_detail,
                f"getOnePlantInfo for {plant.get('plantName')}",
                required=False,
            )
            if detail_data is None:
                continue
            plant.update(detail_data)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_plant_statistics(region, session, plant_info):
    """Retrieve platUid from the WEB Portal using web_authenticate."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plants")

    try:
         for plant in plant_info["plantList"]:
            if plant.get("type") == 2:
                 continue

            data = {
                "plantUid": plant["plantUid"],
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }

            prepare_data_for_query(plant, data) #add deviceSn or emsSn if needed

            signed = calc_signature(data)

            response = session.get(
                base_url(region) + "/monitor/home/getPlantStatisticsData",
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get plant statistics data error: {response.status_code}")

            plant_statistics = response.json()
            stats_data = _parse_api_data(
                plant_statistics,
                f"getPlantStatisticsData for {plant.get('plantName')}",
                required=False,
            )
            if stats_data is None:
                continue
            if "deviceSnList" in stats_data:
                del stats_data["deviceSnList"]
            if "moduleSnList" in stats_data:
                del stats_data["moduleSnList"]
            plant.update(stats_data)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_device_list(region, session, plant_info):
    """Retrieve a device list from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obain plants")

    try:
        for plant in plant_info["plantList"]:
            data = {
                "plantUid": plant["plantUid"],
                "pageSize": 100,
                "pageNo": 1,
                "searchOfficeIdArr":"1",
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }

            signed = calc_signature(data)

            response = session.get(
                base_url(region) + "/monitor/device/getDeviceList",
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get device {plant['plantName']} deviceList error: {response.status_code}")

            answer = response.json()
            answer_data = _parse_api_data(
                answer,
                f"getDeviceList for {plant.get('plantName')}",
                required=False,
            )
            if not answer_data or "list" not in answer_data:
                continue

            device_list = answer_data["list"]

            if "deviceSnList" not in plant:
                plant["deviceSnList"] = []

            for device in device_list:
                if "deviceSn" in device and device["deviceSn"] not in plant["deviceSnList"]:
                    plant["deviceSnList"].append(device["deviceSn"])

            plant.update({"devices": device_list})

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_device_info(region, session, plant_info):
    """Retrieve device info from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obain plants")

    try:
        for plant in plant_info["plantList"]:
            for device in plant["devices"]:
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
                    base_url(region) + "/monitor/device/getOneDeviceInfo",
                    params = signed,
                    timeout=WEB_TIMEOUT
                )

                response.raise_for_status()

                if response.status_code != 200:
                    raise ValueError(f"Get device {device['deviceSn']} detail error: {response.status_code}")

                device_detail = response.json()
                detail_data = _parse_api_data(
                    device_detail,
                    f"getOneDeviceInfo for {device.get('deviceSn')}",
                    required=False,
                )
                if detail_data is None:
                    continue
                device.update(detail_data)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

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
    """Retrieve plant overview from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obain plants")

    try:
        current_timestamp_sec = time.time()

        one_month_later = datetime.datetime.fromtimestamp(current_timestamp_sec) + relativedelta(months=1)
        timestamp_one_month_later_ms = int(one_month_later.timestamp() * 1000)

        for plant in plant_info["plantList"]:
            if plant.get("type") == 0 and (plant.get("isInstallEms") == 1 or plant.get("isInstallLoraMeter") == 1):
                continue

            data = {
                "plantUid": plant["plantUid"],
                "refresh": timestamp_one_month_later_ms,
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }

            prepare_data_for_query(plant, data) #add deviceSn or emsSn if needed

            signed = calc_signature(data)

            response = session.get(
                base_url(region) + "/monitor/home/getPlantGridOverviewInfo",
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get plant {plant["plantName"]} overview data error: {response.status_code}")

            overview = response.json()
            overview_data = _parse_api_data(
                overview,
                f"getPlantGridOverviewInfo for {plant.get('plantName')}",
                required=False,
            )
            if overview_data is not None:
                plant.update(overview_data)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_plant_flow_data(region, session, plant_info):
    """Retrieve plant flow data from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain plants")

    try:
        for plant in plant_info["plantList"]:
            data = {
                "plantUid": plant["plantUid"],
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }

            prepare_data_for_query(plant, data) #add deviceSn or emsSn if needed

            signed = calc_signature(data)

            response = session.get(
                base_url(region) + "/monitor/home/getDeviceEneryFlowData",  #typo from SAJ
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get plant {plant["plantName"]} energy flow data error: {response.status_code}")

            flow = response.json()
            flow_data = _parse_api_data(
                flow,
                f"getDeviceEneryFlowData for {plant.get('plantName')}",
                required=False,
            )
            if flow_data is not None:
                plant.update(flow_data)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

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
                            if "modules" not in plant:
                                plant["modules"] = []
                            found = False
                            for plant_module in plant["modules"]:
                                if "moduleSn" in plant_module and plant_module["moduleSn"] is not None and \
                                        plant_module["moduleSn"] == module_sn:
                                    plant_module.update(module)
                                    found = True
                            if not found:
                                plant["modules"].append(module)

                            if "moduleSnList" not in plant:
                                plant["moduleSnList"] = {}
                            if module_sn not in plant["moduleSnList"]:
                                plant["moduleSnList"].append(module_sn)

                if "moduleSnList" in plant and plant["moduleSnList"] is not None and len(plant["moduleSnList"]) > 0:
                    for moduleSn in plant["moduleSnList"]:
                        data = {
                            "plantUid": plant["plantUid"],
                            "chartDateType": 5,
                            "chartDay": datetime.date.today().strftime("%Y-%m-%d"),
                            'appProjectName': 'elekeeper',
                            'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                            'lang': 'en',
                            'timeStamp': int(time.time() * 1000),
                            'random': generatkey(32),
                            'clientId': 'esolar-monitor-admin',
                        }

                        if plant.get("type") == 0 and plant.get("isInstallEms") == 1:
                            url = "/monitor/plant/chart/getSecSelfUseEnergyData"
                            prepare_data_for_query(plant, data) #add deviceSn or emsSn if needed
                        elif plant.get("type") == 1 or (plant.get("type") == 0 and plant.get("isInstallMeter") != 0):
                            url = "/monitor/home/getSecSelfUseEnergyData"
                            data["moduleSn"] = moduleSn
                        else:
                            url = "/monitor/plant/chart/getSelfUseEnergyData"
                            prepare_data_for_query(plant, data) #add deviceSn or emsSn if needed

                        signed = calc_signature(data)

                        response = session.get(
                            base_url(region) + url,
                            params = signed,
                            timeout=WEB_TIMEOUT
                        )

                        response.raise_for_status()

                        if response.status_code != 200:
                            raise ValueError(f"Get plant getSecSelfUseEnergyData error: {response.status_code}")

                        answer = response.json()
                        energy_data = _parse_api_data(
                            answer,
                            f"getSecSelfUseEnergyData for {plant.get('plantName')}",
                            required=False,
                        )
                        if energy_data is not None:
                            if "modules" not in plant:
                                plant["modules"] = []
                            found = False
                            for plant_module in plant["modules"]:
                                if "moduleSn" in plant_module and plant_module["moduleSn"] is not None and \
                                        plant_module["moduleSn"] == moduleSn:
                                    plant_module.update(energy_data)
                                    found = True
                            if not found:
                                plant["modules"].append(energy_data)


    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_batteries_data(region, session, plant_info):
    """Retrieve batteries data from the WEB Portal."""
    if session is None:
        raise ValueError("Missing session identifier trying to obtain batteries")

    try:
        for plant in plant_info["plantList"]:
            if "hasBattery" not in plant or plant["hasBattery"] != 1:
                continue

            data = {
                "plantUid": plant["plantUid"],
                "pageSize": 100,
                "pageNo": 1,
                "searchOfficeIdArr":"1",
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }

            signed = calc_signature(data)

            response = session.get(
                base_url(region) + "/monitor/battery/getBatteryList",  #typo from SAJ
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError(f"Get plant {plant["plantName"]} battery list data error: {response.status_code}")

            answer = response.json()
            battery_data = _parse_api_data(
                answer,
                f"getBatteryList for {plant.get('plantName')}",
                required=False,
            )
            if (
                isinstance(battery_data, dict)
                and "list" in battery_data
            ):
                plant["batteries"] = battery_data["list"]

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

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
    """Retrieve a plant alarm list from the WEB Portal"""

    if session is None:
        raise ValueError("Missing session identifier trying to obtain alarms list")

    try:
        for plant in plant_info["plantList"]:
            plant["todayAlarmNum"] = plant.get("todayAlarmNum") or 0
            for device in plant.get("devices", []):
                device["todayAlarmNum"] = device.get("todayAlarmNum") or 0

            data = {
                'appProjectName': 'elekeeper',
                'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                'lang': 'en',
                'timeStamp': int(time.time() * 1000),
                'random': generatkey(32),
                'clientId': 'esolar-monitor-admin',
            }
            now = datetime.datetime.now()
            start = now - datetime.timedelta(days=3)

            payload = {
                "pageNo": 1,
                "pageSize": 10,
                "alarmCommonState": state,              # 1-pending, 2-?, 3-closed, 4-manual close
                "orderByIndex": 1,
                "plantUid": plant["plantUid"],
                "queryStartDate": start.strftime("%Y-%m-%d"),
                "queryEndDate": now.strftime("%Y-%m-%d"),
                "searchOfficeIdArr": 1,
            }

            signed = calc_signature(data)

            response = session.post(
                base_url(region) + "/alarm/device/userAlarmPage",
                data = payload | signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get device {plant["plantUid"]} alarm list error: {response.status_code}")

            answer = response.json()
            answer_data = _parse_api_data(
                answer,
                f"userAlarmPage for {plant.get('plantName')}",
                required=False,
            )
            if answer_data and "list" in answer_data and len(answer_data["list"]) > 0:
                alarm_list = answer_data["list"]
                for alarm in alarm_list:
                    if "alarmStartTime" in alarm and alarm["alarmStartTime"] is not None and is_today(alarm["alarmStartTime"]):
                        plant["todayAlarmNum"] = (plant.get("todayAlarmNum") or 0) + 1
                        for device in plant["devices"]:
                            if device["deviceSn"] == alarm["deviceSn"]:
                                device["todayAlarmNum"] = (device.get("todayAlarmNum") or 0) + 1
                                if "alarmList" not in device:
                                    device["alarmList"] = []
                                del alarm["deviceSn"]
                                del alarm["deviceSnType"]
                                del alarm["plantUid"]
                                del alarm["plantName"]
                                del alarm["plantCountry"]

                                device["alarmList"].append(alarm)
                                break

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)