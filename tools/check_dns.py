#!/usr/bin/env python3
"""Phase 2: resolve A/AAAA and XMPP SRV records for every domain."""

import asyncio
import json
import os
import sys

import dns.asyncresolver
import dns.exception
import dns.resolver

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "tools", "work")
CONCURRENCY = 250

res = None
sem = None


def err_name(exc):
    if isinstance(exc, dns.resolver.NXDOMAIN):
        return "nxdomain"
    if isinstance(exc, dns.resolver.NoAnswer):
        return "noanswer"
    if isinstance(exc, dns.resolver.NoNameservers):
        return "servfail"
    if isinstance(exc, dns.exception.Timeout):
        return "timeout"
    return type(exc).__name__


async def query(name, rtype, attempts=3):
    last = None
    for attempt in range(attempts):
        async with sem:
            try:
                ans = await res.resolve(name, rtype, raise_on_no_answer=False)
            except Exception as exc:  # noqa: BLE001
                last = err_name(exc)
                if last in ("timeout", "servfail") and attempt + 1 < attempts:
                    await asyncio.sleep(0.6 * (attempt + 1))
                    continue
                return None, last
        if ans.rrset is None:
            return [], "noanswer"
        return ans, None
    return None, last


async def one(rec):
    d = rec["domain"]
    if rec["kind"] == "ip":
        v6 = ":" in d
        return d, {"a": [] if v6 else [d], "aaaa": [d] if v6 else [],
                   "srv_c2s": None, "srv_s2s": None, "dns_error": None}

    (a, a_err), (aaaa, aaaa_err), (sc, sc_err), (ss, ss_err) = await asyncio.gather(
        query(d, "A"), query(d, "AAAA"),
        query(f"_xmpp-client._tcp.{d}", "SRV"),
        query(f"_xmpp-server._tcp.{d}", "SRV"),
    )

    def srv(ans):
        if not ans:
            return None
        best = sorted(ans, key=lambda r: (r.priority, -r.weight))[0]
        return {"target": str(best.target).rstrip("."), "port": best.port,
                "priority": best.priority, "weight": best.weight}

    srv_ip = None
    if not (a or aaaa) and sc:
        tgt = str(sorted(sc, key=lambda r: (r.priority, -r.weight))[0].target).rstrip(".")
        if tgt and tgt != ".":
            ta, _ = await query(tgt, "A")
            if not ta:
                ta, _ = await query(tgt, "AAAA")
            if ta:
                srv_ip = ta[0].address

    out = {
        "srv_ip": srv_ip,
        "a": sorted(r.address for r in (a or [])),
        "aaaa": sorted(r.address for r in (aaaa or [])),
        "srv_c2s": srv(sc),
        "srv_s2s": srv(ss),
        "dns_error": a_err if (not a and a_err not in (None, "noanswer")) else None,
    }
    if not out["a"] and not out["aaaa"] and a_err is None and aaaa_err:
        out["dns_error"] = aaaa_err
    return d, out


async def main():
    global res, sem
    res = dns.asyncresolver.Resolver()
    res.timeout = 4.0
    res.lifetime = 6.0
    sem = asyncio.Semaphore(CONCURRENCY)
    data = json.load(open(os.path.join(WORK, "domains.json"), encoding="utf-8"))
    recs = data["domains"] + data["non_domains"]
    results = {}
    todo = len(recs)
    done = 0
    tasks = [asyncio.create_task(one(r)) for r in recs]
    for fut in asyncio.as_completed(tasks):
        d, info = await fut
        results[d] = info
        done += 1
        if done % 200 == 0 or done == todo:
            print(f"  dns {done}/{todo}", flush=True)

    alive = [d for d, v in results.items() if v["a"] or v["aaaa"]]
    srv_c2s = [d for d, v in results.items() if v["srv_c2s"]]
    srv_s2s = [d for d, v in results.items() if v["srv_s2s"]]
    errs = {}
    for v in results.values():
        e = v["dns_error"]
        if e:
            errs[e] = errs.get(e, 0) + 1

    json.dump(results, open(os.path.join(WORK, "dns.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    print(f"resolved: {len(alive)}/{len(results)}")
    print(f"srv c2s: {len(srv_c2s)}   srv s2s: {len(srv_s2s)}")
    print(f"errors: {errs}")


if __name__ == "__main__":
    asyncio.run(main())
