# Contract status

All contracts are implementation blueprints, not installed software. SQL scripts are empty-schema design references and are never auto-applied by this package. Do not run them against `/data/foods.sqlite` or Bòrd. Implement versioned migrations after inspecting the actual checkout.

The catalog DDL includes representative stores/products/evidence in one design file; production can split logical packs while retaining required generation-wide foreign-key checks. Only write unpublished private builds. FTS/RTree contents and normalized JSON need application validation beyond SQLite column checks.

The OpenAPI blueprint supplies path/parameter/request/response shapes and local references. Generate the authoritative specification from implemented FastAPI models and validate with a full OpenAPI checker in CI; preserve intentional legacy response differences. The package validator checks structure/reference integrity, not implemented route behavior.
