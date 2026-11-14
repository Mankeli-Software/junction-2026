/**
 * The confirmation endpoints of the FastAPI app (technical-plan.md §9.4).
 * Error bodies are assumed to be `{ detail?: { text?: Text, line_id?: string } }`;
 * align this with #47 when the endpoints exist.
 */
import type { EditOp, Text } from '#lib/confirmation/types.js';
import { ConfirmationError, type ConfirmationSource } from './source';

interface ErrorBody {
	detail?: { text?: Text; line_id?: string } | string;
}

export function apiSource(baseUrl: string, fetchImpl: typeof fetch = fetch): ConfirmationSource {
	const url = (token: string, action = '') =>
		`${baseUrl.replace(/\/$/, '')}/api/v1/confirmations/${encodeURIComponent(token)}${action}`;

	async function post(token: string, action: string, body: unknown): Promise<void> {
		const response = await fetchImpl(url(token, action), {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(body)
		});
		if (!response.ok) throw await toError(response);
	}

	return {
		async get(token) {
			const response = await fetchImpl(url(token));
			if (response.status === 404) return null;
			if (!response.ok) throw await toError(response);
			return response.json();
		},
		acknowledge: (token, quoteHash, flagKey, optionId = null) =>
			post(token, '/acknowledgements', { quote_hash: quoteHash, flag_key: flagKey, option_id: optionId }),
		edit: (token, quoteHash, edit: EditOp) => post(token, '/edits', { quote_hash: quoteHash, ...edit }),
		confirm: (token, quoteHash) => post(token, '/confirm', { quote_hash: quoteHash }),
		cancel: (token, quoteHash) => post(token, '/cancel', { quote_hash: quoteHash })
	};
}

async function toError(response: Response): Promise<ConfirmationError> {
	let body: ErrorBody = {};
	try {
		body = await response.json();
	} catch {
		// Not JSON: keep the status only.
	}
	const detail = typeof body.detail === 'object' ? body.detail : undefined;
	return new ConfirmationError(response.status, detail?.text ?? null, detail?.line_id ?? null);
}
