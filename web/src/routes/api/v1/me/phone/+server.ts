/** `POST /api/v1/me/phone` (#48): the number of a hand-out account, set once on first login. */
import { json } from '@sveltejs/kit';
import { isE164 } from '#lib/demo/phone.js';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { setPhone } from '#lib/server/demo/connector-fixture.js';
import { answer, body, sessionOf, setSessionCookie, str } from '#lib/server/demo/http.js';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const phone = str((await body(event))?.phone_e164);
	if (!isE164(phone)) return json({ detail: 'Invalid phone number' }, { status: 422 });
	return answer(() => {
		const { sessionId, me } = setPhone(sessionOf(event.cookies), phone);
		setSessionCookie(event, sessionId);
		return json(me, { headers: PRIVATE_HEADERS });
	});
};
