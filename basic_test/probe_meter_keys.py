import json
import sys

sys.path.insert(0, "/mnt/e/ha-esolar/custom_components")
from saj_esolar_air.esolar import _post_v2, esolar_web_authenticate

ENTRIES = "/home/homeassistant/.homeassistant/.storage/core.config_entries"
h2 = "H2S2602J2417E01068"
aio = "M5380J2335032716"
wifi = "M5380J2413057820"

for entry in json.load(open(ENTRIES, encoding="utf-8"))["data"]["entries"]:
    if entry.get("domain") == "saj_esolar_air" and (entry.get("options") or {}).get(
        "monitored_sites"
    ) == ["Martin Dures"]:
        cfg = entry["data"]
        break
else:
    raise SystemExit("martin not found")

region = cfg.get("region", "eu")
session = esolar_web_authenticate(region, cfg["username"], cfg["password"])

paths = [
    ("/monitor/module/baseModuleDetail", {"moduleSn": aio}),
    ("/monitor/module/baseModuleDetail", {"moduleSn": wifi}),
    ("/monitor/deviceData/getElectricMeterDetail", {"deviceSn": h2}),
    ("/monitor/deviceData/getElectricMeterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/deviceData/getMeterRealtimeData", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/plantDevice/getMeterRealtimeData", {"deviceSn": h2}),
    ("/monitor/meter/getMeterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/meter/getElectricMeterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/plant/getMeterData", {"deviceSn": h2}),
    ("/monitor/device/getMeterInfo", {"deviceSn": h2}),
    (
        "/monitor/deviceData/findMeterRawdataPageList",
        {"deviceSn": h2, "pageNo": 1, "pageSize": 1},
    ),
    ("/monitor/home/getMeterInfo", {"deviceSn": h2}),
    ("/monitor/module/getModuleRealtimeData", {"moduleSn": aio}),
    ("/monitor/plantDevice/deviceDetail", {"deviceSn": h2}),
    ("/monitor/plantDevice/meterDetail", {"deviceSn": h2, "meterType": 5}),
    ("/monitor/plantDevice/getDeviceMeterList", {"deviceSn": h2}),
    ("/monitor/plantHome/getDeviceEnergyFlowDiagram", {"sn": h2, "snType": 1}),
    ("/monitor/deviceData/getDeviceRealtimeData", {"deviceSn": h2}),
    ("/monitor/inverter/getInverterMeterData", {"deviceSn": h2}),
    ("/monitor/device/electricMeter/detail", {"deviceSn": h2, "meterType": 5}),
]


def summarize(data):
    if isinstance(data, dict):
        nonempty = {
            key: val
            for key, val in data.items()
            if val not in (None, "", "--", [], {}, 0)
            and not str(key).endswith("Str")
        }
        return list(data.keys())[:25], {k: nonempty[k] for k in list(nonempty)[:18]}
    if isinstance(data, list):
        return f"list[{len(data)}]", data[:1]
    return type(data).__name__, data


for path, payload in paths:
    try:
        resp = _post_v2(session, region, path, payload)
        body = resp.json()
    except Exception as err:
        print(f"\nPOST {path} EXC {err}")
        continue
    err = body.get("errCode") if isinstance(body, dict) else None
    msg = body.get("errMsg") if isinstance(body, dict) else ""
    data = body.get("data") if isinstance(body, dict) else None
    keys, nonempty = summarize(data)
    print(f"\nPOST {path} {payload} err={err} {msg}")
    print(" keys", keys)
    print(" nonempty", json.dumps(nonempty, ensure_ascii=False, default=str)[:800])
