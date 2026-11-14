/**
 * The login pages' calls to the backend (#48, technical-plan.md §9.2), all same-origin.
 * The `simo_session` cookie set by sign-up or login is the login.
 */
import type { Me } from '../demo/types';

export class AuthError extends Error {
	constructor(
		readonly status: number,
		readonly detail: string | null
	) {
		super(detail ?? `Request failed with ${status}`);
	}
}

async function call<T>(path: string, method: 'GET' | 'POST', body?: unknown): Promise<T> {
	const response = await fetch(path, {
		method,
		credentials: 'same-origin',
		headers: body === undefined ? undefined : { 'content-type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (!response.ok) {
		const payload = await response.json().catch(() => null);
		const detail = typeof payload?.detail === 'string' ? payload.detail : null;
		throw new AuthError(response.status, detail);
	}
	return response.json() as Promise<T>;
}

export function signup(email: string, password: string, phone_e164: string): Promise<Me> {
	return call('/api/v1/signup', 'POST', { email, password, phone_e164 });
}

export function login(email: string, password: string): Promise<{ phone_required: boolean }> {
	return call('/api/v1/session', 'POST', { email, password });
}

export function setPhone(phone_e164: string): Promise<Me> {
	return call('/api/v1/me/phone', 'POST', { phone_e164 });
}

/** What the consent page asks: "Allow <client_name> to order for <company_name>?" */
export interface ConnectRequest {
	client_name: string;
	company_name: string;
	phone_masked: string;
	redirect_host: string;
}

export function getConnectRequest(id: string): Promise<ConnectRequest> {
	return call(`/api/v1/oauth/requests/${encodeURIComponent(id)}`, 'GET');
}

export function decideConnectRequest(id: string, allow: boolean): Promise<{ redirect_to: string }> {
	return call(`/api/v1/oauth/requests/${encodeURIComponent(id)}`, 'POST', { allow });
}
