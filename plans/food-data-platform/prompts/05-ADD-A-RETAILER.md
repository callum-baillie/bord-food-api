# Add one retailer adapter without crawling during development

Read the existing source adapter, source-policy, identity and scheduler interfaces. Identify the requested retailer/banner separately from parent company, licensed network and subsidiaries. Inspect its official documentation and any All The Places implementation/output metadata before proposing a direct crawler. Research URLs are not automatically an approved crawl allowlist.

Implement the smallest adapter that fits: published ATP/bulk output, official downloadable roster, then an explicitly permitted bounded locator/sitemap/detail adapter if necessary. Define source keys, eligible formats, country scope, dates, canonicalization, full-snapshot completeness, removal semantics and field groups. Extend only reviewed descriptors. Never guess store-page slugs or scan hidden authenticated endpoints.

Use synthetic fixtures showing duplicates, missing fields, changed hours, an unchanged address, a new branch, closed/relocated ambiguity and blocked pages. Add semantic hash/delta tests and verify no unrelated existing records are recrawled. Keep the source disabled until operator activation; no live crawl or bulk import is authorized by this prompt.

Document exact official source/discovery URLs, access/license/robots/retention policy, costs if actually known and last verification level. If no legitimate interface is available, preserve a truthful unsupported/blocked capability and use bulk data/manual store fallback. No anti-bot bypass, credential harvesting or fabricated map/stock endpoint.
