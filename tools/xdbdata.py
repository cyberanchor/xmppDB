#!/usr/bin/env python3
"""Server data of xmppDB: data/servers/<domain>.yaml, one file per XMPP server.

Shared by the importers, the collector, the README writer and the tests. Fields: data/README.md.

    load_all()     -> every record, sorted by domain
    load(domain)   -> one record
    save(record)   -> writes data/servers/<domain>.yaml in the canonical format
    dumps(record)  -> the canonical YAML text of a record
    check(record)  -> list of problems (unknown fields, wrong types); empty when the record is fine
    state(record)  -> online | federation | offline | gone | unchecked
"""
import glob
import os
import re

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.environ.get("XDB_DATA_DIR") or os.path.join(ROOT, "data", "servers")
HEADER = "# xmppDB server record; fields are described in data/README.md\n"

# Field types, in the order they are written.
TEXT, BOOL, INT, LIST, LANGS, MAP = "text", "bool", "int", "list", "langs", "map"
FIELDS = {
    "domain": TEXT, "dead": BOOL, "flag": TEXT, "country": TEXT, "alliance": INT,
    "ip": TEXT, "asn": TEXT, "isp": TEXT, "org": TEXT, "ptr": TEXT,
    "srv_client": TEXT, "srv_server": TEXT,
    "c2s": BOOL, "s2s": BOOL, "starttls": BOOL, "registration": BOOL, "sasl": LIST, "errors": LIST,
    "provider": MAP, "sources": LIST, "last_checked": TEXT,
}
PROVIDER = {
    "category": TEXT, "since": TEXT, "updated": TEXT, "organization": TEXT, "software": TEXT,
    "locations": LIST, "website": LANGS, "legal_notice": LANGS, "free": BOOL, "professional_hosting": BOOL,
    "green_hosting": BOOL, "bus_factor": INT, "inband": BOOL, "registration_web": LANGS, "captcha": BOOL,
    "email_required": BOOL, "password_reset": LANGS, "archive_days": INT, "upload_file_mb": INT,
    "upload_total_mb": INT, "upload_days": INT, "compliance": INT, "support_email": LIST, "support_chat": LIST,
    "support_groupchat": LIST, "alternative_jids": LIST,
}
FLOW = {"sasl", "sources", "locations"}  # short lists written on one line
ALLIANCE = {5: "Five Eyes", 9: "Nine Eyes", 14: "Fourteen Eyes"}
# Five / Nine / Fourteen Eyes membership by country code (the same grouping as the earlier lists and eMailCompare)
EYES = {"US": 5, "GB": 5, "CA": 5, "AU": 5, "NZ": 5, "DK": 9, "FR": 9, "NL": 9, "NO": 9,
        "BE": 14, "DE": 14, "IT": 14, "ES": 14, "SE": 14}
CATEGORIES = ("A", "B", "C", "D")
STATES = ("online", "federation", "offline", "gone", "unchecked")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# One-line strings written in quotes although PyYAML (YAML 1.1) would leave them plain: everything a YAML 1.2
# parser such as Hugo's might read as a number, boolean or null (same rule as eMailCompare's emcdata.py).
QUOTE = re.compile(r"^(?:[-+]?\.?[0-9]|[-+]?\.(?:inf|Inf|INF|nan|NaN|NAN)$"
                   r"|(?:null|Null|NULL|~|true|True|TRUE|false|False|FALSE|yes|Yes|YES|no|No|NO|on|On|ON|off|Off|OFF)$)")


class _Flow(list):
    """A list written on one line: [a, b]."""


class _Dumper(yaml.SafeDumper):
    pass


def _str(dumper, s):
    if "\n" in s or any(c in s for c in ("\x85", " ", " ", "\r")):
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style='"')
    if QUOTE.match(s):
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="'")
    return dumper.represent_scalar("tag:yaml.org,2002:str", s)


_Dumper.add_representer(str, _str)
_Dumper.add_representer(_Flow, lambda d, v: d.represent_sequence("tag:yaml.org,2002:seq", v, flow_style=True))
_Dumper.add_representer(dict, lambda d, m: d.represent_mapping("tag:yaml.org,2002:map", m.items()))


class _Loader(yaml.SafeLoader):
    """Reads YAML the way Hugo (a YAML 1.2 parser) does: no dates, no yes/no/on/off booleans, no sexagesimal
    numbers; those stay text."""


_Loader.yaml_implicit_resolvers = {}
for _tag, _regexp, _first in (
        ("null", r"^(?:~|null|Null|NULL|)$", ["~", "n", "N", ""]),
        ("bool", r"^(?:true|True|TRUE|false|False|FALSE)$", list("tTfF")),
        ("int", r"^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$", list("-+0123456789")),
        ("float", r"^(?:[-+]?(?:\.[0-9]+|[0-9]+(?:\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?|[-+]?\.(?:inf|Inf|INF)"
                  r"|\.(?:nan|NaN|NAN))$", list("-+0123456789."))):
    _Loader.add_implicit_resolver("tag:yaml.org,2002:" + _tag, re.compile(_regexp), _first)


def _empty(v):
    return v is None or v == "" or v == [] or v == {}


def _check_value(where, kind, v):
    if kind == TEXT and not isinstance(v, str):
        return f"{where} must be text"
    if kind == BOOL and not isinstance(v, bool):
        return f"{where} must be true or false"
    if kind == INT and (isinstance(v, bool) or not isinstance(v, int)):
        return f"{where} must be a whole number"
    if kind == LIST and not (isinstance(v, list) and all(isinstance(x, str) and x for x in v)):
        return f"{where} must be a list of text"
    if kind == LANGS and not (isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str)
                                                          for k, x in v.items())):
        return f"{where} must be a map of language: address"
    return None


def check(rec):
    """Problems of a record as text, [] when it is fine. Checks field names, types and a few value rules."""
    if not isinstance(rec, dict):
        return ["the file is not a mapping of fields"]
    out = []
    for k, v in rec.items():
        if k.startswith("_"):
            continue
        if k not in FIELDS:
            out.append(f"unknown field {k!r} (fields: data/README.md)")
            continue
        if _empty(v):
            out.append(f"{k} is empty; leave the field out instead")
            continue
        if FIELDS[k] == MAP:
            if not isinstance(v, dict):
                out.append("provider must be a map")
                continue
            for pk, pv in v.items():
                if pk not in PROVIDER:
                    out.append(f"unknown field provider.{pk}")
                elif _empty(pv):
                    out.append(f"provider.{pk} is empty; leave the field out instead")
                else:
                    p = _check_value(f"provider.{pk}", PROVIDER[pk], pv)
                    if p:
                        out.append(p)
            if v.get("category") not in CATEGORIES:
                out.append("provider.category must be A, B, C or D")
            continue
        p = _check_value(k, FIELDS[k], v)
        if p:
            out.append(p)
    if not rec.get("domain"):
        out.append("domain is required")
    elif rec["domain"] != rec["domain"].lower().strip():
        out.append("domain must be lower case")
    if "alliance" in rec and rec["alliance"] not in ALLIANCE:
        out.append("alliance must be 5, 9 or 14")
    if rec.get("dead") is False:
        out.append("dead: false is the default; leave the field out")
    for k in ("last_checked",):
        if k in rec and isinstance(rec[k], str) and not DATE.match(rec[k]):
            out.append(f"{k} must be a date YYYY-MM-DD")
    for k in ("since", "updated"):
        v = (rec.get("provider") or {}).get(k)
        if isinstance(v, str) and not DATE.match(v):
            out.append(f"provider.{k} must be a date YYYY-MM-DD")
    return out


def _ordered(rec):
    out = {}
    for k in FIELDS:
        v = rec.get(k)
        if _empty(v):
            continue
        if k == "provider":
            v = {pk: v[pk] for pk in PROVIDER if not _empty(v.get(pk))}
            v = {pk: (_Flow(x) if pk in FLOW else dict(sorted(x.items())) if isinstance(x, dict) else x)
                 for pk, x in v.items()}
        elif k in FLOW:
            v = _Flow(v)
        out[k] = v
    return out


def dumps(rec):
    problems = check({k: v for k, v in rec.items() if not _empty(v) or k.startswith("_")})
    if problems:
        raise ValueError(f"{rec.get('domain')}: " + "; ".join(problems))
    text = yaml.dump(_ordered(rec), Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=4096,
                     default_flow_style=False)
    return HEADER + text


def loads(text):
    return yaml.load(text, Loader=_Loader)  # noqa: S506  (a SafeLoader subclass)


def path(domain, directory=None):
    return os.path.join(directory or DIR, domain.lower() + ".yaml")


def load(domain, directory=None):
    with open(path(domain, directory), encoding="utf-8") as f:
        return loads(f.read())


def load_all(directory=None):
    recs = []
    for p in sorted(glob.glob(os.path.join(directory or DIR, "*.yaml"))):
        with open(p, encoding="utf-8") as f:
            rec = loads(f.read())
        if not isinstance(rec, dict):
            raise ValueError(f"{p}: not a YAML mapping of fields")
        rec["_file"] = os.path.basename(p)
        recs.append(rec)
    recs.sort(key=lambda r: r.get("domain", ""))
    return recs


def save(rec, directory=None):
    """Write a record; refuses unknown fields and text that does not read back to the same record."""
    rec = {k: v for k, v in rec.items() if not k.startswith("_") and not _empty(v)}
    if rec.get("dead") is False:
        del rec["dead"]
    if isinstance(rec.get("provider"), dict):
        rec["provider"] = {k: v for k, v in rec["provider"].items() if not _empty(v)}
    text = dumps(rec)
    if loads(text) != rec:
        raise ValueError(f"{rec.get('domain')}: the YAML text would not read back to the same record")
    os.makedirs(directory or DIR, exist_ok=True)
    with open(path(rec["domain"], directory), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def remove(domain, directory=None):
    os.remove(path(domain, directory))


def state(rec):
    """online: clients can connect · federation: only the server-to-server port answered · offline: the domain
    resolves but no XMPP stream opened · gone: the domain does not resolve · unchecked: not checked yet."""
    if rec.get("dead"):
        return "gone"
    if rec.get("c2s"):
        return "online"
    if rec.get("s2s"):
        return "federation"
    if "c2s" in rec or "s2s" in rec:
        return "offline"
    return "unchecked"


def flag(cc):
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in cc)


def slug(domain):
    """Page address of a server: the domain with dots as dashes (same rule as the site)."""
    return domain.lower().replace(".", "-")
