#!/usr/bin/env python3
"""Write the "XMPP servers" table of README.md from data/servers/, then align the | of every Markdown table.

  Status        🟢 online · 🟡 federation only · 🔴 offline · ⏳ not checked · ❌ gone (domain struck out)
  Domain        sorted by name
  Flag          the record's flag, ❓ when it has none
  Registration  ✅ in-band registration advertised · 🌐 sign-up page (XMPP Providers) · 🔒 closed · empty: unknown

Widths are measured as a monospace editor shows them: emoji and wide characters take two columns, combining
marks and variation selectors none.

usage: python3 tools/readme_tables.py [README] [--check]   (--check: exit 1 when the file is not up to date)
"""
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xdbdata  # noqa: E402

HEADING = "## XMPP servers"
STATE = {"online": "🟢", "federation": "🟡", "offline": "🔴", "unchecked": "⏳", "gone": "❌"}
ZERO_WIDTH = {"‍", "︎", "️"}


def width(text):
    return sum(0 if unicodedata.combining(ch) or ch in ZERO_WIDTH
               else 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def align(rows):
    cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    ncol = max(len(r) for r in cells)
    cells = [r + [""] * (ncol - len(r)) for r in cells]
    sep = [i for i, r in enumerate(cells) if all(re.fullmatch(r":?-+:?", c) for c in r if c)]
    widths = [max([width(r[j]) for i, r in enumerate(cells) if i not in sep] + [3]) for j in range(ncol)]
    out = []
    for i, r in enumerate(cells):
        if i in sep:
            out.append("|" + "|".join("-" * (widths[j] + 2) for j in range(ncol)) + "|")
        else:
            out.append("| " + " | ".join(c + " " * (widths[j] - width(c)) for j, c in enumerate(r)) + " |")
    return out


def registration(rec):
    if rec.get("registration"):
        return "✅"
    if (rec.get("provider") or {}).get("registration_web"):
        return "🌐"
    if "registration" in rec:
        return "🔒"
    return ""


def rows_for(recs):
    out = []
    for r in recs:
        state = xdbdata.state(r)
        domain = f"~~{r['domain']}~~" if state == "gone" else r["domain"]
        out.append(f"| {STATE[state]} | {domain} | {r.get('flag') or '❓'} | {registration(r)} |")
    return out


def render(text, recs):
    lines = text.split("\n")
    out, i, found = [], 0, False
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        if line.strip() != HEADING:
            continue
        found = True
        while i < len(lines) and not lines[i].strip().startswith("|"):  # text between heading and table
            out.append(lines[i])
            i += 1
        out += lines[i:i + 2]  # header row and separator
        i += 2
        while i < len(lines) and lines[i].strip().startswith("|"):  # old rows
            i += 1
        out += rows_for(recs)
    if not found:
        raise SystemExit(f'README: heading "{HEADING}" with a table under it not found')
    final, block = [], []
    for line in out + [""]:
        if line.strip().startswith("|"):
            block.append(line)
            continue
        if block:
            final += align(block)
            block = []
        final.append(line)
    return "\n".join(final[:-1])


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    path = args[0] if args else os.path.join(xdbdata.ROOT, "README.md")
    text = open(path, encoding="utf-8").read()
    recs = xdbdata.load_all()
    new = render(text, recs)
    if "--check" in sys.argv:
        if new != text:
            raise SystemExit(f"{path}: the server table is not up to date; run python3 tools/readme_tables.py")
        print(f"{path}: server table up to date ({len(recs)} rows)")
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print(f"{path}: {len(recs)} rows")


if __name__ == "__main__":
    main()
