import json
import sys

sys.path.insert(0, "/mnt/e/ha-esolar/custom_components")
from saj_esolar_air.esolar import get_esolar_data

p = "/home/homeassistant/.homeassistant/.storage/core.config_entries"
for e in json.load(open(p))["data"]["entries"]:
    if e.get("domain") != "saj_esolar_air":
        continue
    if (e.get("options") or {}).get("monitored_sites") != ["Martin Dures"]:
        continue
    cfg = e["data"]
    info = get_esolar_data(cfg.get("region", "eu"), cfg["username"], cfg["password"], ["Martin Dures"], True)
    for plant in info["plantList"]:
        for d in plant.get("devices") or []:
            if d.get("deviceSn") == "H2S2602J2417E01068":
                meter = {k: d[k] for k in d if "meter" in k.lower()}
                print("H2 meter keys on device", json.dumps(meter, ensure_ascii=False, indent=2)[:4000])
        print("modules keys:")
        for m in plant.get("modules") or []:
            print(m.get("moduleKey"), sorted(m.keys()))
            live = {
                k: m.get(k)
                for k in (
                    "gridPower",
                    "volt1",
                    "curr1",
                    "power1",
                    "freq1",
                    "impEp",
                    "expEp",
                    "todayImpEp",
                    "todayExpEp",
                    "updateDate",
                )
                if m.get(k) is not None
            }
            if live:
                print(" ", live)
