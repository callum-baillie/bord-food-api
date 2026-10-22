# Results — 20 October 2026

The API field support and retained evidence publication are live on Unraid. The updated local
viewer runs at http://localhost:4173/#dashboard. New crawler code is staged and passed an offline
serving-image preflight; no new crawl or paid enrichment was started.

## Published data

Generation `g_1d4fbfdf7a5644d1aee9c5ccdef23faf` contains 9,309 stores, 34 chains, 108 maps,
469,046 original USDA foods, 455,458 USDA branded product projections and 49 official Cold Food
Storage Chart guidance records. Store/chain IDs, chain payloads, original store source records/
references and USDA/maps objects were directly compared and preserved. The legacy apple FDC
response bytes remain identical.

| Iowa field | Presence before → after | Currently corroborated |
| --- | ---: | ---: |
| Phone | 287 → 287 | 103 |
| Website | 331 → 331 | 17 |
| Normalized weekly schedule | 0 → 10 | 10 |
| Raw hours | 357 → 357 | Separate from normalized verification |
| IANA timezone | 0 → 735 | Derived, not verified |
| Email, dated holiday exceptions, pickup/delivery links, departments, entrances, accessibility, reviewed aisle mappings | Insufficient evidence for accepted values | 0 |

There are 61 field conflicts across 46 Iowa stores, plus 621 SNAP and 277 OSM evidence links.
Unknown operating status remains unknown; no store was declared permanently closed from absence
or a failed crawl. The 735 Iowa records are a reconciled catalog, not a proven complete census.
All-store timezones derived: 6,257. A local retained-data replay changed zero stores.

Products and Storage guidance now browse successfully. The products pack is 3,696,787,456 bytes;
guidance is 184,320 bytes; enriched stores are 86,790,144 bytes. The guidance source is explicitly
**not full FoodKeeper**: the official FoodKeeper JSON still returns HTTP 403. A separately
attributed official chart supplies 49 complete rows with original ranges/conditions and source
review date 2023-09-19. No exact expiry is calculated.

## Running and staged work

The owner-selected US-labelled OFF import runs separately from the retained 13,179,356,850-byte
export, with networking disabled and exact SHA/size validation. At the final captured runtime
checkpoint, 93,000 selected products had been staged; this is not the final count or publication.
Status: `/data/operator-imports/us-off-snapshot-20261020-r2/status.json`, container
`bord-food-off-us-snapshot-20261020-r2`. No baseline extraction boundary is proven, so delta
alignment/freshness remain unverified and automatic OFF acquisition remains disabled.

API uses the existing pinned base image with five versioned read-only module overrides. The final
API start is 2026-10-20T16:43:01.407058813Z. Bòrd and history retained their exact earlier starts,
with all three services running/healthy, zero restarts/OOM. No Git push or image publication.
The crawler release is staged at
`config/crawl-field-releases/95d704cf3849ab4a6428880becd58cd6173ac391426b879ab2de41a2c6f155e0/`.
Existing state configurations, robots/pacing limits, holds and spending gates were preserved.
Overture/Foursquare extract adapters are ready but real acquisition is not activated.

Retained Open Prices analysis found zero exact Iowa OSM branch matches among 368 US locations /
42,822 observations. SNAP/USDA do not supply store SKU inventories. Retail API options are
[documented separately](../../RETAIL-DATA-DISCOVERY.md); no connectors implemented.
Read-only companion code inspection confirmed that its catalog schema passes through optional
fields and its projection still prefers the preserved raw hours string. The companion currently
projects only its existing store display fields; the new contact/timezone/provenance fields are
visible in the viewer and need a separate Bòrd UI update to be exposed there. No companion code,
end-to-end test or deployment was performed by this work.

## Verification and execution evidence

- API: **344 tests passed**, one upstream Starlette deprecation warning, 11.43 seconds.
- Ruff check/159-file format, generated OpenAPI comparison and whitespace checks passed.
- Plan package: 13 check groups / 93 checksums passed using system Python with jsonschema.
- Viewer: **6 Node + 8 Python tests**, build/format/Ruff and **13 browser tests / 11.1 seconds** passed.
- Live browser read check passed product search/retail evidence, all 49 storage rows, three map
  scopes, mobile controls/overflow, existing USDA/reference/Jev/history views; no browser errors.
- Actual-image network-disabled core/crawler preflights passed. Dashboard concept and current live
  desktop/mobile captures were inspected together; product/guidance drawers inspected too.
- Tower validator passed with existing historical archive/generated-output findings. The audit's
  unreachable VM leg remained incomplete; its partial inventory was isolated, canonical preserved.
- No new source download, retailer crawl or paid request. Jev remains 347 answered / $3.47 reserved,
  not billed spend. Full inventory capture and other-state activation remain off.

Failed/stopped attempts are recorded in status files: slow first projection stopped; second
projection OOM before publication; third published USDA/guidance before an intentional OFF stop
for field priority; busy-lock launches exited safely. Identity batching/streamed snapshot checks
resolved bulk import issues. Immutable validation now caches only exact inode/size/mtime/ctime
signatures and revalidates changed files; first/forced validation still hashes and checks SQLite.
A receipt scope/outcome key collision was fixed and regression-tested; original live receipt
preserved before correcting successful-publication metadata. TWR-053 was recorded in Tower;
Forgejo issue creation returned HTTP 502.

See [live-verification.json](live-verification.json), [final-runtime-check.json](final-runtime-check.json),
[live-field-publication.json](live-field-publication.json), [crawler-staging.json](crawler-staging.json)
and the sibling viewer's `docs/live-enrichment-check.json` for point-in-time evidence.
