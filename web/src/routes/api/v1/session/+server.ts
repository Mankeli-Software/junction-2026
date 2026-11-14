/** `POST /api/v1/session` (log in, #48) and `DELETE /api/v1/session` (log out, #44). */
import { json } from '@sveltejs/kit';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { login } from '#lib/server/demo/connector-fixture.js';
import { SESSION_COOKIE } from '#lib/server/demo/fixture.js';
import { answer, body, setSessionCookie, str } from '#lib/server/demo/http.js';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const request = await body(event);
	return answer(() => {
		const { sessionId, phoneRequired } = login(str(request?.email), str(request?.password));
		setSessionCookie(event, sessionId);
		return json({ phone_required: phoneRequired }, { headers: PRIVATE_HEADERS });
	});
};

export const DELETE: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	event.cookies.delete(SESSION_COOKIE, { path: '/' });
	return new Response(null, { status: 204 });
};
