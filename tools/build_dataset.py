#!/usr/bin/env python3
"""Phase 1: merge README.md + xmpp_domain_list.txt + xmpp_ip.txt into one
normalized dataset, validate domain syntax and report every fix."""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import classify, normalize  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "tools", "work")

README_COLS = ["domain", "c2s", "s2s", "inband", "update", "ip", "cc", "flag",
               "country", "isp", "org", "asn", "alliance"]
IP_COLS = ["domain", "ip", "cc", "country", "isp", "org", "asn", "ptr"]


def parse_readme(path):
    rows = []
    for ln in open(path, encoding="utf-8"):
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != 13:
            continue
        if cells[0] == "domain":
            continue
        if all(set(c) <= {"-", ":"} for c in cells):
            continue
        rows.append(dict(zip(README_COLS, cells)))
    return rows


def parse_ipfile(path):
    rows = []
    for ln in open(path, encoding="utf-8"):
        if not ln.strip():
            continue
        cells = [c.strip() for c in ln.rstrip("\n").split("|")]
        if len(cells) != 8:
            continue
        rows.append(dict(zip(IP_COLS, cells)))
    return rows


def main():
    os.makedirs(WORK, exist_ok=True)
    readme = parse_readme(os.path.join(BASE, "README.md"))
    iprows = parse_ipfile(os.path.join(BASE, "xmpp_ip.txt"))
    lst = [ln.strip() for ln in open(os.path.join(BASE, "xmpp_domain_list.txt"),
                                     encoding="utf-8") if ln.strip()]

    issues = collections.defaultdict(list)
    merged = {}

    def put(raw, source, old=None):
        d, notes = normalize(raw)
        if d != raw.lower():
            pass
        for n in notes:
            issues[n].append(raw)
        if not d:
            issues["empty"].append(repr(raw))
            return
        kind = classify(d)
        rec = merged.setdefault(d, {
            "domain": d, "kind": kind, "sources": [], "old": {}, "notes": [],
        })
        if source not in rec["sources"]:
            rec["sources"].append(source)
        if rec["kind"] != kind:
            rec["kind"] = kind
        if kind != "domain":
            issues["non_domain_" + kind].append(d)
        if old:
            for k, v in old.items():
                if v and not rec["old"].get(k):
                    rec["old"][k] = v

    for r in readme:
        put(r["domain"], "readme", r)
    for r in iprows:
        put(r["domain"], "ipfile", r)
    for d in lst:
        put(d, "list")

    # duplicates that collapsed after normalization
    raw_names = [r["domain"].strip().lower() for r in readme] + \
                [r["domain"].strip().lower() for r in iprows] + \
                [d.strip().lower() for d in lst]
    counts = collections.Counter(raw_names)
    dups = {k: v for k, v in counts.items() if v > 1 and k in merged}

    domain_recs = sorted((r for r in merged.values() if r["kind"] == "domain"),
                         key=lambda r: r["domain"])
    other = sorted((r for r in merged.values() if r["kind"] != "domain"),
                   key=lambda r: r["domain"])

    json.dump({
        "generated_at": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "domains": domain_recs,
        "non_domains": other,
        "issues": {k: v for k, v in issues.items()},
        "merged_duplicates": dups,
        "counts": {
            "readme_rows": len(readme),
            "ip_rows": len(iprows),
            "list_rows": len(lst),
            "unique_domains": len(domain_recs),
            "non_domains": len(other),
        },
    }, open(os.path.join(WORK, "domains.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)

    by_src = collections.Counter(tuple(sorted(r["sources"])) for r in merged.values())
    print(f"readme={len(readme)} ipfile={len(iprows)} list={len(lst)}")
    print(f"unique valid domains: {len(domain_recs)}")
    print(f"non-domain entries : {len(other)} -> {[r['domain'] for r in other]}")
    print(f"unique names merged from sources: {len(merged)}")
    for combo, n in sorted(by_src.items(), key=lambda kv: -kv[1]):
        print(f"  sources={combo}: {n}")
    # Intra-file duplicates are real errors; cross-source merging is expected.
    intra = {}
    for name, seq in (("readme", [r["domain"] for r in readme]),
                      ("ipfile", [r["domain"].split(" | ")[0] for r in iprows]),
                      ("list", lst)):
        c = collections.Counter(x.strip().lower() for x in seq)
        intra[name] = {k: v for k, v in c.items() if v > 1}
    print(f"intra-file duplicates: {intra}")
    for k in sorted(issues):
        uniq = sorted(set(issues[k]))
        print(f"[{k}] {len(uniq)}: {uniq[:6]}")


if __name__ == "__main__":
    main()
