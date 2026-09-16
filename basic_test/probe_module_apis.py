import json
import sys

sys.path.insert(0, "/mnt/e/ha-esolar/custom_components")

from saj_esolar_air.esolar import _post_v2, esolar_web_authenticate

ENTRIES = "/home/homeassistant/.homeassistant/.storage/core.config_entries"


def load_martin():
    data = json.load(open(ENTRIES, encoding="utf-8"))
    for e in data["data"]["entries"]:
        if e.get("domain") == "saj_esolar_air" and (e.get("options") or {}).get("monitored_sites") == ["Martin Dures"]:
            return e
    raise SystemExit("martin not found")


def try_post(session, region, path, payload):
    resp = _post_v2(session, region, path, payload)
    try:
        body = resp.json()
    except Exception:
        body = {"text": resp.text[:500]}
    err = body.get("errCode") if isinstance(body, dict) else None
    keys = list(body.keys()) if isinstance(body, dict) else type(body).__name__
    data = body.get("data") if isinstance(body, dict) else None
    dkeys = list(data.keys())[:40] if isinstance(data, dict) else (type(data).__name__ if data is not None else None)
    print(f"\nPOST {path} status={resp.status_code} err={err} {body.get('errMsg') if isinstance(body, dict) else ''}")
    print(" data keys", dkeys)
    if isinstance(data, dict):
        interesting = {k: data[k] for k in data if k.lower()[:4] in ("mete", "grid", "volt", "curr", "powe", "freq", "sign", "rssi", "onli", "stat", "fw", "soft", "hard", "upda") or any(x in k.lower() for x in ("meter", "signal", "rssi", "power", "volt", "curr", "freq", "online", "status", "update", "sn"))}
        print(json.dumps(interesting, ensure_ascii=False, indent=2)[:2500])
    elif isinstance(data, list) and data:
        print(" list0 keys", list(data[0].keys())[:40] if isinstance(data[0], dict) else data[0])


entry = load_martin()
cfg = entry["data"]
session = esolar_web_authenticate(cfg.get("region", "eu"), cfg["username"], cfg["password"])
region = cfg.get("region", "eu")
h2 = "H2S2602J2417E01068"
aio = "M5380J2335032716"
wifi = "M5380J2413057820"

sec = "M5370G2219003428"
for path, payload in [
    ("/monitor/module/baseModuleDetail", {"moduleSn": aio}),
    ("/monitor/module/baseModuleDetail", {"moduleSn": wifi}),
    ("/monitor/module/baseModuleDetail", {"moduleSn": h2}),
    ("/monitor/module/getElectricMeterDetail", {"moduleSn": h2, "meterType": 5}),
    ("/monitor/module/getElectricMeterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/meter/baseMeterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/meter/baseMeterDetail", {"moduleSn": h2, "meterType": 5}),
    ("/monitor/deviceData/getElectricMeterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/plantDevice/getMeterRealtimeData", {"deviceSn": h2, "meterType": 5}),
]:
    try_post(session, region, path, payload)
