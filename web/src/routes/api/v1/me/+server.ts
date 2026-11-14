/** `GET /api/v1/me` (technical-plan.md §9.2): the demo account of this browser, or 401. */
import { json } from '@sveltejs/kit';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { me, SESSION_COOKIE } from '#lib/server/demo/fixture.js';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const account = me(event.cookies.get(SESSION_COOKIE));
	if (!account) return json({ detail: 'Not signed in' }, { status: 401 });
	return json(account, { headers: PRIVATE_HEADERS });
};
