# Schema scope

These Draft 2020-12 JSON Schemas validate representative records, envelopes and planning policies. They intentionally allow additive domain extensions. They are not a substitute for the full implemented Pydantic contract. The validator checks real examples against both envelope and entity schemas and performs semantic cross-record checks separately.

Dates/URIs use JSON Schema formats; application validation must additionally check allowed hosts, date plausibility, civil-time interpretation, effective policy and source permissions. A valid URI is not authorization to fetch it. String IDs remain opaque. Financial observations use decimal strings, not binary floats.

`contracts/openapi.blueprint.json` embeds compatible schemas for portability. FastAPI-generated OpenAPI becomes authoritative after implementation and must be validated with the chosen full OpenAPI validator in CI. Package QA checks JSON Schema validity and internal reference/parameter consistency; it does not claim full implementation conformance.
