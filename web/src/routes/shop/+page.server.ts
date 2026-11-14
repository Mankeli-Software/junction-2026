import { SHOP_LANG } from '$app/env/private';
import { shopLang } from '#lib/shop/lang.js';
import type { PageServerLoad } from './$types';

/** The language is picked on the server, so the first render is already right (#56). */
export const load: PageServerLoad = async ({ url, request, setHeaders }) => {
	setHeaders({ 'cache-control': 'no-store', vary: 'Accept-Language' });
	return {
		lang: shopLang(SHOP_LANG, url.searchParams.get('lang'), request.headers.get('accept-language'))
	};
};
