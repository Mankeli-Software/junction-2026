/** `POST /api/v1/demo/accounts` (technical-plan.md §9.2): number and kitchen in, demo account out. */
import { json } from '@sveltejs/kit';
import { isE164 } from '#lib/demo/phone.js';
import { isExclusion, type DemoAccountRequest } from '#lib/demo/types.js';
import { demoSource, PRIVATE_HEADERS, proxyToApi } from '#lib/server/demo/index.js';
import { createAccount, FixtureLimitError, SESSION_COOKIE } from '#lib/server/demo/fixture.js';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);

	const body = await event.request.json().catch(() => null);
	const request = parse(body);
	if (!request) return json({ detail: 'Invalid phone number or exclusions' }, { status: 422 });

	try {
		const { sessionId, account } = createAccount(event.cookies.get(SESSION_COOKIE) ?? null, request);
		event.cookies.set(SESSION_COOKIE, sessionId, {
			path: '/',
			httpOnly: true,
			sameSite: 'lax',
			secure: event.url.protocol === 'https:',
			maxAge: 60 * 60 * 24 * 3
		});
		return json(account, { headers: PRIVATE_HEADERS });
	} catch (error) {
		if (error instanceof FixtureLimitError) return json({ detail: error.message }, { status: 429 });
		throw error;
	}
};

function parse(body: unknown): DemoAccountRequest | null {
	if (typeof body !== 'object' || body === null) return null;
	const { phone_e164, exclusions, lang } = body as Record<string, unknown>;
	if (typeof phone_e164 !== 'string' || !isE164(phone_e164)) return null;
	if (!Array.isArray(exclusions) || !exclusions.every(isExclusion)) return null;
	return { phone_e164, exclusions: [...new Set(exclusions)], lang: lang === 'fi' ? 'fi' : 'en' };
}
