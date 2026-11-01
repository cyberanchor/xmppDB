# Data pipeline

Reproducible generation of the XMPP domain database.

## Requirements

- Python 3.9+
- `dnspython` (installed in `tools/venv`)
- network access: DNS, `ip-api.com`, XMPP ports 5222/5269

```bash
python3 -m venv tools/venv
tools/venv/bin/pip install dnspython
```

## Phases

| # | script | output | what it does |
|---|--------|--------|--------------|
| 1 | `build_dataset.py` | `tools/work/domains.json` | merges README + both txt files, normalizes and deduplicates domains, validates syntax |
| 2 | `check_dns.py` | `tools/work/dns.json` | A/AAAA, `_xmpp-client._tcp` and `_xmpp-server._tcp` SRV, retries on SERVFAIL/timeout |
| 3 | `enrich_geo.py` | `tools/work/geo.json` | country, flag source, ISP, org, AS and PTR via ip-api.com (batched) |
| 4 | `probe_xmpp.py` | `tools/work/xmpp.json` | active C2S/S2S stream checks, STARTTLS, SASL mechanisms, XEP-0077 advertisement |
| 5 | `render.py` | `README.md`, `xmpp_domains.csv`, `xmpp_domain_list.txt`, `xmpp_ip.txt`, `VALIDATION.md` | renders all artifacts |
| 6 | `verify.py` | exit code | cross-checks README/CSV/txt, field validity, duplicates, flags, alliances |

## Full run

```bash
python3 tools/build_dataset.py
tools/venv/bin/python tools/check_dns.py
python3 tools/enrich_geo.py
python3 tools/probe_xmpp.py --workers 64
python3 tools/render.py
python3 tools/verify.py
```

Intermediate results are cached in `tools/work/` (git-ignored), so individual
phases can be re-run without repeating the network work.

## Probe definitions

- **C2S** — client stream opened on the SRV target (fallback `:5222`), stream
  features received.
- **S2S** — server stream opened on the SRV target (fallback `:5269`).
- **InBand** — XEP-0077 in-band registration advertised after STARTTLS
  (stream feature or positive `jabber:iq:register` IQ result).

No authentication or registration is performed; probes are reachability and
feature-discovery checks only.

## CSV schema

`domain, status, sources, c2s, s2s, inband, tls, sasl_mechs, ip, ip_source,
country_code, country, flag, isp, org, as, ptr, srv_c2s, srv_s2s, updated, notes`

- `status`: `alive`, `dead`, `ip_literal`
- `ip_source`: `dns` (A/AAAA of the domain) or `srv` (resolved SRV target)
- `notes`: DNS and probe errors, e.g. `dns:nxdomain`, `c2s:connect-timeout`,
  `s2s:stream-error:invalid-from`
