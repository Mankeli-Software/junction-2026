/**
 * In-memory stand-in for the connector accounts and the OAuth consent step (#48), used
 * with DEMO_SOURCE=fixture (`pnpm dev`, the Playwright tests). It sits on top of the demo
 * fixture, so a signed-in connector account is an ordinary fixture user with an inbox.
 *
 * - Any `judge<anything>@simo.mankeli.co` with the password `handout-pass` is a hand-out
 *   account without a number (made on its first login, so every test can have its own):
 *   the first login asks for the number.
 * - Any request id works on `/connect?request=<id>`; `expired` answers 404. The client is
 *   always "Claude", and Allow sends the browser to `/phone?inbox=1&code=fixture`.
 */
import { randomBytes } from 'node:crypto';
import { createAccount, me } from './fixture.ts';
import type { Me } from '../../demo/types.ts';

export const HANDOUT_PASSWORD = 'handout-pass';
const HANDOUT_EMAIL = /^judge[a-z0-9-]*@simo\.mankeli\.co$/;

interface Account {
	password: string;
	phone: string | null;
}

interface Store {
	accounts: Map<string, Account>;
	/** Sessions of hand-out accounts that have no number yet: session id → email. */
	unclaimed: Map<string, string>;
}

const KEY = Symbol.for('simo.connector.fixture');

function store(): Store {
	const holder = globalThis as unknown as Record<symbol, Store | undefined>;
	holder[KEY] ??= {
		accounts: new Map(),
		unclaimed: new Map()
	};
	return holder[KEY];
}

export class FixtureError extends Error {
	constructor(
		readonly status: number,
		detail: string
	) {
		super(detail);
	}
}

function session(phone: string): string {
	return createAccount(null, { phone_e164: phone, exclusions: [], lang: 'en' }).sessionId;
}

export function signup(email: string, password: string, phone: string): { sessionId: string; me: Me } {
	const key = email.trim().toLowerCase();
	if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(key)) throw new FixtureError(422, 'Invalid email address');
	if (password.length < 10) throw new FixtureError(422, 'Password needs at least 10 characters');
	const { accounts } = store();
	if (accounts.has(key)) throw new FixtureError(409, "This email can't be used to sign up. Try logging in instead.");
	accounts.set(key, { password, phone });
	const sessionId = session(phone);
	return { sessionId, me: me(sessionId)! };
}

export function login(email: string, password: string): { sessionId: string; phoneRequired: boolean } {
	const key = email.trim().toLowerCase();
	const { accounts } = store();
	if (!accounts.has(key) && HANDOUT_EMAIL.test(key)) accounts.set(key, { password: HANDOUT_PASSWORD, phone: null });
	const account = accounts.get(key);
	if (!account || account.password !== password) throw new FixtureError(401, 'Wrong email or password');
	if (account.phone) return { sessionId: session(account.phone), phoneRequired: false };
	const sessionId = randomBytes(18).toString('base64url');
	store().unclaimed.set(sessionId, key);
	return { sessionId, phoneRequired: true };
}

export function setPhone(sessionId: string | undefined, phone: string): { sessionId: string; me: Me } {
	if (!sessionId) throw new FixtureError(401, 'Not signed in');
	const { unclaimed, accounts } = store();
	const email = unclaimed.get(sessionId);
	if (!email) {
		throw me(sessionId) ? new FixtureError(409, 'The phone number is already set') : new FixtureError(401, 'Not signed in');
	}
	unclaimed.delete(sessionId);
	accounts.get(email)!.phone = phone;
	const next = session(phone);
	return { sessionId: next, me: me(next)! };
}

export function connectRequest(sessionId: string | undefined, requestId: string) {
	if (sessionId && store().unclaimed.has(sessionId)) throw new FixtureError(409, 'phone_required');
	const account = me(sessionId);
	if (!account) throw new FixtureError(401, 'Not signed in');
	if (requestId === 'expired') throw new FixtureError(404, 'This sign-in request has expired. Start again from your assistant.');
	return {
		client_name: 'Claude',
		company_name: account.company_name,
		phone_masked: account.phone_masked,
		redirect_host: 'claude.ai'
	};
}

export function decide(sessionId: string | undefined, requestId: string, allow: boolean): { redirect_to: string } {
	connectRequest(sessionId, requestId);
	return { redirect_to: allow ? '/phone?inbox=1&code=fixture' : '/phone?inbox=1&error=access_denied' };
}
