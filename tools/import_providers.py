#!/usr/bin/env python3
"""Import the curated provider list of XMPP Providers (https://providers.xmpp.net, data under CC0-1.0).

Downloads https://data.xmpp.net/providers/v2/providers-D.json (every listed provider with its category) and
providers.json (the same properties with their sources), and writes the "provider" block of
data/servers/<domain>.yaml. A provider that is not in data/servers/ yet gets a new file without check results;
run tools/collect.py --unchecked afterwards. Servers that left the list lose their provider block.

A property without a source is a default value of the list, not a statement of the provider ("unknown" on
providers.xmpp.net), so it is left out, as are -1 (unknown) numbers and empty values.

usage: python3 tools/import_providers.py [--from DIR]   (DIR holds providers-D.json and providers.json)
"""
import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xdbdata  # noqa: E402

API = "https://data.xmpp.net/providers/v2/"
FILES = ("providers-D.json", "providers.json")
SOURCE = "xmpp-providers"


def fetch(name, directory):
    if directory:
        with open(os.path.join(directory, name), encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(API + name, headers={"User-Agent": "xmppDB-import/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def addresses(by_lang):
    """{"en": ["a@x"], "de": ["a@x", "b@x"]} -> ["a@x", "b@x"]"""
    out = []
    for lst in (by_lang or {}).values():
        for a in lst if isinstance(lst, list) else [lst]:
            if a and a not in out:
                out.append(a)
    return out


def block(flat, full):
    """The provider block of one provider: flat = its entry in providers-D.json, full = in providers.json."""
    def known(key):
        p = full.get(key)
        return isinstance(p, dict) and bool(p.get("source"))

    def num(key):
        v = flat.get(key)
        return v if known(key) and isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None

    def yesno(key):
        v = flat.get(key)
        return v if known(key) and isinstance(v, bool) else None

    def langs(key):
        v = flat.get(key) or {}
        return {k.lower(): u for k, u in v.items() if isinstance(u, str) and u.startswith("http")} or None

    software = " ".join(x for x in (flat.get("serverSoftwareName"), flat.get("serverSoftwareVersion"))
                        if known("serverSoftwareName") and x)
    bus = num("busFactor")
    return {
        "category": flat["category"],
        "since": flat.get("since") if known("since") else None,
        "updated": flat.get("latestChange"),
        "organization": (flat.get("organization") or None) if known("organization") else None,
        "software": software or None,
        "locations": [c.lower() for c in flat.get("serverLocations") or []] if known("serverLocations") else None,
        "website": langs("website"),
        "legal_notice": langs("legalNotice"),
        "free": yesno("freeOfCharge"),
        "professional_hosting": yesno("professionalHosting"),
        "green_hosting": yesno("ratingGreenWebCheck"),
        "bus_factor": bus if bus else None,
        "inband": yesno("inBandRegistration"),
        "registration_web": langs("registrationWebPage"),
        "captcha": yesno("inBandRegistrationCaptchaRequired"),
        "email_required": yesno("inBandRegistrationEmailAddressRequired"),
        "password_reset": langs("passwordReset"),
        "archive_days": num("maximumMessageArchiveManagementStorageTime"),
        "upload_file_mb": num("maximumHttpFileUploadFileSize"),
        "upload_total_mb": num("maximumHttpFileUploadTotalSize"),
        "upload_days": num("maximumHttpFileUploadStorageTime"),
        "compliance": num("ratingXmppComplianceTester"),
        "support_email": addresses(flat.get("emailSupport")),
        "support_chat": addresses(flat.get("chatSupport")),
        "support_groupchat": addresses(flat.get("groupChatSupport")),
        "alternative_jids": [j.lower() for j in flat.get("alternativeJids") or []],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="directory", help="read providers-D.json and providers.json from this folder")
    args = ap.parse_args()
    flat_list, full = (fetch(n, args.directory) for n in FILES)
    flat = {p["jid"].lower(): p for p in flat_list}
    full = {j.lower(): v for j, v in full.items()}
    missing = set(flat) - set(full)
    if missing:
        raise SystemExit(f"providers.json lacks {sorted(missing)}")

    recs = {r["domain"]: r for r in xdbdata.load_all()}
    added = changed = dropped = 0
    for jid in sorted(flat):
        provider = {k: v for k, v in block(flat[jid], full[jid]).items() if v not in (None, "", [], {})}
        rec = recs.get(jid)
        if rec is None:
            rec = {"domain": jid, "provider": provider, "sources": [SOURCE]}
            added += 1
        else:
            changed += rec.get("provider") != provider
            rec["provider"] = provider
            rec["sources"] = sorted(set(rec.get("sources") or []) | {SOURCE})
        xdbdata.save(rec)
    for domain, rec in recs.items():
        if domain not in flat and rec.get("provider"):
            rec.pop("provider")
            rec["sources"] = [s for s in rec.get("sources") or [] if s != SOURCE]
            xdbdata.save(rec)
            dropped += 1
    print(f"XMPP Providers: {len(flat)} providers, {added} new files, {changed} changed, {dropped} no longer listed")


if __name__ == "__main__":
    main()
