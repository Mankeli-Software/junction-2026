import { langParam } from '#lib/demo/i18n.js';
import { qrSvg } from '#lib/server/qr.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url, setHeaders }) => {
	// The page shows the visitor's own inbox once it runs; never cache it.
	setHeaders({ 'cache-control': 'no-store' });
	const lang = langParam(url.searchParams.get('lang'));
	return {
		lang,
		qr: await qrSvg(`${url.origin}/phone${lang === 'fi' ? '?lang=fi' : ''}`)
	};
};
