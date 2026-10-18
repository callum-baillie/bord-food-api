# Final adversarial implementation review

Review the actual implementation against `docs/00-SCOPE.md`, `docs/02-ARCHITECTURE.md`, `docs/05-INCREMENTAL-SYNC.md`, `docs/11-SECURITY-AND-RIGHTS.md` and all T01–T42 acceptance cases. Inspect code and run available offline tests; do not rely on implementation-status prose alone.

Prioritize: empty startup/no seed data; old USDA compatibility; generation-consistent reads; two-phase publication recovery; fencing; cursor advancement only after publication; delta gap/filtered-no-row handling; snapshot absence/closures; stable IDs and false merges; network kill switches at execution time; hostile redirects/files/maps; source licenses; unknown versus false/zero; local-only Bòrd mode and durable reviewed snapshots.

Find permanent stubs hidden behind optional-source flags. Separate legitimately unverified live access from unfinished required parser or scheduler code. Check that tests fail when the transport attempts source traffic. Do not run live source downloads, crawlers, paid calls, deploy or push.

Fix proven defects within scope with regression tests. Report severity, file/function, trigger, impact, change and test evidence. Check authoritative generated OpenAPI rather than merely this package’s planning blueprint. State what remains untested; never claim Docker/Unraid or companion success without direct evidence. Update tasks/evidence only where justified.
