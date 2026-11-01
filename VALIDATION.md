# Validation & refresh report

Generated: **2026-11-01 08:48:04 UTC**

## Inputs

| file | rows | notes |
| --- | --- | --- |
| README.md (old) | 1521 | sorted by old probe time, 13 columns |
| xmpp_domain_list.txt (old) | 1141 | alphabetical |
| xmpp_ip.txt (old) | 1141 | domain + IP intel, 8 columns |

The three files were **different snapshots**: the old README and the two txt files shared only 140 domains. The refreshed database is the union of all three, deduplicated.

## Normalization & fixes

- merged unique names: **2520** domains + 2 non-domain entries
- duplicate lines inside a single file: none
- IP addresses found in the domain list were moved to the `ip_literal` status and are probed directly (`47.244.130.192`, `52.77.238.158`)
- old cross-file conflicts (`autistici.org`, `mailbox.bz`, `tigase.me`, `404.city`) are resolved: one record per domain, fresh DNS/intel used everywhere
- country names unified via the IP-intelligence provider (`Netherlands` vs `The Netherlands` etc.)
- ASN field kept in the original `AS<number> <name>` format

## Domain status

- alive: **2095**
- dead (NXDOMAIN/timeout, kept with empty fields): **425**
- IP literals: **2**

## XMPP checks

Definitions used in this database:
- **C2S** — a client stream was opened on the SRV target (`_xmpp-client._tcp`, fallback `:5222`) and stream features were returned
- **S2S** — a server stream was opened on the SRV target (`_xmpp-server._tcp`, fallback `:5269`)
- **InBand** — XEP-0077 in-band registration is advertised after STARTTLS (feature or positive `<iq type='result'>` on `jabber:iq:register`)
- no authentication or registration was attempted

Results: C2S true 1289 / false 808; S2S true 1428 / false 669; STARTTLS 1271; in-band 643.

Note: the old `InBand` column meant an actual registration probe and does not always match the new advertisement-based value (e.g. `disroot.org`, `xmpp.jp`).

## Old vs new probe results

Rows where the old README had a boolean value:

| column | old | new true | new false | new unknown |
| --- | --- | --- | --- | --- |
| c2s | true | 982 | 430 | 86 |
| c2s | false | 1 | 20 | 2 |
| s2s | true | 1113 | 214 | 72 |
| s2s | false | 4 | 97 | 16 |
| inband | true | 330 | 40 | 82 |
| inband | false | 114 | 499 | 456 |

Differences are expected: servers change, and the old in-band column was an attempt-based probe.

## Known limitations

- probe timeouts / rate limits can produce false negatives; the raw error is in the CSV `notes` column
- geo/ASN/PTR come from ip-api.com (free tier)
- C2S/S2S checks are reachability checks, not a full XMPP conformance test
- dead domains are intentionally kept with empty fields, so rows can be resurrected later

## Files

| file | content |
| --- | --- |
| `README.md` | human-readable table (13 columns) |
| `xmpp_domains.csv` | full data: status, SRV, TLS, SASL, PTR, errors, sources |
| `xmpp_domain_list.txt` | plain domain list |
| `xmpp_ip.txt` | domain + IP + geo/ASN/PTR |
| `tools/` | reproducible pipeline (build → dns → geo → probe → render) |