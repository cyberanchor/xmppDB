#!/usr/bin/env python3
"""Phase 4: active XMPP checks.

For every resolvable domain:
  * C2S  — connect (SRV _xmpp-client._tcp or :5222), open a client stream,
           record STARTTLS, SASL mechanisms and in-band registration (XEP-0077).
  * S2S  — connect (SRV _xmpp-server._tcp or :5269), open a server stream.
No authentication, no registration is performed: only feature discovery.
"""

import argparse
import concurrent.futures as cf
import json
import os
import re
import socket
import ssl
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(BASE, "tools", "work")

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 6.0
WORKERS = 64

C2S_HDR = ("<?xml version='1.0'?><stream:stream to='{d}' xmlns='jabber:client' "
           "xmlns:stream='http://etherx.jabber.org/streams' version='1.0'>")
S2S_HDR = ("<?xml version='1.0'?><stream:stream xmlns='jabber:server' "
           "xmlns:stream='http://etherx.jabber.org/streams' from='{d}' to='{d}' version='1.0'>")

STARTTLS = "<starttls xmlns='urn:ietf:params:xml:ns:xmpp-tls'/>"
REG_IQ = ("<iq type='get' id='reg1'><query xmlns='jabber:iq:register'/></iq>")

MECH_RE = re.compile(r"<mechanism>([^<]+)</mechanism>")
ERR_RE = re.compile(r"<stream:error>\s*<([a-zA-Z0-9:-]+)")


def read_until(sock, markers, timeout=READ_TIMEOUT, limit=262144):
    sock.settimeout(timeout)
    buf = b""
    while len(buf) < limit:
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            break
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if any(m in buf for m in markers):
            break
    return buf


def features_of(text):
    sasl = MECH_RE.findall(text)
    return {
        "starttls": "<starttls" in text,
        "required": "<required" in text,
        "sasl": sorted(set(sasl)),
        "register": "jabber:iq:register" in text,
    }


def connect_any(host, port):
    infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
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
    out = {"ok": False, "tls": False, "sasl": [], "register": False,
           "error": None, "version": None, "note": ""}
    try:
        s = connect_any(host, port)
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
        m = re.search(r"<stream:stream[^>]*version=['\"]([^'\"]+)", text)
        if m:
            out["version"] = m.group(1)
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
                    s = ctx.wrap_socket(s, server_hostname=None if _is_ip(host) else host)
                    out["tls"] = True
                    s.sendall(C2S_HDR.format(d=domain).encode())
                    resp = read_until(s, [b"</stream:features>", b"<stream:error>"])
                    text = resp.decode("utf-8", "replace")
                    feat = features_of(text)
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


def _is_ip(host):
    try:
        socket.inet_pton(socket.AF_INET, host)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return True
    except OSError:
        return False


def targets(domain, dns):
    v = dns.get(domain) or {}
    ips = v.get("a") or v.get("aaaa") or []
    c2s = v.get("srv_c2s")
    s2s = v.get("srv_s2s")
    if not ips and not c2s:
        return None, None
    c2s_t = (c2s["target"], c2s["port"]) if c2s else ((ips[0] if ips else None), 5222)
    s2s_t = (s2s["target"], s2s["port"]) if s2s else ((ips[0] if ips else None), 5269)
    if c2s_t[0] in (None, "."):
        c2s_t = None
    if s2s_t[0] in (None, "."):
        s2s_t = None
    return c2s_t, s2s_t


def work(rec, dns):
    d = rec["domain"]
    c2s_t, s2s_t = targets(d, dns)
    if c2s_t is None and s2s_t is None:
        return d, {"checked": False, "reason": "no-dns"}
    empty = {"ok": False, "error": "no-target", "note": ""}
    c2s = probe_c2s(d, *c2s_t) if c2s_t else dict(empty)
    s2s = probe_s2s(d, *s2s_t) if s2s_t else dict(empty)
    return d, {"checked": True, "c2s": c2s, "s2s": s2s}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()

    data = json.load(open(os.path.join(WORK, "domains.json"), encoding="utf-8"))
    dns = json.load(open(os.path.join(WORK, "dns.json"), encoding="utf-8"))
    recs = data["domains"] + data["non_domains"]
    if args.limit:
        recs = recs[:args.limit]

    t0 = time.time()
    res = {}
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, r, dns): r["domain"] for r in recs}
        for fut in cf.as_completed(futs):
            d, info = fut.result()
            res[d] = info
            done += 1
            if done % 100 == 0 or done == len(recs):
                print(f"  probe {done}/{len(recs)}  {time.time()-t0:.0f}s", flush=True)

    out_path = os.path.join(WORK, "xmpp.json")
    if args.limit:
        out_path = os.path.join(WORK, "xmpp_sample.json")
    json.dump(res, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    checked = [v for v in res.values() if v.get("checked")]
    c2s_ok = sum(1 for v in checked if v["c2s"]["ok"])
    s2s_ok = sum(1 for v in checked if v["s2s"]["ok"])
    tls_ok = sum(1 for v in checked if v["c2s"]["tls"])
    reg = sum(1 for v in checked if v["c2s"]["register"])
    print(f"checked={len(checked)} c2s={c2s_ok} s2s={s2s_ok} tls={tls_ok} inband={reg}")
    print(f"elapsed {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
