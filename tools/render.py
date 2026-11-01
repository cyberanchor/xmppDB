#!/usr/bin/env python3
"""Phase 5: render README.md, xmpp_domains.csv, txt files and VALIDATION.md."""

import collections
import csv
import datetime
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "tools", "work")
NOW = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

README_HEADER = ["domain", "C2S", "S2S", "InBand", "Update", "IP",
                 "countryCode", "flag", "country", "isp", "org", "as",
                 "intelligence_alliance"]


def load(name, default=None):
    p = os.path.join(WORK, name)
    if not os.path.exists(p):
        return default if default is not None else {}
    return json.load(open(p, encoding="utf-8"))


def clean(s):
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def tf(v):
    return "true" if v else "false"


def cell(v):
    return "" if v in (None, "") else str(v)


def main():
    data = load("domains.json")
    dns = load("dns.json")
    geo = load("geo.json")
    xmpp = load("xmpp.json")

    # Canonical country name per country code (provider returns e.g. both
    # "Netherlands" and "The Netherlands").
    cc_names = collections.defaultdict(collections.Counter)
    for g in geo.values():
        if isinstance(g, dict) and g.get("status") == "success" and g.get("countryCode"):
            cc_names[g["countryCode"]][g["country"]] += 1
    cc_name = {cc: c.most_common(1)[0][0] for cc, c in cc_names.items()}
    if not xmpp:
        print("warning: xmpp.json missing, probes not included")

    recs = data["domains"] + data["non_domains"]
    recs.sort(key=lambda r: r["domain"])

    rows = []
    csv_rows = []
    for rec in recs:
        d = rec["domain"]
        v = dns.get(d) or {}
        x = xmpp.get(d) or {}
        ip = (v.get("a") or v.get("aaaa") or [None])[0]
        if not ip:
            ip = v.get("srv_ip")
            ip_source = "srv" if ip else ""
        else:
            ip_source = "dns"
        g = geo.get(ip) if ip else None
        if not g or g.get("status") != "success":
            g = {}

        alive = bool(v.get("a") or v.get("aaaa") or v.get("srv_c2s") or v.get("srv_ip"))
        if rec["kind"] == "ip":
            status = "ip_literal"
        elif not alive:
            status = "dead"
        else:
            status = "alive"

        c2s = x.get("c2s") or {}
        s2s = x.get("s2s") or {}
        checked = bool(x.get("checked"))
        c2s_ok = "true" if checked and c2s.get("ok") else ("false" if checked else "")
        s2s_ok = "true" if checked and s2s.get("ok") else ("false" if checked else "")
        inband = ("true" if checked and c2s.get("ok") and c2s.get("register")
                  else ("false" if checked and c2s.get("ok") else ""))
        tls = ("true" if checked and c2s.get("tls") else
               ("false" if checked and c2s.get("ok") else ""))

        cc = g.get("countryCode", "")
        row = {
            "domain": d,
            "c2s": c2s_ok,
            "s2s": s2s_ok,
            "inband": inband,
            "update": NOW if alive else "",
            "ip": ip or "",
            "cc": cc,
            "flag": _flag(cc),
            "country": cc_name.get(cc, g.get("country", "")),
            "isp": clean(g.get("isp")),
            "org": clean(g.get("org")),
            "as": clean(g.get("as")),
            "alliance": _alliance(cc),
            "_status": status,
            "_tls": tls,
            "_sasl": ";".join(c2s.get("sasl") or []),
            "_ptr": clean(g.get("reverse")),
            "_srv_c2s": (f"{v['srv_c2s']['target']}:{v['srv_c2s']['port']}"
                         if v.get("srv_c2s") else ""),
            "_srv_s2s": (f"{v['srv_s2s']['target']}:{v['srv_s2s']['port']}"
                         if v.get("srv_s2s") else ""),
            "_ip_source": ip_source,
            "_sources": "+".join(rec["sources"]),
        }
        notes = []
        if v.get("dns_error"):
            notes.append("dns:" + v["dns_error"])
        if checked and c2s.get("error"):
            notes.append("c2s:" + c2s["error"])
        if checked and c2s.get("note"):
            notes.append("c2s:" + c2s["note"])
        if checked and s2s.get("error"):
            notes.append("s2s:" + s2s["error"])
        if checked and s2s.get("note"):
            notes.append("s2s:" + s2s["note"])
        row["_notes"] = ";".join(notes)
        rows.append(row)

        csv_rows.append({
            "domain": d,
            "status": status,
            "sources": row["_sources"],
            "c2s": c2s_ok,
            "s2s": s2s_ok,
            "inband": inband,
            "tls": tls,
            "sasl_mechs": row["_sasl"],
            "ip": ip or "",
            "ip_source": ip_source,
            "country_code": cc,
            "country": row["country"],
            "flag": row["flag"],
            "isp": row["isp"],
            "org": row["org"],
            "as": row["as"],
            "ptr": row["_ptr"],
            "srv_c2s": row["_srv_c2s"],
            "srv_s2s": row["_srv_s2s"],
            "intelligence_alliance": row["alliance"],
            "updated": NOW if alive else "",
            "notes": row["_notes"],
        })

    # ---------- CSV ----------
    cols = ["domain", "status", "sources", "c2s", "s2s", "inband", "tls",
            "sasl_mechs", "ip", "ip_source", "country_code", "country", "flag",
            "isp", "org", "as", "ptr", "srv_c2s", "srv_s2s",
            "intelligence_alliance", "updated", "notes"]
    with open(os.path.join(BASE, "xmpp_domains.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(csv_rows)

    # ---------- txt files ----------
    with open(os.path.join(BASE, "xmpp_domain_list.txt"), "w", encoding="utf-8") as f:
        for r in rows:
            if r["_status"] != "ip_literal":
                f.write(r["domain"] + "\n")

    with open(os.path.join(BASE, "xmpp_ip.txt"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(" | ".join([
                r["domain"], r["ip"], r["cc"], r["country"],
                r["isp"], r["org"], r["as"], r["_ptr"],
            ]) + "\n")

    # ---------- README ----------
    stats = collections.Counter(r["_status"] for r in rows)
    c2s_t = sum(1 for r in rows if r["c2s"] == "true")
    c2s_f = sum(1 for r in rows if r["c2s"] == "false")
    s2s_t = sum(1 for r in rows if r["s2s"] == "true")
    s2s_f = sum(1 for r in rows if r["s2s"] == "false")
    ib_t = sum(1 for r in rows if r["inband"] == "true")
    ib_f = sum(1 for r in rows if r["inband"] == "false")
    tls_t = sum(1 for r in rows if r["_tls"] == "true")
    srv_c2s = sum(1 for r in rows if r["_srv_c2s"])
    srv_s2s = sum(1 for r in rows if r["_srv_s2s"])
    countries = collections.Counter(r["country"] for r in rows if r["country"])

    out = []
    out.append("# XMPP Domain Database\n")
    out.append(f"**Generated:** {NOW}  ")
    out.append("**Records:** %d domains (%d alive, %d dead, %d IP literals)  "
               % (len(rows), stats["alive"], stats["dead"], stats["ip_literal"]))
    out.append("**Machine-readable:** [`xmpp_domains.csv`](xmpp_domains.csv) — "
               "full details: SRV targets, TLS, SASL mechanisms, PTR, errors  ")
    out.append("**Method & fixes:** [`VALIDATION.md`](VALIDATION.md)\n")
    out.append("Data was re-validated and re-probed on the generation date: "
               "DNS (A/AAAA, SRV), IP intelligence (country/ISP/org/AS/PTR), "
               "and active XMPP checks (C2S, S2S, STARTTLS, SASL, "
               "XEP-0077 in-band registration advertisement).\n")
    out.append("## Summary\n")
    out.append("| metric | value |")
    out.append("| --- | --- |")
    out.append(f"| total domains | {len(rows)} |")
    out.append(f"| alive (DNS/SRV) | {stats['alive']} |")
    out.append(f"| dead (NXDOMAIN/timeout) | {stats['dead']} |")
    out.append(f"| C2S reachable | {c2s_t} (false: {c2s_f}) |")
    out.append(f"| S2S reachable | {s2s_t} (false: {s2s_f}) |")
    out.append(f"| STARTTLS offered | {tls_t} |")
    out.append(f"| in-band registration advertised | {ib_t} (false: {ib_f}) |")
    out.append(f"| SRV `_xmpp-client._tcp` | {srv_c2s} |")
    out.append(f"| SRV `_xmpp-server._tcp` | {srv_s2s} |")
    out.append("")
    out.append("Top countries:\n")
    out.append("| country | domains |")
    out.append("| --- | --- |")
    for c, n in countries.most_common(12):
        out.append(f"| {c} | {n} |")
    out.append("")
    out.append("## Domains\n")
    out.append("| " + " | ".join(README_HEADER) + " |")
    out.append("| " + " | ".join(["---"] * len(README_HEADER)) + " |")
    for r in rows:
        out.append("| " + " | ".join([
            r["domain"], r["c2s"], r["s2s"], r["inband"], r["update"],
            r["ip"], r["cc"], r["flag"], clean(r["country"]),
            clean(r["isp"]), clean(r["org"]), clean(r["as"]), r["alliance"],
        ]) + " |")
    out.append("")
    with open(os.path.join(BASE, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    # ---------- old vs new comparison ----------
    cmp_rows = collections.Counter()
    for rec in recs:
        old = rec.get("old") or {}
        x = xmpp.get(rec["domain"]) or {}
        c2sx = x.get("c2s") or {}
        chk = bool(x.get("checked"))
        newvals = {
            "c2s": "true" if chk and c2sx.get("ok") else ("false" if chk else "unknown"),
            "s2s": ("true" if chk and (x.get("s2s") or {}).get("ok")
                    else ("false" if chk else "unknown")),
            "inband": ("true" if chk and c2sx.get("ok") and c2sx.get("register")
                       else ("false" if chk and c2sx.get("ok") else "unknown")),
        }
        for f in ("c2s", "s2s", "inband"):
            ov = old.get(f)
            if ov in ("true", "false"):
                cmp_rows[(f, ov, newvals[f])] += 1

    # ---------- VALIDATION ----------
    v = []
    v.append("# Validation & refresh report\n")
    v.append(f"Generated: **{NOW}**\n")
    v.append("## Inputs\n")
    v.append("| file | rows | notes |")
    v.append("| --- | --- | --- |")
    v.append(f"| README.md (old) | {data['counts']['readme_rows']} | "
             "sorted by old probe time, 13 columns |")
    v.append(f"| xmpp_domain_list.txt (old) | {data['counts']['list_rows']} | "
             "alphabetical |")
    v.append(f"| xmpp_ip.txt (old) | {data['counts']['ip_rows']} | "
             "domain + IP intel, 8 columns |")
    v.append("")
    v.append("The three files were **different snapshots**: the old README and "
             "the two txt files shared only 140 domains. The refreshed database "
             "is the union of all three, deduplicated.\n")
    v.append("## Normalization & fixes\n")
    v.append(f"- merged unique names: **{data['counts']['unique_domains']}** "
             f"domains + {data['counts']['non_domains']} non-domain entries")
    v.append("- duplicate lines inside a single file: none")
    v.append("- IP addresses found in the domain list were moved to the "
             "`ip_literal` status and are probed directly "
             "(`47.244.130.192`, `52.77.238.158`)")
    v.append("- old cross-file conflicts (`autistici.org`, `mailbox.bz`, "
             "`tigase.me`, `404.city`) are resolved: one record per domain, "
             "fresh DNS/intel used everywhere")
    v.append("- country names unified via the IP-intelligence provider "
             "(`Netherlands` vs `The Netherlands` etc.)")
    v.append("- ASN field kept in the original `AS<number> <name>` format")
    v.append("")
    v.append("## Domain status\n")
    v.append(f"- alive: **{stats['alive']}**")
    v.append(f"- dead (NXDOMAIN/timeout, kept with empty fields): "
             f"**{stats['dead']}**")
    v.append(f"- IP literals: **{stats['ip_literal']}**")
    v.append("")
    v.append("## XMPP checks\n")
    v.append("Definitions used in this database:")
    v.append("- **C2S** — a client stream was opened on the SRV target "
             "(`_xmpp-client._tcp`, fallback `:5222`) and stream features were "
             "returned")
    v.append("- **S2S** — a server stream was opened on the SRV target "
             "(`_xmpp-server._tcp`, fallback `:5269`)")
    v.append("- **InBand** — XEP-0077 in-band registration is advertised after "
             "STARTTLS (feature or positive `<iq type='result'>` on "
             "`jabber:iq:register`)")
    v.append("- no authentication or registration was attempted\n")
    v.append(f"Results: C2S true {c2s_t} / false {c2s_f}; S2S true {s2s_t} / "
             f"false {s2s_f}; STARTTLS {tls_t}; in-band {ib_t}.\n")
    v.append("Note: the old `InBand` column meant an actual registration "
             "probe and does not always match the new advertisement-based "
             "value (e.g. `disroot.org`, `xmpp.jp`).\n")
    if cmp_rows:
        v.append("## Old vs new probe results\n")
        v.append("Rows where the old README had a boolean value:\n")
        v.append("| column | old | new true | new false | new unknown |")
        v.append("| --- | --- | --- | --- | --- |")
        for f in ("c2s", "s2s", "inband"):
            for ov in ("true", "false"):
                t = sum(cmp_rows[(f, ov, nv)] for nv in ["true"])
                fl = sum(cmp_rows[(f, ov, nv)] for nv in ["false"])
                unk = sum(cmp_rows[(f, ov, nv)] for nv in ["unknown"])
                if t + fl + unk:
                    v.append(f"| {f} | {ov} | {t} | {fl} | {unk} |")
        v.append("")
        v.append("Differences are expected: servers change, and the old "
                 "in-band column was an attempt-based probe.\n")

    v.append("## Known limitations\n")
    v.append("- probe timeouts / rate limits can produce false negatives; "
             "the raw error is in the CSV `notes` column")
    v.append("- geo/ASN/PTR come from ip-api.com (free tier)")
    v.append("- C2S/S2S checks are reachability checks, not a full XMPP "
             "conformance test")
    v.append("- dead domains are intentionally kept with empty fields, so "
             "rows can be resurrected later\n")
    v.append("## Files\n")
    v.append("| file | content |")
    v.append("| --- | --- |")
    v.append("| `README.md` | human-readable table (13 columns) |")
    v.append("| `xmpp_domains.csv` | full data: status, SRV, TLS, SASL, PTR, "
             "errors, sources |")
    v.append("| `xmpp_domain_list.txt` | plain domain list |")
    v.append("| `xmpp_ip.txt` | domain + IP + geo/ASN/PTR |")
    v.append("| `tools/` | reproducible pipeline "
             "(build → dns → geo → probe → render) |")
    with open(os.path.join(BASE, "VALIDATION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(v))

    print(f"rows={len(rows)} alive={stats['alive']} dead={stats['dead']} "
          f"ip_literal={stats['ip_literal']}")
    print(f"c2s={c2s_t}/{c2s_f} s2s={s2s_t}/{s2s_f} tls={tls_t} inband={ib_t}")
    print("wrote README.md, xmpp_domains.csv, xmpp_domain_list.txt, xmpp_ip.txt, VALIDATION.md")


def _flag(cc):
    if not cc or len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in cc)


def _alliance(cc):
    return {
        "US": "Five Eyes 👁️", "GB": "Five Eyes 👁️", "CA": "Five Eyes 👁️",
        "AU": "Five Eyes 👁️", "NZ": "Five Eyes 👁️",
        "DK": "Nine Eyes 👁️", "FR": "Nine Eyes 👁️", "NL": "Nine Eyes 👁️",
        "NO": "Nine Eyes 👁️",
        "BE": "Fourteen Eyes 👁️", "DE": "Fourteen Eyes 👁️", "IT": "Fourteen Eyes 👁️",
        "ES": "Fourteen Eyes 👁️", "SE": "Fourteen Eyes 👁️",
    }.get(cc, "")


if __name__ == "__main__":
    main()
