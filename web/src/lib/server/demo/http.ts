/** Small helpers for the fixture routes of technical-plan.md §9.2. */
import { json, type Cookies, type RequestEvent } from '@sveltejs/kit';
import { SESSION_COOKIE } from './fixture.ts';
import { FixtureError } from './connector-fixture.ts';
import { PRIVATE_HEADERS } from './index.ts';

export function setSessionCookie(event: RequestEvent, sessionId: string): void {
	event.cookies.set(SESSION_COOKIE, sessionId, {
		path: '/',
		httpOnly: true,
		sameSite: 'lax',
		secure: event.url.protocol === 'https:',
		maxAge: 60 * 60 * 24 * 3
	});
}

export function sessionOf(cookies: Cookies): string | undefined {
	return cookies.get(SESSION_COOKIE);
}

/** The JSON body as an object, or null. */
export async function body(event: RequestEvent): Promise<Record<string, unknown> | null> {
	const value = await event.request.json().catch(() => null);
	return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
}

export function str(value: unknown): string {
	return typeof value === 'string' ? value : '';
}

/** Runs a fixture call, turning a FixtureError into its status and `{detail}`. */
export function answer(run: () => Response): Response {
	try {
		return run();
	} catch (error) {
		if (error instanceof FixtureError) return json({ detail: error.message }, { status: error.status, headers: PRIVATE_HEADERS });
		throw error;
	}
}
