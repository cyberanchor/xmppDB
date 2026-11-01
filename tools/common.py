"""Shared helpers for the xmppDB validation/update pipeline."""

import ipaddress
import re

# Five/Nine/Fourteen Eyes groupings used by the original README.
EYES = {
    "US": "Five Eyes 👁️", "GB": "Five Eyes 👁️", "CA": "Five Eyes 👁️",
    "AU": "Five Eyes 👁️", "NZ": "Five Eyes 👁️",
    "DK": "Nine Eyes 👁️", "FR": "Nine Eyes 👁️", "NL": "Nine Eyes 👁️", "NO": "Nine Eyes 👁️",
    "BE": "Fourteen Eyes 👁️", "DE": "Fourteen Eyes 👁️", "IT": "Fourteen Eyes 👁️",
    "ES": "Fourteen Eyes 👁️", "SE": "Fourteen Eyes 👁️",
}

LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")
TS_FMT = "%Y-%m-%d %H:%M:%S UTC"


def normalize(raw):
    """Return (normalized_domain, notes) after stripping/lowercasing."""
    notes = []
    d = raw.strip()
    if d != raw.strip("\n"):
        pass
    if d != raw:
        notes.append("whitespace")
    if d != d.lower():
        notes.append("uppercased")
        d = d.lower()
    if d.endswith("."):
        notes.append("trailing_dot")
        d = d.rstrip(".")
    return d, notes


def classify(d):
    """Return kind in {ip, invalid, single_label, domain}."""
    try:
        ipaddress.ip_address(d)
        return "ip"
    except ValueError:
        pass
    if ".." in d or d.startswith(".") or d.endswith("."):
        return "invalid"
    labels = d.split(".")
    if len(labels) < 2:
        return "single_label"
    if len(d) > 253:
        return "invalid"
    for lab in labels:
        if not LABEL_RE.match(lab):
            return "invalid"
    if labels[-1].isdigit():
        return "invalid"
    return "domain"


def flag(cc):
    if not cc or len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c.upper()) - ord("A")) for c in cc)


def alliance(cc):
    return EYES.get(cc, "")


def ip_version(s):
    try:
        return "v6" if ipaddress.ip_address(s).version == 6 else "v4"
    except ValueError:
        return ""
