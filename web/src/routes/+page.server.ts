import { langParam } from '#lib/demo/i18n.js';
import { qrSvg } from '#lib/server/qr.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const lang = langParam(url.searchParams.get('lang'));
	const phoneUrl = `${url.origin}/phone${lang === 'fi' ? '?lang=fi' : ''}`;
	return {
		lang,
		qr: await qrSvg(phoneUrl),
		mcpUrl: `${url.origin}/mcp`
	};
};
