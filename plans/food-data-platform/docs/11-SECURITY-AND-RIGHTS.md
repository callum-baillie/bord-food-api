# 11 — Security, privacy, rights and network policy

## Trust boundaries

Downloaded records, HTML, JSON-LD, sitemaps, PDFs, images, filenames, source links and contributed text are untrusted data. They cannot change configuration, execute code, instruct an LLM or cause an arbitrary fetch. The Bòrd server URL is trusted operator configuration; crawler targets are a different, tightly controlled input class.

## Central outbound network guard

Route every acquisition path through a reviewed transport/policy boundary, including optional Scrapy requests, redirect handlers, image fetches and conditional requests. Require HTTPS, valid certificates, exact approved origins and public resolved IPs; reject loopback, private/link-local, multicast, metadata-service endpoints, credentials in URLs and unsafe ports. Validate every redirect and defend against DNS rebinding/TOCTOU at connection time. Reject userinfo, malformed IDNs, embedded alternate IP encodings and proxy env escape paths. Package/network egress used by a developer shell is not an authorization for runtime adapters.

Trusted bulk CDNs may require multiple origins. Add each documented delivery origin to an explicit source policy with expiry/review; do not permit arbitrary `*.amazonaws.com`, `*.cloudfront.net`, `*.githubusercontent.com` or every redirect just because the first URL was trusted. If a legitimate large-file host changes, mark `network_policy_review_required`; do not turn off SSRF checks.

No auth secrets or cookies are sent across origins. No public GET endpoint proxies arbitrary URLs. Import CLI local paths must remain under allowed directories and reject symlink escapes. Do not expose a remote arbitrary-file import endpoint in V1.

## Source policy actions are distinct

For each source record: `can_fetch`, `can_store_raw`, `can_store_normalized`, `can_display`, `can_rehost_media`, `can_redistribute`, permitted retention, attribution and actual review evidence. Values are allow/deny/review_required, not one `licensed=true` boolean. Approved collection is not permission to rehost maps. A paid API response is not open data.

All The Places output license, source retailer content, scraper code and map assets have separate rights. OFF/OSM/Open Prices licensing is not removed by placing their records in different database files. Do not assert that partitioning automatically avoids derivative-database obligations; it supports audit/removal. Before public redistribution or a hosted public service, review combined-database and attribution obligations against the actual terms. The plan provides engineering controls, not a legal opinion. [S02, S05, S07, S10]

## Raw and normalized retention

Retain sufficient permitted manifests, hashes, source versions and extraction provenance to explain an import. Do not retain unnecessary contributor handles or receipt identity/payment details. Some licensed live data may need immediate or short-term expiry and must be excluded from general backups. Content hashes may themselves be useful provenance even after permitted payload deletion, subject to policy.

Public bulk facts and private household data never share an automatic export path. Bòrd private receipts/purchases/notes remain in Bòrd; no anonymous “help improve data” upload without a separate explicit consent and redaction design.

## Untrusted archives and documents

Stream compressed data with both compressed/expanded byte, row, nesting, member-count and wall-time bounds. Reject unsafe archive paths, device names, symlinks and zip bombs. XML parsers disable external entities/DTD. JSON parsing rejects nonfinite numeric values where unsupported. Reject active/malformed document content; isolate rendering with no network, no secrets, a read-only base and disposable writable directory. Prefer raster previews of untrusted SVG. Store normalized assets by content hash and emit correct media types/CSP/content disposition.

## Authentication and operations

Retain `X-Api-Key` read compatibility. Source configuration, job retries that cause network work, identity merges, deletion and activation are operator CLI actions in V1. Keep API read keys separate from optional admin/maintenance authority. Do not invent an unauthenticated dashboard that can turn crawling on.

Readiness/status must be sanitized: no raw searches, exact private preferences, response bodies, credentials, full request URLs with query tokens, local filesystem paths or account identifiers. Structured logs contain source/operation/status, byte/count/duration metrics and safe reason codes. Disable HTTP access logs that would record barcodes/search text or apply explicit redaction.

## Dependency and supply-chain policy

Pin new parser/crawler libraries and optional extras; inspect license/security impact. Do not download/execute changing GitHub scripts or install dependencies at production container startup. Upstream spider files and model assets are versioned build inputs, not runtime executable updates. Version source parser/config separately so replay is auditable.

## Hard budgets

Default commercial spend is zero. Enabling a paid source requires actual tariff/billing unit, account entitlement, per-request/source/day/month limits and a kill switch. HTTP attempts/retries count. Prevent a job from creating a Cartesian product of store × SKU × date. Real national stock data is not guaranteed by any open directory source.

## Fail closed without erasing useful data

On access refusal, policy changes, expired credentials, invalid data or missing rights: stop the affected acquisition, keep lawful last-good catalog data under its retention policy, expose degraded status, and preserve other packs. Do not bypass restrictions to satisfy a completion checklist.
