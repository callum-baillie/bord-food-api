-- Illustrative private build schema. Serve only an immutable published copy.
-- USDA legacy foods tables/payloads remain in their own compatible pack; do not overwrite them with this DDL.
PRAGMA foreign_keys = ON;
CREATE TABLE pack_metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL CHECK(json_valid(value_json)));
CREATE TABLE source_records (
  source_id TEXT NOT NULL, source_record_id TEXT NOT NULL, revision TEXT NOT NULL,
  content_hash TEXT NOT NULL, normalization_version TEXT NOT NULL,
  source_observed_at TEXT, source_published_at TEXT, retrieved_at TEXT NOT NULL,
  rights_policy_id TEXT NOT NULL, payload BLOB NOT NULL,
  PRIMARY KEY(source_id,source_record_id,revision)
);
CREATE TABLE entity_crosswalk (
  entity_id TEXT NOT NULL, source_id TEXT NOT NULL, source_record_id TEXT NOT NULL, revision TEXT NOT NULL,
  match_method TEXT NOT NULL, PRIMARY KEY(entity_id,source_id,source_record_id,revision),
  FOREIGN KEY(source_id,source_record_id,revision) REFERENCES source_records(source_id,source_record_id,revision)
);
CREATE TABLE chains (
  chain_id TEXT PRIMARY KEY, name TEXT NOT NULL, entity_kind TEXT NOT NULL,
  country_code TEXT NOT NULL, parent_organization_id TEXT, data_json TEXT NOT NULL CHECK(json_valid(data_json))
);
CREATE TABLE stores (
  row_id INTEGER PRIMARY KEY, store_id TEXT NOT NULL UNIQUE, chain_id TEXT REFERENCES chains(chain_id),
  display_name TEXT NOT NULL, country_code TEXT NOT NULL, region_code TEXT, city TEXT,
  latitude REAL CHECK(latitude BETWEEN -90 AND 90), longitude REAL CHECK(longitude BETWEEN -180 AND 180),
  lifecycle_status TEXT NOT NULL, eligible_grocery INTEGER NOT NULL CHECK(eligible_grocery IN (0,1)),
  data_json TEXT NOT NULL CHECK(json_valid(data_json)),
  CHECK((latitude IS NULL)=(longitude IS NULL))
);
CREATE INDEX stores_chain_region ON stores(chain_id,region_code,lifecycle_status);
CREATE VIRTUAL TABLE stores_spatial USING rtree(row_id,min_lon,max_lon,min_lat,max_lat);
CREATE VIRTUAL TABLE stores_fts USING fts5(display_name,city,region_code,content='stores',content_rowid='row_id');
CREATE TABLE products (
  row_id INTEGER PRIMARY KEY, product_id TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  brand TEXT NOT NULL DEFAULT '', data_json TEXT NOT NULL CHECK(json_valid(data_json))
);
CREATE VIRTUAL TABLE products_fts USING fts5(display_name,brand,content='products',content_rowid='row_id');
CREATE TABLE product_identifiers (
  product_id TEXT NOT NULL REFERENCES products(product_id), namespace TEXT NOT NULL, value TEXT NOT NULL,
  validation_status TEXT NOT NULL, PRIMARY KEY(product_id,namespace,value)
);
CREATE INDEX product_identifier_lookup ON product_identifiers(namespace,value,validation_status);
CREATE TABLE retailer_listings (
  listing_id TEXT PRIMARY KEY, chain_id TEXT NOT NULL, retailer_item_id TEXT NOT NULL,
  product_id TEXT, data_json TEXT NOT NULL CHECK(json_valid(data_json)), UNIQUE(chain_id,retailer_item_id)
);
CREATE TABLE retail_observations (
  observation_id TEXT PRIMARY KEY, store_id TEXT, listing_id TEXT, product_id TEXT,
  observation_kind TEXT NOT NULL CHECK(observation_kind IN ('assortment','price','availability','placement','banner_association')),
  channel TEXT NOT NULL, source_observed_at TEXT, retrieved_at TEXT NOT NULL,
  source_id TEXT NOT NULL, source_record_id TEXT NOT NULL, revision TEXT NOT NULL,
  data_json TEXT NOT NULL CHECK(json_valid(data_json))
);
CREATE INDEX observations_product_store ON retail_observations(product_id,store_id,observation_kind);
CREATE TABLE map_assets (
  map_id TEXT PRIMARY KEY, store_id TEXT NOT NULL, floor_label TEXT, version TEXT,
  discovery_status TEXT NOT NULL, rights_status TEXT NOT NULL, original_sha256 TEXT,
  data_json TEXT NOT NULL CHECK(json_valid(data_json))
);
CREATE TABLE food_measures (
  measure_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_record_id TEXT NOT NULL,
  revision TEXT NOT NULL, data_json TEXT NOT NULL CHECK(json_valid(data_json))
);
CREATE TABLE guidance (
  guidance_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, revision TEXT NOT NULL,
  data_json TEXT NOT NULL CHECK(json_valid(data_json))
);
-- Cross-pack references need generation-wide validation because SQLite FKs cannot enforce across separate files.
-- FTS/RTree indexes must be populated and verified by the private builder, never triggers writing serving files.
