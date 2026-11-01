# Server data

One YAML file per XMPP server: [`servers/<domain>.yaml`](servers/). The site, the downloads and the README table
are built from these files.

Downloads built from the same files: [servers.csv](https://cyberanchor.github.io/xmppDB/site/public/servers.csv)
(one row per server) and [servers.json](https://cyberanchor.github.io/xmppDB/site/public/servers.json) (the
records as they are here).

## Fields

Only `domain` is required. Empty and unknown values are left out; `false` means the check ran and the answer was no.

| Field | Example | Meaning |
|---|---|---|
| `domain` | `conversations.im` | The server's domain (the part after `@` in an address); the file is named after it |
| `dead` | `true` | The domain does not resolve (NXDOMAIN, SERVFAIL, DNS timeout, no address). The record is kept so the server can come back |
| `flag`, `country` | `🇩🇪`, `Germany` | Country of the server's address (IP geolocation) |
| `alliance` | `5`, `9`, `14` | Five / Nine / Fourteen Eyes membership of that country |
| `ip` | `'78.47.177.120'` | The address the checks connected to: the domain's A/AAAA record, else the address of its client SRV target |
| `asn`, `isp`, `org` | `AS24940 Hetzner Online GmbH` | Network (autonomous system), provider and organisation of the address |
| `ptr` | `xmpp.example.org` | Reverse DNS name of the address |
| `srv_client`, `srv_server` | `xmpp.conversations.im:5222` | First `_xmpp-client._tcp` and `_xmpp-server._tcp` SRV record |
| `c2s` | `true` | A client stream opened on the client SRV target, or on port 5222 |
| `s2s` | `true` | A server stream opened on the server SRV target, or on port 5269 |
| `starttls` | `true` | STARTTLS offered and the TLS handshake worked |
| `registration` | `true` | In-band registration (XEP-0077) advertised after STARTTLS: the stream feature, or a registration form returned for `jabber:iq:register`. The server may still ask for a CAPTCHA or limit sign-ups |
| `sasl` | `[PLAIN, SCRAM-SHA-1, SCRAM-SHA-1-PLUS]` | SASL mechanisms offered after STARTTLS |
| `errors` | `['c2s:connect-timeout']` | What failed in the last check: `dns:`, `c2s:` or `s2s:` and the error. `ipv6-only, not checked` means the checking host has no IPv6 |
| `provider` | | The server's entry in [XMPP Providers](https://providers.xmpp.net/) (below); only for listed servers |
| `sources` | `[list, xmpp-providers]` | Where the domain came from: `list` the domain list this repository started with (2025), `xmpp-providers` the XMPP Providers list, `manual` added by hand |
| `last_checked` | `'2026-11-01'` | Date of the last check |

The status shown on the site and in the README follows from these fields: **online** (`c2s: true`), **federation
only** (`s2s: true` without `c2s`), **offline** (checked, neither stream opened), **gone** (`dead: true`) and **not
checked** (no stream result, for example an IPv6-only server).

### `provider`

Copied from the XMPP Providers list (`https://data.xmpp.net/providers/v2/providers.json`, CC0-1.0) by
`tools/import_providers.py`. Values the list has no source for ("unknown" on providers.xmpp.net) are left out.

| Field | Example | Meaning |
|---|---|---|
| `category` | `A` | A and B are recommended for sign-up, C is average, D is any listed provider |
| `since` | `'2013-11-17'` | Date the service started |
| `updated` | `'2026-10-29'` | Last change of the entry |
| `organization` | `private person` | Who runs it: private person, commercial person, company, non-governmental, governmental |
| `software` | `Prosody 13.0.7` | Server software and version |
| `locations` | `[de]` | Countries of the servers and data, as stated by the provider |
| `website`, `legal_notice`, `registration_web`, `password_reset` | `{en: https://…}` | Pages by language |
| `free`, `professional_hosting`, `green_hosting` | `true` | Free of charge; hosted professionally; hosted on green energy (Green Web check) |
| `bus_factor` | `3` | People who can keep the service running |
| `inband`, `captcha`, `email_required` | `true` | In-band registration; a CAPTCHA or an e-mail address is needed for it |
| `archive_days`, `upload_days` | `30` | How long messages and uploaded files are kept; `0` unlimited |
| `upload_file_mb`, `upload_total_mb` | `100` | Upload limits per file and in total; `0` unlimited |
| `compliance` | `100` | Result of the [XMPP Compliance Tester](https://compliance.conversations.im/) in percent |
| `support_email`, `support_chat`, `support_groupchat` | `[admin@example.org]` | Support addresses |
| `alternative_jids` | `[example.net]` | Other domains of the same service |

Dates are quoted so that YAML keeps them as text; so are addresses and anything else that starts with a digit.

## Adding or changing a server

Add a domain with `python3 tools/collect.py example.org` (it creates the file and checks the server), or edit a
file by hand in the format of the others, then run `python3 tools/test_data.py --no-site` and open a pull request.
The site build stops with a message when a file is broken (an unknown field, a file name that does not match the
domain).
