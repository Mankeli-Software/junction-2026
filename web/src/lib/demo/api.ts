/**
 * The phone page's calls to the backend, all same-origin (technical-plan.md §9.2).
 * The session cookie set by `POST /api/v1/demo/accounts` is the login.
 */
import type { DemoAccount, DemoAccountRequest, InboxMessage, Me } from './types';

export class ApiError extends Error {
	constructor(readonly status: number) {
		super(`Request failed with ${status}`);
	}
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(path, { credentials: 'same-origin', ...init });
	if (!response.ok) throw new ApiError(response.status);
	return response.json() as Promise<T>;
}

export function createAccount(request: DemoAccountRequest): Promise<DemoAccount> {
	return call('/api/v1/demo/accounts', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(request)
	});
}

export function getMe(): Promise<Me> {
	return call('/api/v1/me');
}

export function getInbox(): Promise<InboxMessage[]> {
	return call('/api/v1/private/inbox');
}

/** New inbox messages as they arrive. EventSource reconnects by itself. Returns close. */
export function watchInbox(onMessage: (message: InboxMessage) => void, onOpen: () => void = () => {}): () => void {
	const source = new EventSource('/api/v1/private/inbox/stream');
	source.addEventListener('open', onOpen);
	source.addEventListener('inbox_message', (event) => {
		try {
			onMessage(JSON.parse((event as MessageEvent<string>).data));
		} catch {
			// A malformed event: skip it.
		}
	});
	return () => source.close();
}
