/**
 * The webshop's catalogue on the server (#118): FastAPI's /api/v1/shop with
 * DEMO_SOURCE=api, the twelve fixture products with DEMO_SOURCE=fixture (the dev server
 * and the Playwright tests), like the phone page's data (./demo/index.ts).
 */
import { apiBaseUrl, demoSource } from '#lib/server/demo/index.js';
import { fixtureCatalogue, fixtureProducts, type ShopCatalogue, type ShopProducts } from '#lib/shop/products.js';

export class ShopUnavailable extends Error {}

async function getJson<T>(fetcher: typeof fetch, path: string): Promise<T | null> {
	let response: Response;
	try {
		response = await fetcher(`${apiBaseUrl()}/api/v1/shop${path}`, { headers: { accept: 'application/json' } });
	} catch {
		throw new ShopUnavailable('The shop could not reach the server.');
	}
	if (response.status === 404) return null;
	if (!response.ok) throw new ShopUnavailable(`The shop catalogue answered ${response.status}.`);
	return (await response.json()) as T;
}

export async function loadCatalogue(fetcher: typeof fetch): Promise<ShopCatalogue> {
	if (demoSource() === 'fixture') return fixtureCatalogue();
	return (await getJson<ShopCatalogue>(fetcher, '/categories')) ?? { sections: [] };
}

/** A category's top products, or null when there is no such category. */
export async function loadProducts(fetcher: typeof fetch, id: string): Promise<ShopProducts | null> {
	if (demoSource() === 'fixture') return fixtureProducts(id);
	return getJson<ShopProducts>(fetcher, `/categories/${encodeURIComponent(id)}/products`);
}
