/**
 * The live connection: one `EventSource` per page on `/api/v1/public/stream`, or the fake
 * event source when `PUBLIC_DASHBOARD_MOCK=1`. The header reads `connection` for the live dot
 * and the demo clock.
 */
import { PUBLIC_DASHBOARD_MOCK } from '$app/env/public';
import { streamUrl } from './api';
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

function connectReal(filter: OverviewFilter, listener: StreamListener): LiveConnection {
	// EventSource reconnects by itself and sends Last-Event-ID, so missed events come first.
	const source = new EventSource(streamUrl(filter));
	source.onopen = () => setUp(source, true);
	source.onerror = () => setUp(source, source.readyState === EventSource.OPEN);
	for (const event of EVENT_TYPES) {
		source.addEventListener(event, (e) => {
			const message = e as MessageEvent<string>;
			try {
				listener({ event, id: message.lastEventId || null, data: JSON.parse(message.data) } as StreamMessage);
			} catch (err) {
				console.error('Bad stream event', event, err);
			}
		});
	}
	return {
		close() {
			source.close();
			setUp(source, false);
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
