/** Planning example, not an already integrated/compiled Bòrd client.
 * Use inside an authorized our-recipes checkout; never expose the key to the browser.
 * Production implementation adds all generated endpoint types and contract tests.
 */
import 'server-only';
import { z } from 'zod';

const storeResponse = z.object({
  schema_version: z.literal('1.0.0'),
  data: z.object({
    entity_type: z.literal('store_location'),
    store_id: z.string().min(1),
    chain_id: z.string().min(1).nullable(),
    name: z.string().min(1),
    address: z.object({
      line_1: z.string().nullable(), city: z.string().nullable(), region_code: z.string().nullable(),
      postal_code: z.string().nullable(), country_code: z.literal('US'),
    }).passthrough(),
  }).passthrough(),
  meta: z.object({
    catalog_generation: z.string().nullable(), source_refs: z.array(z.string()),
    warnings: z.array(z.object({ code: z.string(), message: z.string() })),
    next_cursor: z.string().nullable(),
  }).passthrough(),
});
export type CatalogStoreResponse = z.infer<typeof storeResponse>;

async function boundedJson(response: Response, maxBytes = 2 * 1024 * 1024): Promise<unknown> {
  if (!response.headers.get('content-type')?.toLowerCase().includes('application/json'))
    throw new Error('Catalog returned an unexpected content type.');
  if (!response.body) throw new Error('Catalog returned no body.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let bytes = 0;
  let text = '';
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maxBytes) throw new Error('Catalog response exceeded its size limit.');
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    return JSON.parse(text) as unknown;
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export class BordCatalogClient {
  private readonly base: URL;
  constructor(baseUrl: string, private readonly key: string, private readonly fetcher: typeof fetch = fetch) {
    this.base = new URL(baseUrl);
    if (!['http:', 'https:'].includes(this.base.protocol) || this.base.username || this.base.password ||
        this.base.search || this.base.hash || !['', '/'].includes(this.base.pathname))
      throw new Error('Use an operator-configured catalog origin without credentials or a path.');
    // Private LAN/container origins are intentional trusted server configuration,
    // not URLs accepted from a user request. Apply deployment-specific origin policy.
  }
  async getStore(storeId: string): Promise<CatalogStoreResponse> {
    if (!storeId || storeId.length > 160 || /[\s/\\]/u.test(storeId))
      throw new Error('Invalid store identifier.');
    const response = await this.fetcher(new URL(`/v1/stores/${encodeURIComponent(storeId)}`, this.base), {
      method: 'GET', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(5000),
      headers: { Accept: 'application/json', ...(this.key ? { 'X-Api-Key': this.key } : {}) },
    });
    if (!response.ok) {
      await response.body?.cancel().catch(() => undefined);
      // Never interpolate source body, URL, key or household query into logs/errors.
      throw new Error(`Catalog request failed with status ${response.status}.`);
    }
    return storeResponse.parse(await boundedJson(response));
  }
}
