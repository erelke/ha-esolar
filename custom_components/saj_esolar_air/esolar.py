"""ESolar Cloud Platform data fetchers."""
import calendar
import datetime
import time
import logging
import random
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
import hashlib
import binascii
import json
import requests
import urllib.parse

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://eop.saj-electric.com/dev-api/api/v1"
WEB_TIMEOUT = 30

BASIC_TEST = False
VERBOSE_DEBUG = False
if BASIC_TEST:
    from .esolar_static_test import (
        get_esolar_data_static_h1_r5,
        web_get_plant_static_h1_r5,
    )


def add_months(sourcedate, months):
    """SAJ eSolar Helper Function - Adds a months to input."""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def add_years(source_date, years):
    """SAJ eSolar Helper Function - Adds a years to input."""
    try:
        return source_date.replace(year=source_date.year + years)
    except ValueError:
        return source_date + (
            datetime.date(source_date.year + years, 1, 1)
            - datetime.date(source_date.year, 1, 1)
        )


def get_esolar_data(username, password, plant_list=None, use_pv_grid_attributes=True):
    """SAJ eSolar Data Update."""
    if BASIC_TEST:
        return get_esolar_data_static_h1_r5(
            username, password, plant_list, use_pv_grid_attributes
        )

    try:
        plant_info = None
        session = esolar_web_autenticate(username, password)
        plant_info = web_get_plant(session, plant_list)
        web_get_plant_details(session, plant_info)
        web_get_plant_statistics(session, plant_info)
        web_get_device_info(session, plant_info)
        web_get_device_rawData(session, plant_info)

        plant_info['status'] = 'success'

        # with open('plant_info.json', 'w') as json_file:
        #     json.dump(plant_info, json_file, indent=4)


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


def sha1_hash(data):
    """SHA-1 hash kiszámítása, megfelelően konvertálva 32 bites előjeles számokká."""
    if isinstance(data, str):
        data = data.encode()  # String átalakítása byte formátumba
    elif isinstance(data, bytes):
        data = bytearray(data)  # Ha byte-ként jön, átalakítjuk megfelelően
    else:
        data = str(data).encode()  # Egyéb típusok átalakítása

    sha1 = hashlib.sha1()
    sha1.update(data)

    # SHA-1 hash 20 bájt, 5 darab 32 bites számként visszaadva
    result = [int.from_bytes(sha1.digest()[i:i + 4], "big", signed=True) for i in range(0, 20, 4)]
    return result

def extract_bytes_from_words(words):
    """32 bites számokat átalakít 8 bites byte-listává."""
    t = []
    for n in range(0, 32 * len(words), 8):
        t.append((words[n >> 5] >> (24 - n % 32)) & 255)
    return t

def bytes_to_hex_string(e):
    """Bytes lista átalakítása hexadecimális stringgé."""
    t = []
    for n in range(len(e)):
        t.append(hex(e[n] >> 4)[2:])  # Magasabb 4 bit átalakítása hexadecimálissá
        t.append(hex(e[n] & 15)[2:])  # Alacsonyabb 4 bit átalakítása hexadecimálissá
    return "".join(t)

def sign(data):
    n = sha1_hash(data)
    b = extract_bytes_from_words(n)
    h = bytes_to_hex_string(b)
    return h

def hex_string_to_signed_array(hex_str):
    """Hexadecimális karakterlánc átalakítása előjeles 32 bites számokat tartalmazó tömbbé."""
    t = len(hex_str)
    n = [0] * ((t + 7) // 8)  # Létrehozunk egy megfelelő méretű listát

    for r in range(0, t, 2):
        byte_val = int(hex_str[r:r + 2], 16)  # Hexadecimális érték konvertálása
        n[r >> 3] |= byte_val << (24 - (r % 8) * 4)  # Biteltolás

    # Az előjeles 32 bites konverzió biztosítása
    n = [(x & 0x7FFFFFFF) - (x & 0x80000000) for x in n]

    return n

def parse_string(e):
    """Szöveg karakterkódokból számtömbbé alakítása."""
    t = len(e)
    n = [0] * ((t + 3) // 4)  # Létrehozunk egy megfelelő méretű listát

    for r in range(t):
        char_code = ord(e[r]) & 255  # Unicode karakterek alsó 8 bitjének kinyerése
        n[r >> 2] |= char_code << (24 - (r % 4) * 8)

    return n, t  # Hasonló visszatérési érték, mint az eredeti JS függvény

def process_text(e):
    """Szöveg kódolása és feldolgozása."""
    encoded = urllib.parse.quote(e)  # JavaScript encodeURIComponent megfelelője
    decoded = urllib.parse.unquote(encoded)  # JavaScript unescape megfelelője
    return parse_string(decoded)  # Az előző parse_string függvény meghívása

def dict_to_sorted_string(data):
    """Szótár elemeit átalakítja abc sorrendbe, majd kulcs=érték formátumban összefűzi."""
    sorted_items = sorted(data.items())  # Kulcsok alapján rendezés
    result_string = "&".join(f"{k}={v}" for k, v in sorted_items)  # Összefűzés
    return result_string

def calc_signature(dict):
    keys = dict.keys()
    keys_str = ','.join(keys)
    string = dict_to_sorted_string(dict)+"&key=ktoKRLgQPjvNyUZO8lVc9kU1Bsip6XIe" #esolar app.js
    h = hashlib.md5(string.encode('latin-1')).hexdigest()
    signature = sign(h).upper()

    dict['signature'] = signature
    dict['signParams'] = keys_str
    return dict

def pad_pkcs7(data, block_size=16):
    """PKCS7 padding hozzáadása, hogy kompatibilis legyen a JavaScript verzióval."""
    padding_len = block_size - (len(data) % block_size)
    return data + bytes([padding_len] * padding_len)

def aes_ecb_encrypt(plaintext, key_hex):
    """AES-ECB titkosítás hexadecimális kulccsal, PKCS7 padding-et alkalmazva."""
    key = binascii.unhexlify(key_hex)  # Hex kulcs átalakítása byte formátumba
    cipher = AES.new(key, AES.MODE_ECB)  # AES-ECB titkosító inicializálása
    padded_plaintext = pad_pkcs7(plaintext.encode())  # PKCS7 padding hozzáadása
    encrypted_bytes = cipher.encrypt(padded_plaintext)  # Titkosítás
    return binascii.hexlify(encrypted_bytes).decode()  # Hexadecimális eredmény

def encrypt(plaintext):
    key_hex = 'ec1840a7c53cf0709eb784be480379b6' #esolar app.js
    return aes_ecb_encrypt(plaintext, key_hex)

def generatkey(length):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return ''.join(random.choice(chars) for _ in range(length))

def esolar_web_autenticate(username, password):
    """Authenticate the user to the SAJ's WEB Portal."""
    if BASIC_TEST:
        return True

    try:
        session = requests.Session()
        random = generatkey(32)

        sign = {
            "appProjectName": "elekeeper",
            "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
            "lang": "en",
            "timeStamp": int(time.time()*1000),
            "random": random,
            "clientId": "esolar-monitor-admin"
        }

        login_data = dict({
            "username": username,
            "password": encrypt(password),
            "rememberMe": "false",
            "loginType": 1,
        })
        signed = calc_signature(sign)
        data = signed | login_data
        response = (
            session.post(
                BASE_URL + "/sys/login",
                data = data,
                timeout=WEB_TIMEOUT,
            )
        )

        response.raise_for_status()

        if response.status_code != 200:
            raise ValueError(f"Login failed, returned {response.status_code}")

        answer = json.loads(response.text)

        if "errCode" in answer and answer["errCode"] != 0:
            _LOGGER.error(f"Login failed, returned {answer['errMsg']}")
            raise ValueError('Error message in answer: ' + answer['errMsg'])
        else:
            if "data" in answer and "token" in answer['data']:
                session.headers.update({'Authorization': answer['data']['tokenHead'] + answer['data']['token']})
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


def web_get_plant(session, requested_plant_list=None):
    """Retrieve the platUid from WEB Portal using web_authenticate."""
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
            BASE_URL + "/monitor/plant/getEndUserPlantList",
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


def web_get_plant_details(session, plant_info):
    """Retrieve platUid from the WEB Portal using web_authenticate."""
    if session is None:
        raise ValueError("Missing session identifier trying to obain plants")

    try:
        device_list = []
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
                BASE_URL + "/monitor/plant/getOnePlantInfo", #/monitor/site/getPlantDetailInfo
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get plant detail error: {response.status_code}")

            plant_detail = response.json()
            plant.update(plant_detail["data"])
            for device in plant_detail["data"]["deviceSnList"]:
                device_list.append(device)

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)

def web_get_plant_statistics(session, plant_info):
    """Retrieve platUid from the WEB Portal using web_authenticate."""
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
                BASE_URL + "/monitor/home/getPlantStatisticsData",
                params = signed,
                timeout=WEB_TIMEOUT
            )

            response.raise_for_status()

            if response.status_code != 200:
                raise ValueError(f"Get plant statistics data error: {response.status_code}")

            plant_statistics = response.json()
            plant.update(plant_statistics["data"])

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)


def web_get_device_info(session, plant_info):
    """Retrieve platUid from the WEB Portal using web_authenticate."""
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
                    BASE_URL + "/monitor/device/getOneDeviceInfo",
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


def web_get_device_rawData(session, plant_info):
    """Retrieve platUid from the WEB Portal using web_authenticate."""
    if session is None:
        raise ValueError("Missing session identifier trying to obain plants")

    try:
        for plant in plant_info["plantList"]:
            for device in plant["devices"]:
                data = {
                    'appProjectName': 'elekeeper',
                    'clientDate': datetime.date.today().strftime("%Y-%m-%d"),
                    'lang': 'en',
                    'timeStamp': int(time.time() * 1000),
                    'random': generatkey(32),
                    'clientId': 'esolar-monitor-admin',
                }

                payload = {
                    "deviceSn": device["deviceSn"],
                    "pageSize": 1,
                    "pageNo": 1,
                    "deviceType": 0,
                    'timeStr': datetime.date.today().strftime("%Y-%m-%d 00:00:00"),
                    "startTime": datetime.date.today().strftime("%Y-%m-%d 00:00:00"),
                    "endTime": datetime.date.today().strftime("%Y-%m-%d 23:59:59"),
                }

                signed = calc_signature(data)

                response = session.post(
                    BASE_URL + "/monitor/deviceData/findRawdataPageList",
                    data = payload | signed,
                    timeout=WEB_TIMEOUT
                )

                response.raise_for_status()

                if response.status_code != 200:
                    raise ValueError(f"Get device {device['deviceSn']} raw data error: {response.status_code}")

                raw = response.json()
                device.update({"raw": raw["data"]["list"][0]})

    except requests.exceptions.HTTPError as errh:
        raise requests.exceptions.HTTPError(errh)
    except requests.exceptions.ConnectionError as errc:
        raise requests.exceptions.ConnectionError(errc)
    except requests.exceptions.Timeout as errt:
        raise requests.exceptions.Timeout(errt)
    except requests.exceptions.RequestException as errr:
        raise requests.exceptions.RequestException(errr)
