import { SHOP_LANG } from '$app/env/private';
import { loadCatalogue, loadProducts, ShopUnavailable } from '#lib/server/shop.js';
import { shopLang } from '#lib/shop/lang.js';
import { findCategory, firstCategory, type ShopCatalogue, type ShopProducts } from '#lib/shop/products.js';
import type { PageServerLoad } from './$types';

/**
 * The language is picked on the server, so the first render is already right (#56).
 * `?category=` picks the category to list (#118); without one, or with an unknown one,
 * the shop opens on the tree's first category.
 */
export const load: PageServerLoad = async ({ url, request, setHeaders, fetch }) => {
	setHeaders({ 'cache-control': 'no-store', vary: 'Accept-Language' });
	const lang = shopLang(SHOP_LANG, url.searchParams.get('lang'), request.headers.get('accept-language'));
	let catalogue: ShopCatalogue = { sections: [] };
	let shown: ShopProducts | null = null;
	let unavailable = false;
	try {
		catalogue = await loadCatalogue(fetch);
		const asked = url.searchParams.get('category');
		const id = asked && findCategory(catalogue, asked) ? asked : firstCategory(catalogue);
		shown = id ? await loadProducts(fetch, id) : null;
	} catch (error) {
		if (!(error instanceof ShopUnavailable)) throw error;
		unavailable = true;
	}
	return { lang, catalogue, shown, unavailable };
};
