/** `POST /api/v1/signup` (#48, technical-plan.md §9.2): email, password and number in, signed in. */
import { json } from '@sveltejs/kit';
import { isE164 } from '#lib/demo/phone.js';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { signup } from '#lib/server/demo/connector-fixture.js';
import { answer, body, setSessionCookie, str } from '#lib/server/demo/http.js';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const request = await body(event);
	const phone = str(request?.phone_e164);
	if (!isE164(phone)) return json({ detail: 'Invalid phone number' }, { status: 422 });
	return answer(() => {
		const { sessionId, me } = signup(str(request?.email), str(request?.password), phone);
		setSessionCookie(event, sessionId);
		return json(me, { status: 201, headers: PRIVATE_HEADERS });
	});
};
