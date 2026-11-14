/** The connector consent step (#48): `GET` what to ask, `POST` Allow or Cancel. */
import { json } from '@sveltejs/kit';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { connectRequest, decide } from '#lib/server/demo/connector-fixture.js';
import { answer, body, sessionOf } from '#lib/server/demo/http.js';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	return answer(() => json(connectRequest(sessionOf(event.cookies), event.params.id), { headers: PRIVATE_HEADERS }));
};

export const POST: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const allow = (await body(event))?.allow === true;
	return answer(() => json(decide(sessionOf(event.cookies), event.params.id, allow), { headers: PRIVATE_HEADERS }));
};
