#!/usr/bin/env python3
"""Write the plain lists in the repository root from data/servers/. They keep the format of the first xmppDB
files, for anyone who downloads them directly:

  xmpp_domain_list.txt  every domain, one per line, sorted; IP addresses left out
  xmpp_ip.txt           domain | ip | country code | country | isp | org | as | ptr
                        (every server; the fields after the domain are empty for a gone domain)

usage: python3 tools/lists.py [--check]   (--check: exit 1 when a file is not up to date)
"""
import ipaddress
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xdbdata  # noqa: E402

FILES = ("xmpp_domain_list.txt", "xmpp_ip.txt")


def country_code(flag):
    """🇩🇪 -> DE"""
    return "".join(chr(ord(c) - 0x1F1E6 + ord("A")) for c in flag if 0x1F1E6 <= ord(c) <= 0x1F1FF)


def is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def render(recs):
    domains = [r["domain"] for r in recs if not is_ip(r["domain"])]
    ip_rows = []
    for r in recs:
        g = r.get
        ip_rows.append(" | ".join([r["domain"], g("ip", ""), country_code(g("flag", "")), g("country", ""),
                                   g("isp", ""), g("org", ""), g("asn", ""), g("ptr", "")]))
    return {
        "xmpp_domain_list.txt": "\n".join(domains) + "\n",
        "xmpp_ip.txt": "\n".join(ip_rows) + "\n",
    }


def main():
    out = render(xdbdata.load_all())
    stale = []
    for name, text in out.items():
        path = os.path.join(xdbdata.ROOT, name)
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old == text:
            continue
        if "--check" in sys.argv:
            stale.append(name)
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"{name}: {text.count(chr(10))} lines")
    if stale:
        raise SystemExit(f"not up to date: {', '.join(stale)}; run python3 tools/lists.py")
    if "--check" in sys.argv:
        print("lists up to date")


if __name__ == "__main__":
    main()
