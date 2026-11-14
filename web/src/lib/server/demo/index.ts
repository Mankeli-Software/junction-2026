/**
 * Where the phone page's data comes from, picked with DEMO_SOURCE (like the
 * confirmation page's CONFIRMATION_SOURCE):
 * - `fixture` (default until #44, #46 and #52 land): the in-memory fixture in
 *   ./fixture.ts and the mock relay in ./relay.ts.
 * - `api`: FastAPI at API_BASE_URL (default http://localhost:8000).
 *
 * The browser always calls the same-origin paths of technical-plan.md §9.2 and
 * §9.3. On the VM, Caddy sends `/api/*` and `/voice/*` to FastAPI, so these
 * SvelteKit routes are never reached there. Without Caddy (local development), the
 * routes answer from the fixture or pass the request through to FastAPI, and
 * vite.config.ts proxies `/voice/ws`.
 */
import type { RequestEvent } from '@sveltejs/kit';

export type DemoSource = 'fixture' | 'api';

export function demoSource(): DemoSource {
	const kind = process.env.DEMO_SOURCE ?? 'fixture';
	if (kind !== 'fixture' && kind !== 'api') {
		throw new Error(`DEMO_SOURCE must be "fixture" or "api", not "${kind}"`);
	}
	return kind;
}

export function apiBaseUrl(): string {
	return (process.env.API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '');
}

const FORWARD_REQUEST = ['cookie', 'content-type', 'accept', 'accept-language', 'last-event-id'];
const FORWARD_RESPONSE = ['content-type', 'cache-control'];

/** Passes the request through to the same path on FastAPI, cookies included. */
export async function proxyToApi(event: RequestEvent): Promise<Response> {
	const target = `${apiBaseUrl()}${event.url.pathname}${event.url.search}`;
	const headers = new Headers();
	for (const name of FORWARD_REQUEST) {
		const value = event.request.headers.get(name);
		if (value) headers.set(name, value);
	}
	const method = event.request.method;
	const upstream = await fetch(target, {
		method,
		headers,
		body: method === 'GET' || method === 'HEAD' ? undefined : await event.request.arrayBuffer(),
		signal: event.request.signal
	});
	const out = new Headers();
	for (const name of FORWARD_RESPONSE) {
		const value = upstream.headers.get(name);
		if (value) out.set(name, value);
	}
	for (const cookie of upstream.headers.getSetCookie()) out.append('set-cookie', cookie);
	return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const PRIVATE_HEADERS = { 'cache-control': 'no-store' } as const;
