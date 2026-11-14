/**
 * The dashboard stream's wire format: server-sent events as `/api/v1/public/stream` writes
 * them (#49), read with `fetch` rather than `EventSource` so the client picks what it sends
 * as `Last-Event-ID` on a reconnect.
 *
 * Why: one `status_events` id can carry several events (a `step`, a `transcript` and an
 * `order_updated`), and the server resends only the events with a *greater* id. Resuming
 * from the last id seen, as `EventSource` does, would lose the rest of a group the
 * connection dropped in the middle of. So the client resumes from the last id it knows is
 * complete, the one before the latest, and the events it gets twice merge idempotently.
 */

export interface SseMessage {
	event: string;
	/** The `id:` of this message, or null when it had none. */
	id: string | null;
	data: string;
}

/**
 * Splits a text stream into messages (the WHATWG "event stream interpretation"): fields
 * `event`, `data` (several lines are joined with "\n"), `id`; comments (`: ping`) and
 * `retry` are ignored. A message is dispatched at a blank line, and only when it has data.
 */
export function createSseParser(onMessage: (message: SseMessage) => void) {
	let buffer = '';
	let event = '';
	let data: string[] = [];
	let id: string | null = null;

	function line(text: string): void {
		if (text === '') {
			if (data.length > 0) onMessage({ event: event || 'message', id, data: data.join('\n') });
			event = '';
			data = [];
			id = null;
			return;
		}
		if (text.startsWith(':')) return;
		const colon = text.indexOf(':');
		const field = colon === -1 ? text : text.slice(0, colon);
		let value = colon === -1 ? '' : text.slice(colon + 1);
		if (value.startsWith(' ')) value = value.slice(1);
		if (field === 'event') event = value;
		else if (field === 'data') data.push(value);
		else if (field === 'id' && !value.includes('\0')) id = value;
	}

	return {
		push(chunk: string): void {
			buffer += chunk;
			for (;;) {
				const match = /\r\n|\r|\n/.exec(buffer);
				// A lone "\r" at the end may be the first half of "\r\n": wait for more.
				if (!match || (match[0] === '\r' && match.index === buffer.length - 1)) break;
				line(buffer.slice(0, match.index));
				buffer = buffer.slice(match.index + match[0].length);
			}
		},
		/** Drops a half-received message, for a new connection. */
		reset(): void {
			buffer = '';
			event = '';
			data = [];
			id = null;
		}
	};
}

/**
 * Which id to send as `Last-Event-ID` on a reconnect. A snapshot's id is complete: the
 * snapshot already holds everything up to it. A live event's id is complete once an event
 * with another id follows it, because the server sends each group together and in order.
 */
export class ResumePoint {
	/** The id to resume from, or null for a fresh snapshot. */
	complete: string | null = null;
	private latest: string | null = null;

	seen(event: string, id: string | null): void {
		if (event === 'snapshot') {
			this.complete = id;
			this.latest = id;
			return;
		}
		if (id === null || id === this.latest) return;
		if (this.latest !== null) this.complete = this.latest;
		this.latest = id;
	}
}
