"""Inspect a local Elekeeper HAR for meter/module APIs. Chart calls skipped."""
from __future__ import annotations

import json
import sys
from urllib.parse import urlparse

PII_KEYS = {
    "password",
    "token",
    "authorization",
    "email",
    "owneremail",
    "ownername",
    "address",
    "phone",
    "latitude",
    "longitude",
    "installeremail",
    "distributoremail",
}


def load_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in PII_KEYS:
                out[key] = "***"
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def summarize(value, limit=40):
    if isinstance(value, dict):
        return {"keys": list(value.keys())[:limit], "n": len(value)}
    if isinstance(value, list):
        first = value[0] if value and isinstance(value[0], dict) else value[:1]
        return {
            "list_len": len(value),
            "item0_keys": list(first.keys()) if isinstance(first, dict) else type(first).__name__,
        }
    return type(value).__name__


har_path = sys.argv[1] if len(sys.argv) > 1 else r"d:\Letöltések\eop.saj-electric.com.2026.09.16.har"
with open(har_path, encoding="utf-8") as handle:
    har = json.load(handle)

for entry in har["log"]["entries"]:
    url = entry["request"]["url"]
    if "dev-api/api/" not in url:
        continue
    path = urlparse(url).path
    if "chart" in path.lower():
        print("SKIP CHART", path)
        continue
    req = load_json((entry["request"].get("postData") or {}).get("text") or "")
    resp = load_json((entry["response"].get("content") or {}).get("text") or "")
    print("=" * 100)
    print(entry["request"]["method"], path, "status", entry["response"]["status"])
    print("REQUEST", json.dumps(redact(req), ensure_ascii=False)[:1500] if req else None)
    if not isinstance(resp, dict):
        print("RESPONSE", type(resp).__name__)
        continue
    print("errCode", resp.get("errCode"), "errMsg", resp.get("errMsg"))
    data = resp.get("data")
    print("DATA summary", summarize(data))
    interesting = path.endswith(("getMeterDetail", "getElectricMeterDetail", "listForWeb", "listPlantDeviceType", "listSmartDeviceForWeb"))
    if interesting and data is not None:
        print(json.dumps(redact(data), ensure_ascii=False, indent=2)[:14000])
