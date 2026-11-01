#!/usr/bin/env python3
"""Phase 3: enrich primary IPs with country/ISP/org/AS/PTR via ip-api.com."""

import ipaddress
import json
import os
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "tools", "work")
FIELDS = "status,message,country,countryCode,isp,org,as,reverse,query"
URL = f"http://ip-api.com/batch?fields={FIELDS}"
BATCH = 100
PAUSE = 1.7


def is_public(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


def post(batch):
    body = json.dumps([{"query": ip} for ip in batch]).encode()
    req = urllib.request.Request(URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    dns = json.load(open(os.path.join(WORK, "dns.json"), encoding="utf-8"))
    primary = {}
    for d, v in dns.items():
        ip = (v["a"] or v["aaaa"] or [None])[0]
        if ip and is_public(ip):
            primary[d] = ip

    ips = sorted(set(primary.values()))
    print(f"domains with public IP: {len(primary)}, unique IPs: {len(ips)}")

    geo = {}
    for i in range(0, len(ips), BATCH):
        chunk = ips[i:i + BATCH]
        for attempt in range(4):
            try:
                res = post(chunk)
                break
            except urllib.error.HTTPError as e:
                wait = 5 * (attempt + 1)
                print(f"  HTTP {e.code}, retry in {wait}s", flush=True)
                time.sleep(wait)
            except Exception as exc:  # noqa: BLE001
                print(f"  batch error {exc}, retry", flush=True)
                time.sleep(4)
        else:
            print(f"  batch {i} failed permanently", flush=True)
            continue
        for item in res:
            geo[item["query"]] = item
        print(f"  geo {min(i + BATCH, len(ips))}/{len(ips)}", flush=True)
        time.sleep(PAUSE)

    ok = sum(1 for v in geo.values() if v.get("status") == "success")
    json.dump(geo, open(os.path.join(WORK, "geo.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    print(f"geo ok: {ok}/{len(geo)}")


if __name__ == "__main__":
    main()
