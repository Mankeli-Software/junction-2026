/**
 * The public dashboard API (#49) for the browser: the live stream and "Download JSON". On the
 * VM, Caddy sends `/api/*` to FastAPI and this route is never reached. Locally (`pnpm dev`, a
 * build without Caddy, the Playwright tests), GET requests pass through to FastAPI at
 * `API_INTERNAL_URL`, the stream included, with `Last-Event-ID`. With
 * `PUBLIC_DASHBOARD_MOCK=1` the browser never calls these, so they answer 503.
 */
import { API_INTERNAL_URL } from '$app/env/private';
import { PUBLIC_DASHBOARD_MOCK } from '$app/env/public';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const FORWARD_REQUEST = ['accept', 'last-event-id'];
const FORWARD_RESPONSE = ['content-type', 'cache-control', 'content-disposition', 'x-accel-buffering'];

export const GET: RequestHandler = async ({ request, url }) => {
	if (PUBLIC_DASHBOARD_MOCK) {
		return json({ detail: 'The dashboard runs on mock data (PUBLIC_DASHBOARD_MOCK=1).' }, { status: 503 });
	}
	const headers = new Headers();
	for (const name of FORWARD_REQUEST) {
		const value = request.headers.get(name);
		if (value) headers.set(name, value);
	}
	let upstream: Response;
	try {
		upstream = await fetch(`${API_INTERNAL_URL}${url.pathname}${url.search}`, { headers, signal: request.signal });
	} catch {
		return json({ detail: 'The API is not reachable.' }, { status: 502 });
	}
	const out = new Headers();
	for (const name of FORWARD_RESPONSE) {
		const value = upstream.headers.get(name);
		if (value) out.set(name, value);
	}
	return new Response(upstream.body, { status: upstream.status, headers: out });
};
