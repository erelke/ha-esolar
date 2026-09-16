import json
from pathlib import Path

DUMP = Path("/mnt/e/ha-esolar/basic_test/dumps")


def walk(nodes, acc):
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        acc.append(n)
        walk(n.get("children") or [], acc)


for path in sorted(DUMP.glob("*_endpoints.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    for plant, extra in data.items():
        body = extra.get("listForWeb") or {}
        payload = body.get("data") if isinstance(body, dict) else body
        if isinstance(payload, dict):
            payload = payload.get("list") or payload.get("records") or payload.get("devices") or []
        nodes = []
        walk(payload if isinstance(payload, list) else [], nodes)
        print("=" * 80, plant)
        for n in nodes:
            dtype = n.get("deviceType")
            if dtype in (2, 3, 4) or "meter" in str(n.get("deviceName") or "").lower() or "module" in str(n.get("deviceName") or "").lower():
                skip = {"children"}
                keys = {k: n[k] for k in n if k not in skip}
                print(json.dumps({
                    "sn": n.get("deviceSn") or n.get("sn"),
                    "type": dtype,
                    "name": n.get("deviceName"),
                    "model": n.get("deviceModel"),
                    "fields": {k: v for k, v in keys.items() if v not in (None, "", [], {})},
                }, ensure_ascii=False, indent=2)[:4000])
                print()
