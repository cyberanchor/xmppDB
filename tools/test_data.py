#!/usr/bin/env python3
"""Check the server data and what is built from it. Exit code 1 and a list of problems when something is wrong.

  files   every data/servers/*.yaml: fields and types (xdbdata.check), file named after the domain, canonical
          format (the file reads back to exactly what xdbdata would write), no two servers with one page address
  README  the "XMPP servers" table matches the records (tools/readme_tables.py --check)
  lists   xmpp_domain_list.txt and xmpp_ip.txt match the records (tools/lists.py --check)
  site    site/public/: servers.json equals the records, one page per server and no other, one table row per
          server on the home page, servers.csv has one row per server (skipped with --no-site)

usage: python3 tools/test_data.py [--no-site]
"""
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lists  # noqa: E402
import readme_tables  # noqa: E402
import xdbdata  # noqa: E402

PUBLIC = os.path.join(xdbdata.ROOT, "site", "public")


def check_files(problems):
    recs = xdbdata.load_all()
    slugs = {}
    for r in recs:
        f = r["_file"]
        found = xdbdata.check(r)
        problems += [f"data/servers/{f}: {p}" for p in found]
        if r.get("domain") and f != r["domain"] + ".yaml":
            problems.append(f"data/servers/{f}: holds {r['domain']!r}; name the file after the domain")
        if not found:
            with open(os.path.join(xdbdata.DIR, f), encoding="utf-8") as fh:
                if fh.read() != xdbdata.dumps(r):
                    problems.append(f"data/servers/{f}: not in the canonical format; load and save it with xdbdata")
        slug = xdbdata.slug(r.get("domain", ""))
        if slug in slugs:
            problems.append(f"data/servers/{f}: same page address /servers/{slug}/ as {slugs[slug]}")
        slugs[slug] = f
    return recs


def check_readme(recs, problems):
    path = os.path.join(xdbdata.ROOT, "README.md")
    text = open(path, encoding="utf-8").read()
    if readme_tables.render(text, recs) != text:
        problems.append("README.md: the server table is not up to date (python3 tools/readme_tables.py)")


def check_lists(recs, problems):
    for name, text in lists.render(recs).items():
        path = os.path.join(xdbdata.ROOT, name)
        if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
            problems.append(f"{name}: not up to date (python3 tools/lists.py)")


def check_site(recs, problems):
    if not os.path.isdir(PUBLIC):
        problems.append("site/public/ is missing (site/build.sh)")
        return
    clean = [{k: v for k, v in r.items() if k != "_file"} for r in recs]
    with open(os.path.join(PUBLIC, "servers.json"), encoding="utf-8") as f:
        if json.load(f) != clean:
            problems.append("site/public/servers.json differs from data/servers/ (rebuild with site/build.sh)")
    with open(os.path.join(PUBLIC, "servers.csv"), encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if [r["domain"] for r in rows] != [r["domain"] for r in recs]:
        problems.append("site/public/servers.csv: the rows do not match the records")
    want = {xdbdata.slug(r["domain"]) for r in recs}
    have = set(os.listdir(os.path.join(PUBLIC, "servers")))
    for s in sorted(want - have):
        problems.append(f"site/public/servers/{s}/ is missing")
    for s in sorted(have - want):
        problems.append(f"site/public/servers/{s}/ has no record (rebuild with site/build.sh)")
    with open(os.path.join(PUBLIC, "index.html"), encoding="utf-8") as f:
        links = re.findall(r'<a href="?servers/([^/"]+)/"?>', f.read())
    if sorted(links) != sorted(want):
        problems.append(f"site/public/index.html: {len(links)} table rows for {len(recs)} servers")


def main():
    problems = []
    recs = check_files(problems)
    check_readme(recs, problems)
    check_lists(recs, problems)
    if "--no-site" not in sys.argv:
        check_site(recs, problems)
    for p in problems:
        print(p)
    states = {}
    for r in recs:
        states[xdbdata.state(r)] = states.get(xdbdata.state(r), 0) + 1
    summary = ", ".join(f"{n} {s}" for s, n in sorted(states.items(), key=lambda x: -x[1]))
    print(f"{len(recs)} servers ({summary}): {'%d problems' % len(problems) if problems else 'all checks passed'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
