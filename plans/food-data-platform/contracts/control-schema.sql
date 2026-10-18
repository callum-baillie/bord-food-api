-- Illustrative relational design, not a migration to run against an existing deployment.
-- The complete implemented migrations must preserve all legacy data. No seed rows here.
PRAGMA foreign_keys = ON;
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL, checksum TEXT NOT NULL);
CREATE TABLE identities (
  entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL,
  created_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('reserved','active','alias','retired'))
);
CREATE TABLE source_aliases (
  source_id TEXT NOT NULL, namespace TEXT NOT NULL, external_id TEXT NOT NULL,
  entity_id TEXT NOT NULL REFERENCES identities(entity_id), valid_from TEXT NOT NULL, valid_until TEXT,
  decision_id TEXT, PRIMARY KEY(source_id,namespace,external_id,valid_from)
);
CREATE UNIQUE INDEX alias_current ON source_aliases(source_id,namespace,external_id) WHERE valid_until IS NULL;
CREATE TABLE identity_decisions (
  decision_id TEXT PRIMARY KEY, decision_kind TEXT NOT NULL,
  input_json TEXT NOT NULL CHECK(json_valid(input_json)), result_json TEXT NOT NULL CHECK(json_valid(result_json)),
  actor TEXT NOT NULL, decided_at TEXT NOT NULL, reverses_decision_id TEXT REFERENCES identity_decisions(decision_id)
);
CREATE TABLE source_policies (
  source_id TEXT NOT NULL, policy_version TEXT NOT NULL, config_json TEXT NOT NULL CHECK(json_valid(config_json)),
  reviewed_at TEXT, status TEXT NOT NULL, PRIMARY KEY(source_id,policy_version)
);
CREATE TABLE source_scopes (
  source_id TEXT NOT NULL, scope_key TEXT NOT NULL, committed_release_id TEXT, committed_cursor_json TEXT,
  committed_generation_id TEXT, last_success_at TEXT, source_observed_at TEXT,
  next_check_at TEXT, failure_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(source_id,scope_key), CHECK(committed_cursor_json IS NULL OR json_valid(committed_cursor_json))
);
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY, source_id TEXT, scope_key TEXT NOT NULL, kind TEXT NOT NULL,
  dedupe_key TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('queued','leased','running','validating','publishing','retry','prepared','succeeded','failed','cancelled','paused')),
  not_before TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5,
  lease_owner TEXT, lease_until TEXT, fence_token INTEGER NOT NULL DEFAULT 0,
  requested_policy_version TEXT NOT NULL, checkpoint_json TEXT, last_error_code TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  CHECK(checkpoint_json IS NULL OR json_valid(checkpoint_json))
);
CREATE UNIQUE INDEX job_active_dedupe ON jobs(dedupe_key) WHERE status IN ('queued','leased','running','validating','publishing','retry','prepared','paused');
CREATE INDEX job_dispatch ON jobs(status,not_before);
CREATE TABLE generation_publications (
  generation_id TEXT PRIMARY KEY, prior_generation_id TEXT, job_id TEXT NOT NULL REFERENCES jobs(job_id),
  state TEXT NOT NULL CHECK(state IN ('prepared','visible','committed','abandoned','rolled_back')),
  fence_token INTEGER NOT NULL, manifest_path TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
  prepared_at TEXT NOT NULL, visible_at TEXT, committed_at TEXT,
  pending_checkpoints_json TEXT NOT NULL CHECK(json_valid(pending_checkpoints_json))
);
CREATE TABLE source_artifacts (
  artifact_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, scope_key TEXT NOT NULL,
  release_id TEXT, resolved_url TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
  etag TEXT, last_modified TEXT, retrieved_at TEXT NOT NULL, source_published_at TEXT,
  object_path TEXT NOT NULL, validation_status TEXT NOT NULL, policy_version TEXT NOT NULL
);
CREATE TABLE entity_field_state (
  entity_id TEXT NOT NULL REFERENCES identities(entity_id), source_id TEXT NOT NULL, field_group TEXT NOT NULL,
  committed_hash TEXT, hash_version TEXT NOT NULL, last_verified_at TEXT, last_checked_at TEXT,
  next_audit_at TEXT, consecutive_valid_absences INTEGER NOT NULL DEFAULT 0, first_absent_at TEXT,
  PRIMARY KEY(entity_id,source_id,field_group)
);
CREATE TABLE change_outbox (
  event_id TEXT PRIMARY KEY, generation_id TEXT NOT NULL REFERENCES generation_publications(generation_id),
  entity_id TEXT NOT NULL, event_json TEXT NOT NULL CHECK(json_valid(event_json)),
  published_at TEXT, sequence_no INTEGER UNIQUE
);
CREATE TABLE crawl_frontier (
  frontier_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, canonical_url TEXT NOT NULL,
  entity_id TEXT, field_groups_json TEXT NOT NULL CHECK(json_valid(field_groups_json)),
  state TEXT NOT NULL, next_fetch_at TEXT, negative_count INTEGER NOT NULL DEFAULT 0,
  etag TEXT, last_modified TEXT, policy_version TEXT NOT NULL,
  UNIQUE(source_id,canonical_url)
);
CREATE TABLE host_budgets (
  host TEXT NOT NULL, window_start TEXT NOT NULL, requests_used INTEGER NOT NULL DEFAULT 0,
  bytes_used INTEGER NOT NULL DEFAULT 0, next_allowed_at TEXT, PRIMARY KEY(host,window_start)
);
-- Workers also require a tested single-publisher process lock / lease protocol, not DDL alone.
