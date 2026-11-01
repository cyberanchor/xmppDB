#!/usr/bin/env python3
"""Check XMPP servers and write the results into data/servers/<domain>.yaml.

For every domain:
  DNS  A, AAAA, _xmpp-client._tcp and _xmpp-server._tcp SRV records (dig)
  IP   the address the checks use: the domain's A/AAAA record, else the address of its client SRV target.
       Country, ISP, organisation and AS from ip-api.com (batch API, free tier), PTR from dig -x
  C2S  a client stream to the client SRV target (fallback: port 5222): STARTTLS, the SASL mechanisms offered
       after TLS, and in-band registration (XEP-0077): the stream feature, or a registration form returned
       for a jabber:iq:register query
  S2S  a server stream to the server SRV target (fallback: port 5269)
No account is created and no login is attempted. The checks are the ones of the earlier pipeline's
tools/probe_xmpp.py (git history up to commit b934996), with the registration stream feature matched by its
namespace.

Only the check fields of a record are replaced; the XMPP Providers block is kept.

usage:
  python3 tools/collect.py --unchecked     servers without check results (for example new ones from
                                           tools/import_providers.py)
  python3 tools/collect.py --all           every server
  python3 tools/collect.py DOMAIN...       these servers; a domain without a file gets one
options: --workers N (default 64), --dry-run (print the results as JSON, write nothing)
"""
import argparse
import concurrent.futures as cf
import datetime
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xdbdata  # noqa: E402

CHECK_FIELDS = ["dead", "flag", "country", "alliance", "ip", "asn", "isp", "org", "ptr", "srv_client",
                "srv_server", "c2s", "s2s", "starttls", "registration", "sasl", "errors", "last_checked"]
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 6.0
GEO_URL = "http://ip-api.com/batch?fields=status,message,country,countryCode,isp,org,as,query"
GEO_BATCH = 100
GEO_PAUSE = 4.2  # the batch endpoint allows 15 requests a minute

C2S_HDR = ("<?xml version='1.0'?><stream:stream to='{d}' xmlns='jabber:client' "
           "xmlns:stream='http://etherx.jabber.org/streams' version='1.0'>")
S2S_HDR = ("<?xml version='1.0'?><stream:stream xmlns='jabber:server' "
           "xmlns:stream='http://etherx.jabber.org/streams' from='{d}' to='{d}' version='1.0'>")
STARTTLS = "<starttls xmlns='urn:ietf:params:xml:ns:xmpp-tls'/>"
REG_IQ = "<iq type='get' id='reg1'><query xmlns='jabber:iq:register'/></iq>"
IPV6_ONLY = "ipv6-only, not checked: the checking host has no IPv6"
MECH_RE = re.compile(r"<mechanism>([^<]+)</mechanism>")
ERR_RE = re.compile(r"<stream:error>\s*<([a-zA-Z0-9:-]+)")


# ------------------------------------------------------------------------------------------------------- DNS
def dig(name, rtype):
    """(status, answers): status is noerror / nxdomain / servfail / timeout, answers the RDATA fields of the
    records of that type (CNAMEs on the way are skipped)."""
    cmd = ["dig", "+time=3", "+tries=2", "+noall", "+comments", "+answer"]
    cmd += ["-x", name] if rtype == "PTR" else [name, rtype]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except subprocess.TimeoutExpired:
        return "timeout", []
    m = re.search(r"status: ([A-Z]+)", out)
    status = m.group(1).lower() if m else "timeout"
    answers = []
    for line in out.splitlines():
        parts = line.split()
        if line.startswith(";") or len(parts) < 5:
            continue
        if parts[3] == rtype:
            answers.append(parts[4:])
    return status, answers


def is_ip(s):
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def is_public(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast
                or a.is_unspecified)


def best_srv(answers):
    """The SRV record a client tries first: lowest priority, then highest weight. None when there is none."""
    recs = []
    for a in answers:
        try:
            recs.append((int(a[0]), -int(a[1]), int(a[2]), a[3].rstrip(".")))
        except (ValueError, IndexError):
            continue
    if not recs:
        return None
    prio, _, port, target = sorted(recs)[0]
    return {"target": target or ".", "port": port}


def check_dns(domain):
    if is_ip(domain):
        v6 = ":" in domain
        return {"a": [] if v6 else [domain], "aaaa": [domain] if v6 else [], "srv_c2s": None, "srv_s2s": None,
                "srv_ip": None, "error": None}
    st_a, a = dig(domain, "A")
    st_aaaa, aaaa = dig(domain, "AAAA")
    _, sc = dig(f"_xmpp-client._tcp.{domain}", "SRV")
    _, ss = dig(f"_xmpp-server._tcp.{domain}", "SRV")
    out = {"a": sorted({x[0] for x in a}), "aaaa": sorted({x[0] for x in aaaa}),
           "srv_c2s": best_srv(sc), "srv_s2s": best_srv(ss), "srv_ip": None, "error": None}
    if not out["a"] and not out["aaaa"]:
        for srv in (out["srv_c2s"], out["srv_s2s"]):
            if srv and srv["target"] != "." and not out["srv_ip"]:
                for rtype in ("A", "AAAA"):
                    _, ta = dig(srv["target"], rtype)
                    if ta:
                        out["srv_ip"] = ta[0][0]
                        break
        if st_a != "noerror":
            out["error"] = st_a
        elif st_aaaa != "noerror":
            out["error"] = st_aaaa
    return out


# ----------------------------------------------------------------------------------------------- XMPP streams
def read_until(sock, markers, timeout=READ_TIMEOUT, limit=262144):
    sock.settimeout(timeout)
    buf = b""
    while len(buf) < limit:
        try:
            chunk = sock.recv(8192)
        except (socket.timeout, OSError):
            break
        if not chunk:
            break
        buf += chunk
        if any(m in buf for m in markers):
            break
    return buf


def features_of(text):
    return {
        "starttls": "<starttls" in text,
        "sasl": sorted(set(MECH_RE.findall(text))),
        "register": "http://jabber.org/features/iq-register" in text,
    }


class IPv6Only(OSError):
    """The target has only IPv6 addresses and this host has no IPv6 route: nothing can be said about it."""


_HAS_IPV6 = []


def has_ipv6():
    if not _HAS_IPV6:
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s.connect(("2001:4860:4860::8888", 53))  # a UDP connect only picks a route, nothing is sent
            s.close()
            _HAS_IPV6.append(True)
        except OSError:
            _HAS_IPV6.append(False)
    return _HAS_IPV6[0]


def connect_any(host, port):
    """Connect to the first address of host that answers, IPv4 first. Without IPv6 on this host, IPv6
    addresses are skipped (their error would hide the IPv4 one); a target with only IPv6 raises IPv6Only."""
    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
    if not has_ipv6():
        infos = [i for i in infos if i[0] == socket.AF_INET]
        if not infos:
            raise IPv6Only("ipv6-only")
    last = None
    for fam, typ, proto, _, addr in infos:
        s = None
        try:
            s = socket.socket(fam, typ, proto)
            s.settimeout(CONNECT_TIMEOUT)
            s.connect(addr)
            return s
        except OSError as e:
            last = e
            if s is not None:
                s.close()
    raise last or OSError("no address")


def probe_c2s(domain, host, port):
    out = {"ok": False, "tls": False, "sasl": [], "register": False, "error": None, "note": ""}
    try:
        s = connect_any(host, port)
    except IPv6Only:
        out.update(ok=None, error=IPV6_ONLY)
        return out
    except socket.timeout:
        out["error"] = "connect-timeout"
        return out
    except OSError as e:
        out["error"] = "connect-error: " + (e.strerror or type(e).__name__)
        return out
    try:
        s.sendall(C2S_HDR.format(d=domain).encode())
        resp = read_until(s, [b"</stream:features>", b"<stream:error>", b"</stream:stream>"])
        text = resp.decode("utf-8", "replace")
        if not resp:
            out["error"] = "no-response"
            return out
        if "<stream:error>" in text:
            em = ERR_RE.search(text)
            out["error"] = "stream-error: " + (em.group(1) if em else "unknown")
            return out
        if "<stream:stream" not in text:
            out["error"] = "not-xmpp"
            return out
        out["ok"] = True
        feat = features_of(text)
        if feat["starttls"]:
            s.sendall(STARTTLS.encode())
            tls_resp = read_until(s, [b"<proceed", b"<failure"])
            if b"<proceed" in tls_resp:
                try:
                    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    s = ctx.wrap_socket(s, server_hostname=None if is_ip(host) else host)
                    out["tls"] = True
                    s.sendall(C2S_HDR.format(d=domain).encode())
                    resp = read_until(s, [b"</stream:features>", b"<stream:error>"])
                    feat = features_of(resp.decode("utf-8", "replace"))
                except (ssl.SSLError, OSError) as e:
                    out["note"] = "tls-failed:" + type(e).__name__
                    return out
            else:
                out["note"] = "starttls-refused"
        out["sasl"] = feat["sasl"]
        if feat["register"]:
            out["register"] = True
        elif out["tls"]:
            try:
                s.sendall(REG_IQ.encode())
                iq = read_until(s, [b"</iq>"]).decode("utf-8", "replace")
                if ("jabber:iq:register" in iq and "<iq type='error'" not in iq
                        and '<iq type="error"' not in iq and "<error" not in iq):
                    out["register"] = True
            except OSError:
                pass
    except OSError as e:
        out["error"] = "io-error: " + type(e).__name__
    finally:
        try:
            s.close()
        except OSError:
            pass
    return out


def probe_s2s(domain, host, port):
    out = {"ok": False, "error": None, "note": ""}
    try:
        s = connect_any(host, port)
    except IPv6Only:
        out.update(ok=None, error=IPV6_ONLY)
        return out
    except socket.timeout:
        out["error"] = "connect-timeout"
        return out
    except OSError as e:
        out["error"] = "connect-error: " + (e.strerror or type(e).__name__)
        return out
    try:
        s.sendall(S2S_HDR.format(d=domain).encode())
        resp = read_until(s, [b"</stream:features>", b"<stream:error>", b"</stream:stream>"])
        text = resp.decode("utf-8", "replace")
        if "<stream:stream" in text:
            out["ok"] = True
        if "<stream:error>" in text:
            em = ERR_RE.search(text)
            out["note"] = "stream-error: " + (em.group(1) if em else "unknown")
        elif not out["ok"]:
            out["error"] = "no-response" if not resp else "not-xmpp"
    except OSError as e:
        out["error"] = "io-error: " + type(e).__name__
    finally:
        try:
            s.close()
        except OSError:
            pass
    return out


def check(domain):
    """DNS and both streams of one domain: a dict for result()."""
    dns = check_dns(domain)
    ips = dns["a"] or dns["aaaa"]
    ip = (ips or [dns["srv_ip"]])[0]
    alive = bool(ips or dns["srv_c2s"] or dns["srv_s2s"] or dns["srv_ip"])
    out = {"domain": domain, "dns": dns, "ip": ip, "alive": alive, "c2s": None, "s2s": None, "ptr": ""}
    if not alive:
        return out
    c2s_t = (dns["srv_c2s"]["target"], dns["srv_c2s"]["port"]) if dns["srv_c2s"] else (ip, 5222)
    s2s_t = (dns["srv_s2s"]["target"], dns["srv_s2s"]["port"]) if dns["srv_s2s"] else (ip, 5269)
    none = {"ok": False, "error": "no-target", "note": ""}
    out["c2s"] = probe_c2s(domain, *c2s_t) if c2s_t[0] not in (None, ".") else dict(none, tls=False, sasl=[],
                                                                                   register=False)
    out["s2s"] = probe_s2s(domain, *s2s_t) if s2s_t[0] not in (None, ".") else dict(none)
    if ip and is_public(ip):
        _, ptr = dig(ip, "PTR")
        out["ptr"] = ptr[0][0].rstrip(".") if ptr else ""
    return out


# ----------------------------------------------------------------------------------------------------- geo
def geolocate(ips):
    geo = {}
    ips = sorted(set(ip for ip in ips if ip and is_public(ip)))
    for i in range(0, len(ips), GEO_BATCH):
        chunk = ips[i:i + GEO_BATCH]
        body = json.dumps([{"query": ip} for ip in chunk]).encode()
        for attempt in range(5):
            try:
                req = urllib.request.Request(GEO_URL, data=body, method="POST",
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    for item in json.loads(r.read().decode()):
                        if item.get("status") == "success":
                            geo[item["query"]] = item
                break
            except (urllib.error.URLError, OSError, ValueError) as e:
                wait = 15 * (attempt + 1)
                print(f"  ip-api.com: {e}, retry in {wait}s", file=sys.stderr, flush=True)
                time.sleep(wait)
        if i + GEO_BATCH < len(ips):
            time.sleep(GEO_PAUSE)
    return geo


# ------------------------------------------------------------------------------------------------- records
def fields(res, geo, today):
    """The check fields of a record from one result of check()."""
    dns, c2s, s2s = res["dns"], res["c2s"], res["s2s"]
    rec = {"last_checked": today}
    errors = []
    if dns["error"]:
        errors.append("dns:" + dns["error"])
    if not res["alive"]:
        rec["dead"] = True
        rec["errors"] = errors or ["dns:no-address"]  # the name exists but has no A, AAAA or SRV record
        return rec
    g = geo.get(res["ip"] or "", {})
    cc = (g.get("countryCode") or "").upper()
    rec.update({
        "flag": xdbdata.flag(cc), "country": g.get("country", ""), "alliance": xdbdata.EYES.get(cc),
        "ip": res["ip"] or "", "asn": g.get("as", ""), "isp": g.get("isp", ""), "org": g.get("org", ""),
        "ptr": res["ptr"],
        "srv_client": "{target}:{port}".format(**dns["srv_c2s"]) if dns["srv_c2s"] else "",
        "srv_server": "{target}:{port}".format(**dns["srv_s2s"]) if dns["srv_s2s"] else "",
        "c2s": c2s["ok"], "s2s": s2s["ok"],
    })
    if c2s["ok"]:
        rec["starttls"] = c2s["tls"]
        rec["registration"] = c2s["register"]
        rec["sasl"] = c2s["sasl"]
    for side, r in (("c2s", c2s), ("s2s", s2s)):
        for k in ("error", "note"):
            if r.get(k):
                errors.append(f"{side}:{r[k]}")
    rec["errors"] = errors
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("domains", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--unchecked", action="store_true")
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    recs = {r["domain"]: r for r in xdbdata.load_all()}
    if args.all:
        todo = sorted(recs)
    elif args.unchecked:
        todo = sorted(d for d, r in recs.items() if xdbdata.state(r) == "unchecked")
    else:
        todo = sorted({d.strip().lower().rstrip(".") for d in args.domains if d.strip()})
    if not todo:
        raise SystemExit("nothing to check (give domains, --unchecked or --all)")

    t0 = time.time()
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, res in enumerate(ex.map(check, todo), 1):
            results.append(res)
            if i % 100 == 0 or i == len(todo):
                print(f"  checked {i}/{len(todo)}  {time.time() - t0:.0f}s", file=sys.stderr, flush=True)
    geo = geolocate(r["ip"] for r in results if r["alive"])
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    if args.dry_run:
        print(json.dumps({r["domain"]: fields(r, geo, today) for r in results}, ensure_ascii=False, indent=1))
        return
    for res in results:
        old = recs.get(res["domain"], {"domain": res["domain"]})
        rec = {k: v for k, v in old.items() if k not in CHECK_FIELDS}
        rec.update(fields(res, geo, today))
        if res["domain"] not in recs:
            rec["sources"] = sorted(set(rec.get("sources") or []) | {"manual"})
        xdbdata.save(rec)
    online = sum(1 for r in results if r["c2s"] and r["c2s"]["ok"])
    dead = sum(1 for r in results if not r["alive"])
    print(f"{len(results)} servers checked: {online} accept clients, {dead} do not resolve "
          f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
