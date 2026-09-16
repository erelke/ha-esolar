import json
import sys

sys.path.insert(0, "/mnt/e/ha-esolar/custom_components")
from saj_esolar_air.esolar import _post_v2, esolar_web_autenticate

ENTRIES = "/home/homeassistant/.homeassistant/.storage/core.config_entries"
for entry in json.load(open(ENTRIES, encoding="utf-8"))["data"]["entries"]:
    if entry.get("domain") == "saj_esolar_air" and (entry.get("options") or {}).get(
        "monitored_sites"
    ) == ["Martin Dures"]:
        cfg = entry["data"]
        break

session = esolar_web_autenticate(cfg.get("region", "eu"), cfg["username"], cfg["password"])
for sn in ("M5380J2335032716", "M5380J2413057820"):
    data = _post_v2(
        session, "eu", "/monitor/module/baseModuleDetail", {"moduleSn": sn}
    ).json()["data"]
    print("=" * 80, sn)
    print(
        json.dumps(
            {
                k: data.get(k)
                for k in (
                    "moduleSn",
                    "moduleModel",
                    "aliasName",
                    "signalStrength",
                    "signalStrengthValue",
                    "moduleStatus",
                    "moduleStatusName",
                    "softwareVersion",
                    "hardwareVersion",
                    "updateDate",
                    "modulePc",
                    "deviceSn",
                )
            },
            ensure_ascii=False,
            indent=2,
        )
    )
