// Run with Bòrd's tsx and tsconfig; this imports its real provider without editing Bòrd.
// BORD_SOURCE_DIR, USDA_FDC_BASE_URL and optional USDA_FDC_API_KEY select the target.
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

if (!process.env.BORD_SOURCE_DIR || !process.env.USDA_FDC_BASE_URL) {
  throw new Error('Set BORD_SOURCE_DIR and USDA_FDC_BASE_URL explicitly.');
}
process.env.USDA_FDC_API_KEY ||= 'local';
process.env.USDA_FDC_ENABLED = 'true';
const moduleUrl = pathToFileURL(resolve(process.env.BORD_SOURCE_DIR, 'src/lib/providers/usda-food-data-provider.ts'));
const { UsdaFoodDataProvider } = await import(moduleUrl.href);
const provider = new UsdaFoodDataProvider();
const generic = await provider.searchByName('oats', 1, 'generic');
assert(generic.value.length > 0);
assert(generic.value.every((food: {dataType: string}) => ['Foundation', 'Survey (FNDDS)'].includes(food.dataType)));
const details = await provider.getDetails(generic.value[0].providerRecordId);
assert.equal(details.value.providerRecordId, generic.value[0].providerRecordId);
assert(details.value.nutrients.length > 0);
const branded = await provider.searchByName('oats', 1, 'branded');
const product = branded.value.find((food: {canonicalGtin: string | null}) => food.canonicalGtin);
assert(product, 'Expected an oats product with a valid barcode');
const barcode = await provider.lookupBarcode(product.canonicalGtin);
assert.equal(barcode.value.canonicalGtin, product.canonicalGtin);
console.log(JSON.stringify({genericResults: generic.value.length, detailNutrients: details.value.nutrients.length, brandedResults: branded.value.length, barcodeMatched: true}));
