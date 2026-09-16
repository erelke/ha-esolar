"""Dump processed plant_info and extra SAJ endpoints for shared test accounts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/mnt/e/ha-esolar/custom_components")

from saj_esolar_air.esolar import (  # noqa: E402
    _post_v2,
    base_url,
    calc_signature,
    esolar_web_authenticate,
    generatkey,
    get_esolar_data,
)
import datetime
import time

OUT = Path("/mnt/e/ha-esolar/basic_test/dumps")
OUT.mkdir(parents=True, exist_ok=True)
ENTRIES = "/home/homeassistant/.homeassistant/.storage/core.config_entries"


def load_entries():
    with open(ENTRIES, encoding="utf-8") as f:
        data = json.load(f)
    return [
        e
        for e in data["data"]["entries"]
        if e.get("domain") == "saj_esolar_air"
    ]


def summarize_node(node, depth=0):
    if not isinstance(node, dict):
        return {"type": type(node).__name__}
    kids = node.get("children") or []
    return {
        "sn": node.get("deviceSn") or node.get("sn") or node.get("moduleSn") or node.get("batSn"),
        "deviceType": node.get("deviceType"),
        "type": node.get("type"),
        "model": node.get("deviceModel") or node.get("batModel") or node.get("moduleModel"),
        "name": node.get("deviceName") or node.get("moduleName") or node.get("batteryName"),
        "hasBattery": node.get("hasBattery"),
        "children": [summarize_node(c, depth + 1) for c in kids if isinstance(c, dict)],
    }


def try_json(resp):
    try:
        return resp.json()
    except Exception as err:
        return {"error": str(err), "status": getattr(resp, "status_code", None)}


def probe_endpoints(region, session, plant):
    plant_uid = plant["plantUid"]
    results = {}

    resp = _post_v2(
        session,
        region,
        "/monitor/plantDevice/listForWeb",
        {"plantUid": plant_uid},
    )
    results["listForWeb"] = try_json(resp)

    signed = calc_signature(
        {
            "plantUid": plant_uid,
            "pageSize": 100,
            "pageNo": 1,
            "searchOfficeIdArr": "1",
            "appProjectName": "elekeeper",
            "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
            "lang": "en",
            "timeStamp": int(time.time() * 1000),
            "random": generatkey(32),
            "clientId": "esolar-monitor-admin",
        }
    )
    resp = session.get(
        base_url(region) + "/monitor/battery/getBatteryList",
        params=signed,
        timeout=30,
    )
    results["v1_getBatteryList"] = try_json(resp)

    for path in (
        "/monitor/battery/getBatteryList",
        "/monitor/device/getBatteryList",
        "/monitor/home/getBatteryList",
        "/monitor/plant/getBatteryList",
    ):
        resp = _post_v2(
            session,
            region,
            path,
            {
                "plantUid": plant_uid,
                "pageSize": 100,
                "pageNo": 1,
            },
        )
        results[f"v2_{path.split('/')[-1]}"] = {
            "path": path,
            "status": resp.status_code,
            "body": try_json(resp),
        }

    signed = calc_signature(
        {
            "plantUid": plant_uid,
            "appProjectName": "elekeeper",
            "clientDate": datetime.date.today().strftime("%Y-%m-%d"),
            "lang": "en",
            "timeStamp": int(time.time() * 1000),
            "random": generatkey(32),
            "clientId": "esolar-monitor-admin",
        }
    )
    resp = session.get(
        base_url(region) + "/monitor/sec/plantSECModuleList",
        params=signed,
        timeout=30,
    )
    results["v1_plantSECModuleList"] = try_json(resp)

    resp = _post_v2(
        session,
        region,
        "/monitor/sec/plantSECModuleList",
        {"plantUid": plant_uid},
    )
    results["v2_plantSECModuleList"] = {"status": resp.status_code, "body": try_json(resp)}

    return results


def slim_processed(plant_info):
    slim = []
    for plant in plant_info.get("plantList") or []:
        slim.append(
            {
                "plantName": plant.get("plantName"),
                "type": plant.get("type"),
                "hasBattery": plant.get("hasBattery"),
                "isInstallMeter": plant.get("isInstallMeter"),
                "deviceSnList": plant.get("deviceSnList"),
                "moduleSnList": plant.get("moduleSnList"),
                "devices": [
                    {
                        "deviceSn": d.get("deviceSn"),
                        "deviceType": d.get("deviceType"),
                        "type": d.get("type"),
                        "deviceModel": d.get("deviceModel"),
                        "deviceName": d.get("deviceName"),
                        "hasBattery": d.get("hasBattery"),
                        "stats_keys": sorted((d.get("deviceStatisticsData") or {}).keys()),
                        "child_sns": [
                            (c.get("deviceSn") or c.get("sn"))
                            for c in (d.get("children") or [])
                            if isinstance(c, dict)
                        ],
                    }
                    for d in plant.get("devices") or []
                ],
                "modules": [
                    {
                        "moduleSn": m.get("moduleSn"),
                        "moduleName": m.get("moduleName") or m.get("deviceName"),
                        "deviceModel": m.get("deviceModel") or m.get("moduleModel"),
                        "keys": sorted(m.keys()),
                    }
                    for m in plant.get("modules") or []
                ],
                "batteries": [
                    {
                        "batSn": b.get("batSn"),
                        "bmsSn": b.get("bmsSn"),
                        "batModel": b.get("batModel") or b.get("batteryName"),
                        "batSoc": b.get("batSoc") or b.get("batEnergyPercent"),
                        "keys": sorted(b.keys()),
                    }
                    for b in plant.get("batteries") or []
                ],
            }
        )
    return slim


def main():
    for entry in load_entries():
        cfg = entry["data"]
        sites = (entry.get("options") or {}).get("monitored_sites") or []
        label = "_".join(sites) or entry.get("title") or "unknown"
        print("===", label, "===")
        plant_info = get_esolar_data(
            cfg.get("region", "eu"),
            cfg["username"],
            cfg["password"],
            sites,
            True,
        )
        slim = slim_processed(plant_info)
        (OUT / f"{label}_processed.json").write_text(
            json.dumps(slim, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(json.dumps(slim, indent=2, ensure_ascii=False)[:4000])

        session = esolar_web_authenticate(
            cfg.get("region", "eu"), cfg["username"], cfg["password"]
        )
        extra = {}
        for plant in plant_info.get("plantList") or []:
            extra[plant.get("plantName")] = probe_endpoints(
                cfg.get("region", "eu"), session, plant
            )
            tree = extra[plant.get("plantName")]["listForWeb"]
            data = tree.get("data") if isinstance(tree, dict) else tree
            if isinstance(data, dict):
                data = data.get("list") or data.get("records") or data.get("devices") or data
            if isinstance(data, list):
                extra[plant.get("plantName")]["listForWeb_tree"] = [
                    summarize_node(n) for n in data if isinstance(n, dict)
                ]
        (OUT / f"{label}_endpoints.json").write_text(
            json.dumps(extra, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
