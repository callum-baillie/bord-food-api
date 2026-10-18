# Proposed configuration deployment

Configuration filenames are examples, not supported by the current unmodified application. The implementation must add and document `BORD_FOOD_CONFIG`, role commands and config precedence. Copy the chosen policy to an operator-owned `production.json` only after implementation; examples are not silently applied.

`DATA_DIR`, `IMPORT_DIR`, `PORT`, `API_KEY`, `DATASETS` and explicitly set `AUTO_DOWNLOAD=false` retain their current purpose/compatibility. New source controls do not overload DATASETS, which remains USDA-only. Secrets come from environment or protected mounted secret references, never JSON in Git. A configured source descriptor does not store a chain or store record.

For local/CI implementation use development-offline policy and a temporary data root. Runtime production defaults select bulk-only automatic core acquisition; production deployment itself is a later authorized operation. A single-container Unraid setup uses the implemented `run` supervisor to manage API and worker and forward shutdown signals; do not launch an unmanaged background process in a shell command. The default Compose topology runs separate roles from the same image.

Worker health should use a separate tested heartbeat command/monitor in the implementation. The planning Compose disables the inherited HTTP healthcheck for the worker because it has no HTTP listener; this is not a claim of worker health. Apply resource limits suited to the actual Docker/Compose version and measured host, not an assumed compatibility of every optional Compose limit field.
