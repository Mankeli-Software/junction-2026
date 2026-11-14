/** `GET /api/v1/private/inbox` (technical-plan.md §9.2): the simulated phone's messages. */
import { json } from '@sveltejs/kit';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { inbox, SESSION_COOKIE } from '#lib/server/demo/fixture.js';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const messages = inbox(event.cookies.get(SESSION_COOKIE));
	if (!messages) return json({ detail: 'Not signed in' }, { status: 401 });
	return json(messages, { headers: PRIVATE_HEADERS });
};
