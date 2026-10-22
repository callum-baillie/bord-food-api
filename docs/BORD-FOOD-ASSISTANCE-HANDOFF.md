# Bòrd food-assistance companion handoff

The food API implements authenticated `/v1/food-assistance/sites`, `/services`, `/events`
and detail routes. See [operating guide](FOOD-ASSISTANCE.md) and the generated
[OpenAPI contract](../contracts/openapi.json) for exact query and response shapes.

Bòrd integration has not been implemented in this work. Add a separate food-assistance
finder; this directory is unrelated to household pantry contents or supermarket counts.
Use the server's existing API credentials; never expose keys in the client.

- Request `dataset=osm` explicitly for ODbL records and show OpenStreetMap attribution.
  `dataset=directory` is a separate pack; do not silently combine or relabel licenses.
- Treat 503 `CATALOG_NOT_READY` as a dataset not yet published, rather than no nearby help.
- Display source, verification date, stale/unknown status and confirmation guidance.
  Facility office hours do not establish grocery distribution hours or walk-in access.
- Keep facilities, services and dated distribution events distinct. Do not invent recurring
  events or current food stock. Mobile schedules may change or be cancelled.
- Preserve source IDs and provenance when linking details; use the provided bounded cursors.
  Query nearby coordinates/radius or state/ZIP and service type as appropriate.

211 access, restricted directory partnerships, operator corrections/moderation, reminders,
household ingredient matching and meal planning remain separate companion or future work.
No household schema migration, Bòrd deployment, user messages or partnership signup was
performed for food assistance.
