# Iowa grocery-chain discovery and map-link crawl

The owner requested expansion from Woodman’s to every supermarket chain in Iowa, retaining slow requests, robots compliance and Jev decisions. On 18 October CDT / 19 October UTC the owner explicitly selected **public branch pages gated by robots.txt**, including after reviewing retailers’ automated-access restrictions. This is operator authorization, not a claim of retailer permission. Media rights remain independent.

## Scope and coverage

`scripts/discover-iowa-grocers.py` scans the pinned published All The Places archive, without a hand-selected spider list. It accepts explicit US/Iowa grocery, superstore and warehouse source assertions; excludes fuel, pharmacies and convenience formats; retains native source IDs, attribution, raw source properties and banner distinctions. A full address ending in an explicit Iowa state/ZIP suffix can supply a missing region, with the exact source field retained as evidence. No location is inferred from a chain name, coordinates or URL.

The 2,756,702,590-byte archive is pinned to run `2026-10-10-13-32-41`, SHA256 `174b0a4836f88185d5c7fbe96228814da61141e65c2330b522644dc56d8665d7`. Its central directory has 5,641 members and 27,992,816,145 expanded bytes. Acquisition used the existing bounded, DNS/TLS-pinned bulk transport with a 3 GiB artifact ceiling, 50 GiB installation quota and 5 GiB free-space reserve. The artifact is on Unraid, not the workstation.

Scanning never extracts paths, caps total/member sizes, verifies parsed members through the ZIP reader and reports oversized/malformed scopes. Two foreign address files exceed the 2 GiB member ceiling; they are recorded as skipped scopes. No complete state census is claimed: upstream failures, missing format/identity fields, independent/cooperative/affiliated grocers and missing branch websites remain coverage gaps. Source banner candidates are not silently merged or promoted to a verified chain census.

An explicit partial Iowa import publishes through the existing staged catalog/fence/generation path. `complete=false` prevents absence/retirement assertions from a regional subset; native IDs and other states are preserved. A newer published source scope is not overwritten with an older archive. USDA foods and existing map records remain separate packs. These added scopes are a one-shot regional import; the API’s existing selected-spider schedule is unchanged.

## Crawl behavior

`scripts/run-iowa-crawl.py` supports multiple independently registered exact hosts, using the existing robots/frontier/transport, immutable map-link publication and durable Jev ledger. Its network-free plan validates every target against an actual current Iowa catalog branch, source website, spider and chain ID. Fixed source query URLs can be explicitly approved; query-link following and generated variants remain forbidden. Default behavior for existing crawlers is unchanged.

The first pass selects representative branch URLs across every source-backed Iowa banner for which an eligible distinct public branch URL exists. Missing URLs, homepages, ambiguous identities, robots/access/response blocks and model review outcomes remain explicit. A successful representative branch is not proof that every branch in that chain has a map. No out-of-state fallback fills missing Iowa coverage.

Each retailer request uses contact `hello@foldlab.app`, public-address DNS/TLS pinning, no redirects, 512 KiB HTML maximum and 30–45-second spacing or a stricter configured/robots delay. Requests are sequential, with the durable 50/day/host counter shared with earlier work. Robots are fetched/cached under existing policy and checked before branch HTML. One host block defers that host without retrying or preventing other reviewed hosts from running. Operator STOP/source pause/SIGTERM and two-hour deadline remain available; the source pauses on completion/stop. No recurring crawl schedule is installed.

Jev reviews fixed source-backed targets and visible page evidence, then classifies observed links by advertised purpose. Confidence stays >=0.8. It cannot grant access/media rights, invent URLs, merge store identities, infer map geometry, or alter food facts. Separate read-only worker credential, no images/Box questions, no keys in configuration/logs/responses. New campaign reservations are capped at $1/100 calls; the existing shared $5 cumulative ceiling and retained earlier reservations apply. No model/network retries.

Only public robots text and fixed branch HTML are acquired. Map/PDF/image bytes are not downloaded or rehosted. `discovered`, `ambiguous`, `not_found`, blocked and review outcomes must not be reported as verified usable indoor maps.

## Operations

Data/evidence directory: `/data/crawl-campaigns/iowa-20261019/` (host `/mnt/cache/appdata/bord-food-api/crawl-campaigns/iowa-20261019/`). It contains acquisition receipt, pinned source manifest/hash, normalized roster, discovery status, coverage and publication reports. The private Tower runbook records the separate Compose service, versioned code/config mounts, actual campaign ID, startup evidence and stop command. Production API/Bòrd images are not changed by an operator-worker update.

Offline checks and actual live results are recorded in the plan verification log. Mocked tests do not establish live crawl success, full census coverage, or media permissions.
