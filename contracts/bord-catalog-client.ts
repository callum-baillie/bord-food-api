/** Server-only Bòrd handoff. Import from a server module, never a browser bundle.
 * Reviewed against FastAPI contracts; regenerate openapi.json for full shapes.
 */
export type SourceRef = {
  source_id: string;
  record_id: string;
  release_id?: string;
  parser_version?: string;
};
export type CatalogRecord = {
  id: string;
  content_revision: string;
  source_refs: SourceRef[];
  [field: string]: unknown;
};
export type Envelope<T> = {
  schema_version: '1.0.0';
  data: T;
  meta: {
    catalog_generation: string | null;
    source_refs: SourceRef[];
    warnings: { code: string; message: string; [key: string]: unknown }[];
    next_cursor: string | null;
  };
};
export type SourceFoodRecord = {
  content_revision: string;
  source_id: string;
  record_id?: string;
  data?: Record<string, unknown>;
  measures: Record<string, unknown>[];
  source_refs?: SourceRef[];
  [field: string]: unknown;
};
export type CatalogReference = {
  transport_id: 'bord_food_api';
  source_id: 'usda_fdc' | 'open_food_facts';
  source_record_id: string;
  source_revision: string;
  catalog_generation: string;
  canonical_product_id: string | null;
};
export type Identifier = {
  namespace: 'gtin' | 'retailer_sku' | 'plu';
  value: string;
  chain_id?: string | null;
};
export type ResolveResult = {
  identifier: Identifier;
  status: 'exact' | 'candidates' | 'invalid' | 'not_found';
  candidates: CatalogRecord[];
};
export type RetailEvidence = {
  product_id: string;
  store_id: string | null;
  assortment_status: 'unknown' | 'source_reported' | 'listed' | 'historical_only';
  availability: 'unknown' | 'available' | 'unavailable' | 'limited';
  offers: Record<string, unknown>[];
  placements: Record<string, unknown>[];
  chain_evidence: Record<string, unknown>[];
  capabilities: Record<string, boolean>;
  reason: string | null;
  history_truncated?: boolean;
};
export class CatalogError extends Error {
  constructor(public status: number, public code: string, public retryable: boolean) {
    super(`Catalog request failed: ${code}`);
  }
}
export class BordCatalogClient {
  private readonly base: URL;
  constructor(baseUrl: string, private readonly key: string,
              private readonly transport: typeof fetch = fetch) {
    this.base = new URL(baseUrl);
    if (!['http:', 'https:'].includes(this.base.protocol) || this.base.username || this.base.password) {
      throw new Error('Invalid catalog endpoint');
    }
  }
  private async request<T>(path: string, body?: unknown): Promise<Envelope<T>> {
    // Fixed relative API paths only: no source URLs or arbitrary image proxying.
    const url = new URL(path, this.base);
    const response = await this.transport(url, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-Api-Key': this.key, ...(body === undefined ? {} : {'Content-Type': 'application/json'}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(5000), redirect: 'error', cache: 'no-store',
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new CatalogError(response.status, payload.error?.code ?? 'UNAVAILABLE',
                             payload.error?.retryable ?? false);
    }
    if (payload.schema_version !== '1.0.0') throw new Error('Unsupported catalog contract');
    return payload as Envelope<T>;
  }
  status() { return this.request<Record<string, unknown>>('/v1/system/status'); }
  capabilities() { return this.request<Record<string, unknown>>('/v1/capabilities'); }
  generation() { return this.request<Record<string, unknown>>('/v1/catalog/generations/current'); }
  stores(params = new URLSearchParams()) {
    return this.request<CatalogRecord[]>(`/v1/stores?${params}`);
  }
  store(id: string) { return this.request<CatalogRecord>(`/v1/stores/${encodeURIComponent(id)}`); }
  sourceFood(source: 'usda_fdc' | 'open_food_facts', record: string, revision?: string) {
    const params = new URLSearchParams(revision ? {revision} : {});
    return this.request<SourceFoodRecord>(`/v1/foods/${source}/${encodeURIComponent(record)}?${params}`);
  }
  resolve(identifiers: Identifier[]) {
    return this.request<ResolveResult[]>('/v1/products/resolve', {identifiers});
  }
  retailEvidence(productId: string, storeId?: string) {
    const params = new URLSearchParams(storeId ? {store_id: storeId} : {});
    return this.request<RetailEvidence>(`/v1/products/${encodeURIComponent(productId)}/retail-evidence?${params}`);
  }
}
