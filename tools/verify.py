#!/usr/bin/env python3
"""Verify the generated dataset: README <-> CSV <-> txt consistency,
field validity, duplicates, flags, alliances, timestamps."""

import csv
import ipaddress
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "tools", "work")

CC_RE = re.compile(r"^[A-Z]{2}$")
AS_RE = re.compile(r"^AS\d+( .+)?$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$")
EYES = {"US": "Five Eyes 👁️", "GB": "Five Eyes 👁️", "CA": "Five Eyes 👁️",
        "AU": "Five Eyes 👁️", "NZ": "Five Eyes 👁️",
        "DK": "Nine Eyes 👁️", "FR": "Nine Eyes 👁️", "NL": "Nine Eyes 👁️",
        "NO": "Nine Eyes 👁️",
        "BE": "Fourteen Eyes 👁️", "DE": "Fourteen Eyes 👁️",
        "IT": "Fourteen Eyes 👁️", "ES": "Fourteen Eyes 👁️",
        "SE": "Fourteen Eyes 👁️"}

problems = []


def bad(kind, detail):
    problems.append(f"[{kind}] {detail}")


def flag(cc):
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc)


def main():
    # README
    md = []
    for ln in open(os.path.join(BASE, "README.md"), encoding="utf-8"):
        s = ln.strip()
        if not s.startswith("|") or s.startswith("| ---") or s.startswith("| domain"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) == 13:
            md.append(cells)
    # CSV
    rows = list(csv.DictReader(open(os.path.join(BASE, "xmpp_domains.csv"),
                                    encoding="utf-8")))
    # txt
    domains_txt = [l.strip() for l in open(os.path.join(BASE, "xmpp_domain_list.txt"),
                                           encoding="utf-8") if l.strip()]
    ip_txt = [l.rstrip("\n") for l in open(os.path.join(BASE, "xmpp_ip.txt"),
                                           encoding="utf-8") if l.strip()]

    print(f"readme rows={len(md)} csv rows={len(rows)} txt domains={len(domains_txt)} "
          f"ip rows={len(ip_txt)}")

    if len(md) != len(rows):
        bad("count", f"README {len(md)} != CSV {len(rows)}")

    md_by = {c[0]: c for c in md}
    if len(md_by) != len(md):
        bad("readme_dup", "duplicate domains in README")
    if len(set(domains_txt)) != len(domains_txt):
        bad("txt_dup", "duplicate domains in xmpp_domain_list.txt")

    csv_by = {r["domain"]: r for r in rows}
    if set(md_by) != set(csv_by):
        bad("set", f"README-only={len(set(md_by)-set(csv_by))} "
                   f"CSV-only={len(set(csv_by)-set(md_by))}")

    non_literal = {r["domain"] for r in rows if r["status"] != "ip_literal"}
    if set(domains_txt) != non_literal:
        bad("set_txt", f"only_txt={len(set(domains_txt)-non_literal)} "
                       f"only_csv={len(non_literal-set(domains_txt))}")

    if len(ip_txt) != len(rows):
        bad("count_ip", f"xmpp_ip.txt {len(ip_txt)} != CSV {len(rows)}")

    ip_rows = {}
    for ln in ip_txt:
        parts = [c.strip() for c in ln.split("|")]
        if len(parts) != 8:
            bad("ip_cols", ln[:60])
            continue
        ip_rows[parts[0]] = parts
    if set(ip_rows) != set(csv_by):
        bad("set_ip", f"ip-only={len(set(ip_rows)-set(csv_by))} "
                      f"csv-only={len(set(csv_by)-set(ip_rows))}")

    for r in rows:
        d = r["domain"]
        if r["status"] not in ("alive", "dead", "ip_literal"):
            bad("status", f"{d}: {r['status']}")
        for f in ("c2s", "s2s", "inband", "tls"):
            if r[f] not in ("true", "false", ""):
                bad("bool", f"{d}.{f}={r[f]!r}")
        if r["inband"] == "true" and r["c2s"] != "true":
            bad("logic", f"{d}: inband=true but c2s={r['c2s']!r}")
        if r["status"] == "dead" and (r["ip"] or r["country"] or r["c2s"]):
            bad("dead_fields", d)
        if r["ip"]:
            try:
                ipaddress.ip_address(r["ip"])
            except ValueError:
                bad("ip", f"{d}: {r['ip']!r}")
        if r["country_code"]:
            cc = r["country_code"]
            if not CC_RE.match(cc):
                bad("cc", f"{d}: {cc!r}")
            if r["flag"] != flag(cc):
                bad("flag", f"{d}: {cc} vs {r['flag']!r}")
            if cc in EYES and r["intelligence_alliance"] != EYES[cc]:
                bad("alliance", f"{d}: {cc} vs {r['intelligence_alliance']!r}")
        if r["as"] and not AS_RE.match(r["as"]):
            bad("as", f"{d}: {r['as']!r}")
        if r["updated"] and not TS_RE.match(r["updated"]):
            bad("ts", f"{d}: {r['updated']!r}")

        # README <-> CSV spot consistency
        c = md_by.get(d)
        if c:
            pairs = [(c[1], r["c2s"]), (c[2], r["s2s"]), (c[3], r["inband"]),
                     (c[5], r["ip"]), (c[6], r["country_code"]),
                     (c[7], r["flag"]), (c[8], r["country"]),
                     (c[9], r["isp"]), (c[10], r["org"]), (c[11], r["as"]),
                     (c[12], r["intelligence_alliance"])]
            for a, b in pairs:
                if a != b:
                    bad("cross", f"{d}: README={a!r} CSV={b!r}")
                    break

    # country name consistency per CC
    by_cc = {}
    for r in rows:
        if r["country_code"]:
            by_cc.setdefault(r["country_code"], set()).add(r["country"])
    for cc, names in by_cc.items():
        if len(names) > 1:
            bad("country_variants", f"{cc}: {sorted(names)[:4]}")

    # summary from CSV vs work/xmpp.json
    xmpp = json.load(open(os.path.join(WORK, "xmpp.json"), encoding="utf-8"))
    if len([k for k, v in xmpp.items() if v.get("checked")]) != len(
            [r for r in rows if r["c2s"] in ("true", "false")]):
        bad("probe_count", "checked domains differ from CSV probe rows")

    if problems:
        print(f"\nFAIL: {len(problems)} problems")
        for p in problems[:40]:
            print(" ", p)
        if len(problems) > 40:
            print(f"  ... +{len(problems)-40}")
        sys.exit(1)
    print("OK: dataset is consistent")


if __name__ == "__main__":
    main()
