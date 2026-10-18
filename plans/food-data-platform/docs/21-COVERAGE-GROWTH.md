# 21 — Grow beyond the initial retailer adapters

## Two bulk-selection profiles, one pipeline

The production example uses four previously identified ATP spiders as a manageable first bootstrap. This is **not** a claim to cover all U.S. supermarkets and is not a permanent limit. `configs/nationwide-discovery.example.json` shows the alternative published-archive mode, which discovers additional eligible U.S. grocery banners from ATP’s bulk outputs without running their crawlers or converting the 300-name research list into live inputs. [S02]

Implement both selection modes behind the same V1 ATP adapter. In `selected_spiders`, fetch only configured source outputs. In `published_archive_us_grocery`, resolve the official latest run manifest and acquire its published archive subject to configured resource budgets. Inspect archive members safely; stream supported GeoJSON features; select U.S. grocery/superstore/warehouse formats and reject fuel-only/pharmacy/convenience rows. Preserve each spider’s native scope and available run metadata. Unknown/ambiguous country, format or banner membership is withheld for review rather than silently treated as U.S. grocery.

The archive may contain worldwide, non-grocery data; local filtering cannot guarantee a small network download. Display manifest size, enforce preflight/decompression caps, and permit the operator to remain on selected outputs. Do not automatically jump from the pilot to a huge download just because a store is missing. Neither configuration is executed during coding.

## Automatic new-chain and new-store discovery

Within an enabled bulk scope, newly observed valid retailer/source IDs are staged automatically. Recognized existing banners use their persistent crosswalk; new banner identities are candidates until at least two eligible physical grocery stores and sufficient identity evidence are established. Count unique locations after source/department reconciliation. Ambiguous equal brand names or combined families remain distinct candidates until reviewed. Stable canonical IDs are allocated once, not derived again from a sorted rank.

A new source member in an already permitted ATP archive can be parsed under the dataset’s policy without enabling a new retailer web crawler. Its schema/category/identity results still pass validation. Its retailer website is untrusted data, not a new permitted fetch host. New direct-crawl hosts or proprietary feeds always require explicit approval.

## Differential subsequent runs

Check global run identity/size/validators first. Compare per-member artifact hashes and normalized per-source record hashes. If the publisher exposes only a full archive, transfer it when changed and explain that bandwidth cost; skip unchanged members’ expensive parsing where verified cached member hashes/config versions allow. Never imply ZIP central-directory access or HTTP range savings is guaranteed. All source scopes retain independent complete/failed/missing status.

A missing archive member, malformed member or absent eligible rows must not bulk-close a chain. Only a trustworthy complete comparable member/scope can advance source absence evidence. Scope/filter changes reset the relevant absence baseline and require reconciliation. A source that stopped publishing stays stale or unavailable until reviewed.

Use SNAP as an optional independent food-retailer supplement and Overture as a V1.1 gap-filling source, preserving known upstream overlap. There is no automatic claim of exhaustive national coverage. Report newly discovered banners, additional unique branches, withheld records and field completeness for each profile/run.

## Exit tests

Add synthetic multi-member archive fixtures: grocery and non-grocery, two-store new chain, singleton, duplicate pharmacy, another country, malformed member, unchanged member and a new eligible store. Verify no public source call or retailer crawl occurs in tests. A repeat import changes neither identities nor fact versions; a larger acquisition profile requires explicit effective configuration, not an accidental fallback.
