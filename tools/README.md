# Tools

Scripts that collect the server data and keep the files in sync. Python 3.9+ with PyYAML
(`dnf install python3-pyyaml`); the collector also needs `dig`. The data is `data/servers/<domain>.yaml`, one file
per server (fields: `data/README.md`); every script reads and writes it through `xdbdata.py`, so the files keep one
format. `XDB_DATA_DIR=/other/folder` points the scripts at a copy of the data.

| Script | What it does |
|---|---|
| `xdbdata.py` | Shared module: load / save the records in the canonical YAML format (quotes anything a YAML 1.2 parser would not read as text, refuses unknown fields and wrong types), the server status |
| `collect.py --unchecked \| --all \| DOMAIN...` | Checks servers and writes the check fields: DNS (A, AAAA, client and server SRV), the address's country, network and PTR (ip-api.com, `dig -x`), a client stream (STARTTLS, SASL mechanisms, in-band registration) and a server stream. No account is created, no login is attempted. A new domain gets a file. `--dry-run` prints the results instead |
| `import_providers.py [--from DIR]` | Downloads the [XMPP Providers](https://providers.xmpp.net/) list (`providers-D.json` and `providers.json`, CC0-1.0) and writes the `provider` block; listed servers that have no file yet get one (run `collect.py --unchecked` next) |
| `readme_tables.py [--check]` | Writes the "XMPP servers" table of `README.md` from the records and aligns every table |
| `lists.py [--check]` | Writes the plain lists in the repository root in the format of the first xmppDB files: `xmpp_domain_list.txt` (every domain) and `xmpp_ip.txt` (domain \| ip \| country code \| country \| isp \| org \| as \| ptr) |
| `test_data.py [--no-site]` | Checks every file (fields, types, file name, canonical format), the README table, the plain lists and the built site (`site/public/`: one page per server, `servers.json` equal to the records, the table rows). Run it after every change and after `site/build.sh` |

## What the collector checks

| Step | Checks |
|---|---|
| DNS | A and AAAA of the domain, `_xmpp-client._tcp` and `_xmpp-server._tcp` SRV (the record a client tries first). A domain without any of them is `dead` |
| Address | The domain's first A (else AAAA) record, else the address of the client SRV target. Country, ISP, organisation and AS from ip-api.com (batch API, 15 requests a minute), PTR with `dig -x` |
| C2S | Client stream to the client SRV target or port 5222; STARTTLS and a TLS handshake (certificates are not verified); the SASL mechanisms offered after TLS; in-band registration: the `http://jabber.org/features/iq-register` stream feature or a form returned for a `jabber:iq:register` query |
| S2S | Server stream to the server SRV target or port 5269 (a stream header is enough; most servers then close the stream with an error such as `undefined-condition`, kept in `errors`) |

The checks are the ones of the earlier pipeline (`tools/probe_xmpp.py`, in the git history up to commit b934996)
with two changes: the registration stream feature is matched by its namespace, and on a host without IPv6 the IPv6
addresses are skipped instead of hiding the IPv4 error (an IPv6-only server is reported as `ipv6-only, not
checked`). A server that blocks the checking host shows as offline.

## Refreshing everything

```bash
python3 tools/import_providers.py          # new XMPP Providers data
python3 tools/collect.py --all             # about 10 minutes for 2500 servers
python3 tools/readme_tables.py
python3 tools/lists.py
site/build.sh                              # needs Hugo extended 0.146+
python3 tools/test_data.py
```

then commit `data/`, `README.md`, the two lists and `site/public/`.

Before 2026-11-01 the repository was a README table plus `xmpp_domain_list.txt` and `xmpp_ip.txt`, built by
a pipeline of scripts (`build_dataset.py`, `check_dns.py`, `enrich_geo.py`, `probe_xmpp.py`, `render.py`,
`verify.py`); they are in the git history.
