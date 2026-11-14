/**
 * The live connection: one stream per page on `/api/v1/public/stream`, or the fake
 * event source when `PUBLIC_DASHBOARD_MOCK=1`. The header reads `connection` for the live dot
 * and the demo clock.
 */
import { PUBLIC_DASHBOARD_MOCK } from '$app/env/public';
import { streamUrl } from './api';
import { ResumePoint, createSseParser } from './sse';
import type { OverviewFilter, StreamMessage } from './types';

export const connection = $state({
	connected: false,
	/** The demo clock from the latest snapshot or overview load. */
	businessNow: null as string | null
});

export interface LiveConnection {
	close(): void;
}

export type StreamListener = (message: StreamMessage) => void;

const EVENT_TYPES = ['snapshot', 'order_updated', 'step', 'transcript'] as const;

// Connections that are up. A page's old connection may close after the next page's opens.
const up = new Set<object>();

function setUp(token: object, isUp: boolean): void {
	if (isUp) up.add(token);
	else up.delete(token);
	connection.connected = up.size > 0;
}

const RETRY_MIN_MS = 1000;
const RETRY_MAX_MS = 15000;

function isEventType(event: string): event is StreamMessage['event'] {
	return (EVENT_TYPES as readonly string[]).includes(event);
}

/**
 * The real stream, read with `fetch` (see `sse.ts` for why not `EventSource`). Reconnects
 * after a drop with growing pauses, resuming from the last complete id: the server then
 * sends the missed events, or a new snapshot when it no longer has them.
 */
function connectReal(filter: OverviewFilter, listener: StreamListener): LiveConnection {
	const token = {};
	const resume = new ResumePoint();
	const parser = createSseParser((message) => {
		if (!isEventType(message.event)) return;
		resume.seen(message.event, message.id);
		try {
			listener({ event: message.event, id: message.id, data: JSON.parse(message.data) } as StreamMessage);
		} catch (err) {
			console.error('Bad stream event', message.event, err);
		}
	});
	let abort = new AbortController();
	let closed = false;
	let retry = RETRY_MIN_MS;
	let timer: ReturnType<typeof setTimeout> | undefined;

	async function run(): Promise<void> {
		parser.reset();
		const headers: Record<string, string> = { accept: 'text/event-stream' };
		if (resume.complete !== null) headers['last-event-id'] = resume.complete;
		try {
			const response = await fetch(streamUrl(filter), { headers, signal: abort.signal, cache: 'no-store' });
			if (!response.ok || !response.body) throw new Error(`stream answered ${response.status}`);
			setUp(token, true);
			retry = RETRY_MIN_MS;
			const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
			for (;;) {
				const { done, value } = await reader.read();
				if (done) break;
				parser.push(value);
			}
		} catch (err) {
			if (closed) return;
			console.warn('Dashboard stream dropped', err);
		}
		setUp(token, false);
		if (closed) return;
		timer = setTimeout(() => {
			abort = new AbortController();
			void run();
		}, retry);
		retry = Math.min(retry * 2, RETRY_MAX_MS);
	}

	void run();
	return {
		close() {
			closed = true;
			clearTimeout(timer);
			abort.abort();
			setUp(token, false);
		}
	};
}

/** Opens the stream for a page. Call from `$effect` and close in its cleanup. */
export function connectStream(filter: OverviewFilter, listener: StreamListener): LiveConnection {
	const wrapped: StreamListener = (message) => {
		if (message.event === 'snapshot') connection.businessNow = message.data.business_now;
		listener(message);
	};
	if (!PUBLIC_DASHBOARD_MOCK) return connectReal(filter, wrapped);

	const token = {};
	let closed = false;
	let inner: LiveConnection | null = null;
	import('./mock/replay').then(({ connectFake }) => {
		if (!closed) inner = connectFake(filter, wrapped, (isUp) => setUp(token, isUp));
	});
	return {
		close() {
			closed = true;
			inner?.close();
			setUp(token, false);
		}
	};
}
