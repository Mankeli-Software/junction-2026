import { describe, expect, it } from 'vitest';
import { postChat, readChatStream, refusalCode, toChatEvent, type ChatEvent } from './stream';

function body(chunks: string[]): ReadableStream<Uint8Array> {
	const encoder = new TextEncoder();
	return new ReadableStream({
		start(controller) {
			for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
			controller.close();
		}
	});
}

async function read(chunks: string[]): Promise<ChatEvent[]> {
	const events: ChatEvent[] = [];
	await readChatStream(body(chunks), (e) => events.push(e));
	return events;
}

const STREAM = [
	'event: start\ndata: {"conversation_id":"c1"}\n\n',
	'event: text\ndata: {"delta":"Here is "}\n\n',
	'event: tool\ndata: {"name":"build_quote","status":"started"}\n\n',
	'event: a2ui\ndata: {"envelopes":[{"version":"v0.9","createSurface":{"surfaceId":"s1","catalogId":"x"}}]}\n\n',
	'event: done\ndata: {"quote_id":"q1"}\n\n'
].join('');

describe('readChatStream', () => {
	it('reads every event type in order', async () => {
		expect(await read([STREAM])).toEqual([
			{ type: 'start', conversation_id: 'c1' },
			{ type: 'text', delta: 'Here is ' },
			{ type: 'tool', name: 'build_quote', status: 'started' },
			{ type: 'a2ui', envelopes: [{ version: 'v0.9', createSurface: { surfaceId: 's1', catalogId: 'x' } }] },
			{ type: 'done', quote_id: 'q1' }
		]);
	});

	it('gives the same events however the stream is cut into chunks', async () => {
		const whole = await read([STREAM]);
		for (const size of [1, 2, 3, 7, 13]) {
			const chunks: string[] = [];
			for (let i = 0; i < STREAM.length; i += size) chunks.push(STREAM.slice(i, i + size));
			expect(await read(chunks)).toEqual(whole);
		}
	});

	it('handles CRLF lines and a UTF-8 character split across chunks', async () => {
		const encoder = new TextEncoder();
		const bytes = encoder.encode('event: text\r\ndata: {"delta":"Hyvää päivää"}\r\n\r\n');
		const cut = bytes.indexOf(0xc3) + 1; // inside the first "ä"
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(bytes.slice(0, cut));
				controller.enqueue(bytes.slice(cut));
				controller.close();
			}
		});
		const events: ChatEvent[] = [];
		await readChatStream(stream, (e) => events.push(e));
		expect(events).toEqual([{ type: 'text', delta: 'Hyvää päivää' }]);
	});

	it('joins multi-line data and skips comments, unknown events and bad JSON', async () => {
		const events = await read([
			': ping\n\n',
			'event: text\ndata: {"delta":\ndata: "two lines"}\n\n',
			'event: mystery\ndata: {}\n\n',
			'event: text\ndata: not json\n\n',
			'event: done\ndata: {"quote_id":null}'
		]);
		expect(events).toEqual([
			{ type: 'text', delta: 'two lines' },
			{ type: 'done', quote_id: null }
		]);
	});
});

describe('toChatEvent', () => {
	it('defaults an error without a code to failed', () => {
		expect(toChatEvent('error', '{}')).toEqual({ type: 'error', code: 'failed', message: '' });
		expect(toChatEvent('error', '{"code":"not_configured","message":"no"}')).toEqual({
			type: 'error',
			code: 'not_configured',
			message: 'no'
		});
	});

	it('drops a tool event with an unknown status', () => {
		expect(toChatEvent('tool', '{"name":"x","status":"halfway"}')).toBeNull();
	});
});

describe('refusalCode', () => {
	it('reads the code from the body, then the status', async () => {
		expect(await refusalCode(new Response('{"detail":{"code":"busy"}}', { status: 400 }))).toBe('busy');
		expect(await refusalCode(new Response('{"detail":"Chat not configured"}', { status: 503 }))).toBe('not_configured');
		expect(await refusalCode(new Response('', { status: 409 }))).toBe('busy');
		expect(await refusalCode(new Response('', { status: 401 }))).toBe('signed_out');
		expect(await refusalCode(new Response('', { status: 500 }))).toBe('failed');
	});
});

describe('postChat', () => {
	const request = { conversation_id: null, message: 'hi', action: null, attachment_draft_id: null };

	it('posts the body as JSON and streams the answer', async () => {
		let sent: RequestInit | undefined;
		const fetcher = (async (_url: string, init?: RequestInit) => {
			sent = init;
			return new Response(body([STREAM]), { headers: { 'content-type': 'text/event-stream' } });
		}) as typeof fetch;
		const events: ChatEvent[] = [];
		await postChat('/api/v1/chat', request, (e) => events.push(e), fetcher);
		expect(sent?.method).toBe('POST');
		expect(JSON.parse(String(sent?.body))).toEqual(request);
		expect(events.at(-1)).toEqual({ type: 'done', quote_id: 'q1' });
	});

	it('turns a 503 into not_configured', async () => {
		const fetcher = (async () => new Response('{"detail":"off"}', { status: 503 })) as typeof fetch;
		const events: ChatEvent[] = [];
		await postChat('/api/v1/chat', request, (e) => events.push(e), fetcher);
		expect(events).toEqual([{ type: 'error', code: 'not_configured', message: '' }]);
	});

	it('ends a stream that stops without done as failed, and a thrown fetch as network', async () => {
		const cut = (async () => new Response(body(['event: text\ndata: {"delta":"Hi"}\n\n']))) as typeof fetch;
		const events: ChatEvent[] = [];
		await postChat('/api/v1/chat', request, (e) => events.push(e), cut);
		expect(events).toEqual([
			{ type: 'text', delta: 'Hi' },
			{ type: 'error', code: 'failed', message: '' }
		]);

		const offline = (async () => {
			throw new TypeError('Failed to fetch');
		}) as typeof fetch;
		const more: ChatEvent[] = [];
		await postChat('/api/v1/chat', request, (e) => more.push(e), offline);
		expect(more).toEqual([{ type: 'error', code: 'network', message: '' }]);
	});

	it('ignores anything after done', async () => {
		const fetcher = (async () =>
			new Response(body(['event: done\ndata: {"quote_id":null}\n\nevent: text\ndata: {"delta":"late"}\n\n']))) as typeof fetch;
		const events: ChatEvent[] = [];
		await postChat('/api/v1/chat', request, (e) => events.push(e), fetcher);
		expect(events).toEqual([{ type: 'done', quote_id: null }]);
	});
});
