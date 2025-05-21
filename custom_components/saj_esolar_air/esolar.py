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

_LOGGER = logging.getLogger(__name__)

WEB_TIMEOUT = 30
END_USER_PLANT_LIST = None
WEB_PLANT_DATA: dict = {}

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

    global WEB_PLANT_DATA

    try:
        session = esolar_web_autenticate(region, username, password)
        plant_info = None
        if (WEB_PLANT_DATA is not None
                and username in WEB_PLANT_DATA
                and WEB_PLANT_DATA[username] is not None
                and "plant_list" in WEB_PLANT_DATA[username]
                and "plant_info" in WEB_PLANT_DATA[username]
                and WEB_PLANT_DATA[username]["plant_list"] == plant_list
                and WEB_PLANT_DATA[username]["plant_info"] is not None):
            plant_info = WEB_PLANT_DATA[username]["plant_info"]

        if plant_info is None :
            _LOGGER.debug(
                f"We don't have all plant_info, requesting"
            )
            plant_info = web_get_plant(region, session, plant_list)
            #web_get_ems_list(region, session, plant_info)
            WEB_PLANT_DATA = {username: {'plant_list': plant_list, 'plant_info': plant_info}}
        else:
            _LOGGER.debug(
                f"We have plant data for {username}/{plant_list}, using cached data"
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
                    if (("hasBattery" in device and device["hasBattery"] == 1) or
                            ("batEnergyPercent" in device["deviceStatisticsData"] and float(device["deviceStatisticsData"]["batEnergyPercent"]) > 0) or
                            ("batEnergyPercent" in device and int(device["batEnergyPercent"]) > 0)):
                        device["hasBattery"] = 1
                        plant["hasBattery"] = 1
                        break
            except Exception as e:
                _LOGGER.error(
                    f"We don't have a battery for {username}: {e}"
                )
        web_get_batteries_data(region, session, plant_info)
        web_get_device_battery_data(region, session, plant_info)

        plant_info['status'] = 'success'
        plant_info['stamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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


def esolar_web_autenticate(region, username, password):
    """Authenticate the user to the SAJ's WEB Portal."""
    if BASIC_TEST:
        return True

    try:
        session = requests.Session()

        # I try to authenticate as rarely as possible because if there are too many logins, a captcha challenge might appear.
        stored_data = read_user_data(username, password)
        if "error" not in stored_data and "token" in stored_data and "expires" in stored_data:
            authorization_token = stored_data["token"]
            authorization_expires = int(stored_data["expires"])
            dt = datetime.datetime.fromtimestamp(authorization_expires).strftime("%Y-%m-%d %H:%M:%S")
            _LOGGER.debug(
                f"Using disk cached token, expires at {dt}"
            )
            session.headers.update({'Authorization': authorization_token})
            return session

        _LOGGER.debug(
            f"We don't have a valid token, authenticating..."
        )

        data_to_sign = {
            "appProjectName": "elekeeper",
            "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
            "lang": "en",
            "timeStamp": int(time.time()*1000),
            "random": generatkey(32),
            "clientId": "esolar-monitor-admin"
        }

        login_data = dict({
            "username": username,
            "password": encrypt(password),
            "rememberMe": "false",
            "loginType": 1,
        })
        signed = calc_signature(data_to_sign)
        data = signed | login_data
        response = (
            session.post(
                base_url(region) + "/sys/login",
                data = data,
                timeout=WEB_TIMEOUT,
            )
        )

        response.raise_for_status()

        if response.status_code != 200:
            raise ValueError(f"Login failed, returned {response.status_code}")

        answer = json.loads(response.text)

        if "errCode" in answer and answer["errCode"] != 0:
            if answer["errCode"] == 10004:
                _LOGGER.error(f"Authorization failed, because {answer['errMsg']}")
                store_user_data(username, password, None, None) #force reauth
                return esolar_web_autenticate(region, username, password)

            _LOGGER.error(f"Login failed, returned {answer['errMsg']}")
            raise ValueError('Error message in answer: ' + answer['errMsg'])
        else:
            if "data" in answer and "token" in answer['data'] and 'expiresIn' in answer['data']:
                expires_in = int(answer['data']['expiresIn']) #sec, nem ms
                expires_at = int(time.time() + expires_in)-9 #3nap-10s
                authorization_expires = expires_at
                authorization_token =  answer['data']['tokenHead'] + answer['data']['token']
                store_user_data(username, password, authorization_token, authorization_expires)
                session.headers.update({'Authorization': authorization_token})
                _LOGGER.debug(
                    f"Using new token, expires in {int(expires_at - time.time())} seconds",
                )
                return session
            else:
                _LOGGER.error(f"Login failed, returned {answer}")
                raise ValueError('Token not found in answer: ' + response.text)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

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
        "expires_hrs": datetime.datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M:%S"),
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

    # Expiry ellenőrzése: Csak akkor adjuk vissza a tokent, ha még nem járt le
    current_time = int(time.time())
    if expires > current_time:
        return {"token": token, "expires": expires}

    if refresh_token is not None:
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

        if requested_plant_list is not None:
            for plant in plant_list["data"]['list']:
                if plant["plantName"] in requested_plant_list:
                    output_plant_list.append(plant)
            return {"plantList": output_plant_list}

        return {"plantList": plant_list["data"]['list']}

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
            plant.update(plant_detail["data"])

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
            if 'data' in plant_statistics and 'deviceSnList' in plant_statistics['data']:
                del plant_statistics['data']['deviceSnList']
            if 'data' in plant_statistics and 'moduleSnList' in plant_statistics['data']:
                del plant_statistics['data']['moduleSnList']
            plant.update(plant_statistics["data"])

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
            if 'data' in answer and 'list' in answer['data']:
                device_list = answer["data"]["list"]
            else:
                return

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
                device.update(device_detail["data"])

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
                if 'data' in raw and 'list' in raw['data'] and len(raw['data']['list']) > 0:
                    raw_data = raw["data"]["list"][0]
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
            if 'data' in overview:
                plant.update(overview["data"])
            else:
                _LOGGER.warning(
                    "Nincs data az overview-ban!?",
                )

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
            if 'data' in flow:
                plant.update(flow["data"])
            else:
                _LOGGER.warning(
                    "Nincs data a flow-ban!? {flow}",
                )

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
                if 'data' in answer and answer["data"] is not None and len(answer["data"]) > 0:
                    for module in answer["data"]:
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
                        if 'data' in answer and answer["data"] is not None:
                            if "modules" not in plant:
                                plant["modules"] = []
                            found = False
                            for plant_module in plant["modules"]:
                                if "moduleSn" in plant_module and plant_module["moduleSn"] is not None and \
                                        plant_module["moduleSn"] == moduleSn:
                                    plant_module.update(answer["data"])
                                    found = True
                            if not found:
                                plant["modules"].append(answer["data"])


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
            if 'data' in answer and answer["data"] is not None and "list" in answer["data"]:
                plant["batteries"] = answer["data"]["list"]

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
                if 'data' in answer:
                    del answer["data"]["baseBatteryBtnBeanList"]
                    if "batteries" in plant and plant["batteries"] is not None:
                        for battery in plant["batteries"]:
                            if battery["batSn"] == device["deviceSn"]:
                                battery.update(answer["data"])
                    else:
                        device.update(answer["data"])

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
            if 'data' in answer and 'list' in answer['data']:
                ems_list = answer["data"]["list"]
            else:
                return

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
            if 'data' in answer and 'list' in answer['data'] and len(answer['data']['list']) > 0:
                alarm_list = answer["data"]["list"]
                for alarm in alarm_list:
                    if "alarmStartTime" in alarm and alarm["alarmStartTime"] is not None and is_today(alarm["alarmStartTime"]):
                        plant["todayAlarmNum"] = plant["todayAlarmNum"] + 1
                        for device in plant["devices"]:
                            if device["deviceSn"] == alarm["deviceSn"]:
                                device["todayAlarmNum"] = device["todayAlarmNum"] + 1
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