"""  Special Methods and function used for Elekeeper communication """
import calendar
import datetime
import hashlib
import binascii
from Crypto.Cipher import AES
import urllib.parse
import random
import re
import time
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo

### 1. Signing query params

QUERY_SIGN_KEY = "ktoKRLgQPjvNyUZO8lVc9kU1Bsip6XIe" #extracted from elekeeper app.js

def calc_signature(_dict):
    """ Sign a web request query params (data) """
    keys = _dict.keys()
    keys_str = ','.join(keys)
    string = dict_to_sorted_string(_dict)+"&key="+QUERY_SIGN_KEY
    h = hashlib.md5(string.encode('latin-1')).hexdigest()
    signature = sign(h).upper()

    _dict['signature'] = signature
    _dict['signParams'] = keys_str
    return _dict

def dict_to_sorted_string(data):
    """Szótár elemeit átalakítja abc sorrendbe, majd kulcs=érték formátumban összefűzi."""
    sorted_items = sorted(data.items())  # Kulcsok alapján rendezés
    result_string = "&".join(f"{k}={v}" for k, v in sorted_items)  # Összefűzés
    return result_string

def sign(data):
    """ calculate signature """
    n = sha1_hash(data)
    b = extract_bytes_from_words(n)
    h = bytes_to_hex_string(b)
    return h

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

### 2. Encrypt password

PASSWORD_ENCRYPTION_KEY = "ec1840a7c53cf0709eb784be480379b6"  #extracted from elekeeper app.js

def encrypt(plaintext):
    return aes_ecb_encrypt(plaintext, PASSWORD_ENCRYPTION_KEY)

def aes_ecb_encrypt(plaintext, key_hex):
    """AES-ECB titkosítás hexadecimális kulccsal, PKCS7 padding-et alkalmazva."""
    key = binascii.unhexlify(key_hex)  # Hex kulcs átalakítása byte formátumba
    cipher = AES.new(key, AES.MODE_ECB)  # AES-ECB titkosító inicializálása
    padded_plaintext = pad_pkcs7(plaintext.encode())  # PKCS7 padding hozzáadása
    encrypted_bytes = cipher.encrypt(padded_plaintext)  # Titkosítás
    return binascii.hexlify(encrypted_bytes).decode()  # Hexadecimális eredmény

def pad_pkcs7(data, block_size=16):
    """PKCS7 padding hozzáadása, hogy kompatibilis legyen a JavaScript verzióval."""
    padding_len = block_size - (len(data) % block_size)
    return data + bytes([padding_len] * padding_len)

### 3. generate a random key (as salt) in a query (used for signing a query)

def generatkey(length):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return ''.join(random.choice(chars) for _ in range(length))

### 4. methods used for data extraction

def extract_number(string):
    match = re.findall(r'\d+', string)  # Minden számjegyet megtalál
    return int(match[0]) if match else None  # Visszaadja az első számot

def split_camel_case(s):
    # Ha az első karakter kisbetű, akkor hozzáadjuk külön
    s = s[0].upper() + s[1:] if s else s
    words = re.findall(r'[A-Z][a-z]*|[a-z]+', s)  # Felbontás kis- és nagybetűkre
    return ' '.join(word.capitalize() for word in words)

def extract_date(date_str, timezone = None):
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        if timezone:
            if isinstance(timezone, str):  # Ha stringként adod meg az időzónát
                timezone = ZoneInfo(timezone)
            date_obj = date_obj.replace(tzinfo=timezone)
        else:
            date_obj = datetime.strptime(date_str + " " + time.strftime('%z'), "%Y-%m-%d %H:%M:%S %z")
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
        return None

def is_today(date_string, date_format="%Y-%m-%d %H:%M:%S"):
    try:
        date_obj = datetime.strptime(date_string, date_format).date()
        return date_obj == datetime.today().date()
    except ValueError:
        return False

def set_energy_flow_type(plant):
    if plant.get("ifCMPDevice") == 1 and plant.get("ifInstallPv") == 1:
        plant["flowType"] = "CMP"
        return True
    elif plant.get("ifCHDevice") == 1 and plant.get("ifC6Device") == 1 and plant.get("isInstallEms") == 1:
        plant["flowType"] = "C6"
        return True
    elif plant.get("ifCHDevice") == 1:
        plant["flowType"] = "CH2"
        return True
    elif plant.get("hasH2Device") == 1:
        plant["flowType"] = "H2"
        return True
    elif plant.get("isInstallLoraMeter") == 1:
        plant["flowType"] = "Lora"
        return True

    return False

def prepare_data_for_query( plant, data ):
    """SAJ eSolar Helper Function - A data-t előfeltétellegesen előzik, és a data-t a query-be kell írni."""

    if plant.get("queryDeviceDataType", 1) == 1:
        added = False
        if len(plant["deviceSnList"]) > 1:
            for device in plant["devices"]:
                if "isMasterFlag" in device and device["isMasterFlag"] == 1:
                    data["deviceSn"] = device["deviceSn"]
                    added = True
                    break
            if not added:
                for device in plant["devices"]:
                    if device["deviceModel"].startswith("H"):
                        data["deviceSn"] = device["deviceSn"]
                        added = True
            if not added:
                data["deviceSn"] = plant['deviceSnList'][0]
        else:
            data["deviceSn"] = plant["devices"][0]["deviceSn"]

    elif plant.get("queryDeviceDataType", 1) == 2:
        if "moduleSnList" in plant and plant["moduleSnList"] is not None and len(plant["moduleSnList"]) > 0:
            # if "isInstallMeter" in plant and plant["isInstallMeter"] == 1:
            data["emsSn"] = plant["moduleSnList"][0]


### other (unused) methods

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

def process_text(e):
    """Szöveg kódolása és feldolgozása."""
    encoded = urllib.parse.quote(e)  # JavaScript encodeURIComponent megfelelője
    decoded = urllib.parse.unquote(encoded)  # JavaScript unescape megfelelője
    return parse_string(decoded)  # Az előző parse_string függvény meghívása

def parse_string(e):
    """Szöveg karakterkódokból számtömbbé alakítása."""
    t = len(e)
    n = [0] * ((t + 3) // 4)  # Létrehozunk egy megfelelő méretű listát

    for r in range(t):
        char_code = ord(e[r]) & 255  # Unicode karakterek alsó 8 bitjének kinyerése
        n[r >> 2] |= char_code << (24 - (r % 4) * 8)

    return n, t  # Hasonló visszatérési érték, mint az eredeti JS függvény
