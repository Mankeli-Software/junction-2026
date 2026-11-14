/**
 * The chat stream (docs/plans/57-a2ui-chat.md §3): `POST /api/v1/chat` and
 * `POST /api/v1/confirmations/{token}/chat` answer with server-sent events, read here
 * with `fetch` and a reader (a POST can't use `EventSource`). The SSE framing is the
 * dashboard's parser (#lib/dashboard/sse), which handles events split across chunks
 * and multi-line `data:`.
 */
import { createSseParser } from '#lib/dashboard/sse.js';
import type { A2uiClientAction, A2uiServerEnvelope } from '#lib/a2ui/protocol.js';

/** The request body, the same for both chat endpoints. Exactly one of `message` and `action`. */
export interface ChatRequest {
	conversation_id: string | null;
	message: string | null;
	action: A2uiClientAction | null;
	attachment_draft_id: string | null;
}

export type ChatErrorCode = 'not_configured' | 'busy' | 'failed' | 'network' | 'signed_out';

export type ChatEvent =
	| { type: 'start'; conversation_id: string }
	| { type: 'text'; delta: string }
	| { type: 'a2ui'; envelopes: A2uiServerEnvelope[] }
	| { type: 'tool'; name: string; status: 'started' | 'done' }
	| { type: 'done'; quote_id: string | null }
	| { type: 'error'; code: ChatErrorCode | string; message: string };

const record = (value: unknown): Record<string, unknown> =>
	value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};

/** One SSE message to a chat event, or null for an unknown type or bad data (skipped). */
export function toChatEvent(type: string, data: string): ChatEvent | null {
	let parsed: Record<string, unknown>;
	try {
		parsed = record(JSON.parse(data));
	} catch {
		return null;
	}
	switch (type) {
		case 'start':
			return typeof parsed.conversation_id === 'string'
				? { type, conversation_id: parsed.conversation_id }
				: null;
		case 'text':
			return typeof parsed.delta === 'string' ? { type, delta: parsed.delta } : null;
		case 'a2ui':
			return Array.isArray(parsed.envelopes)
				? { type, envelopes: parsed.envelopes.filter((e) => e !== null && typeof e === 'object') as A2uiServerEnvelope[] }
				: null;
		case 'tool':
			return typeof parsed.name === 'string' && (parsed.status === 'started' || parsed.status === 'done')
				? { type, name: parsed.name, status: parsed.status }
				: null;
		case 'done':
			return { type, quote_id: typeof parsed.quote_id === 'string' ? parsed.quote_id : null };
		case 'error':
			return {
				type,
				code: typeof parsed.code === 'string' ? parsed.code : 'failed',
				message: typeof parsed.message === 'string' ? parsed.message : ''
			};
		default:
			return null;
	}
}

/** Reads an SSE body to its end, calling `onEvent` for each chat event in order. */
export async function readChatStream(body: ReadableStream<Uint8Array>, onEvent: (event: ChatEvent) => void): Promise<void> {
	const parser = createSseParser((message) => {
		const event = toChatEvent(message.event, message.data);
		if (event) onEvent(event);
	});
	const decoder = new TextDecoder();
	const reader = body.getReader();
	for (;;) {
		const { value, done } = await reader.read();
		if (done) break;
		parser.push(decoder.decode(value, { stream: true }));
	}
	// A last event without its blank line still counts.
	parser.push(`${decoder.decode()}\n\n`);
}

/** The error code for a refused request (before any stream): HTTP status, then the body. */
export async function refusalCode(response: Response): Promise<ChatErrorCode> {
	let code: unknown = null;
	try {
		const body = record(await response.json());
		code = body.code ?? record(body.detail).code;
	} catch {
		// Not JSON: the status decides.
	}
	if (code === 'not_configured' || code === 'busy' || code === 'failed') return code;
	if (response.status === 503) return 'not_configured';
	if (response.status === 409 || response.status === 429) return 'busy';
	if (response.status === 401 || response.status === 403) return 'signed_out';
	return 'failed';
}

/**
 * Posts one turn and streams its events. A refused request or a dropped connection
 * becomes an `error` event, and a stream that ends without `done` or `error` gets a
 * `failed` one, so the caller always sees the turn end.
 */
export async function postChat(
	url: string,
	request: ChatRequest,
	onEvent: (event: ChatEvent) => void,
	fetcher: typeof fetch = fetch
): Promise<void> {
	let ended = false;
	const emit = (event: ChatEvent) => {
		if (ended) return;
		if (event.type === 'done' || event.type === 'error') ended = true;
		onEvent(event);
	};
	try {
		const response = await fetcher(url, {
			method: 'POST',
			credentials: 'same-origin',
			headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
			body: JSON.stringify(request)
		});
		if (!response.ok || !response.body) {
			emit({ type: 'error', code: response.ok ? 'failed' : await refusalCode(response), message: '' });
			return;
		}
		await readChatStream(response.body, emit);
		emit({ type: 'error', code: 'failed', message: '' });
	} catch {
		emit({ type: 'error', code: 'network', message: '' });
	}
}
