/**
 * SSE `GET /api/v1/private/inbox/stream` (technical-plan.md §9.2): new messages for
 * the simulated phone, as `inbox_message` events with the message as JSON.
 */
import { json } from '@sveltejs/kit';
import { demoSource, proxyToApi } from '#lib/server/demo/index.js';
import { inbox, SESSION_COOKIE, subscribe } from '#lib/server/demo/fixture.js';
import type { RequestHandler } from './$types';

const PING_MS = 15_000;

export const GET: RequestHandler = async (event) => {
	if (demoSource() === 'api') return proxyToApi(event);
	const sessionId = event.cookies.get(SESSION_COOKIE);
	if (!sessionId || !inbox(sessionId)) return json({ detail: 'Not signed in' }, { status: 401 });

	const encoder = new TextEncoder();
	let close = () => {};
	const stream = new ReadableStream<Uint8Array>({
		start(controller) {
			const write = (text: string) => {
				try {
					controller.enqueue(encoder.encode(text));
				} catch {
					close();
				}
			};
			const unsubscribe = subscribe(sessionId, (message) =>
				write(`event: inbox_message\nid: ${message.id}\ndata: ${JSON.stringify(message)}\n\n`)
			);
			const ping = setInterval(() => write(': ping\n\n'), PING_MS);
			close = () => {
				unsubscribe();
				clearInterval(ping);
			};
			event.request.signal.addEventListener('abort', () => {
				close();
				try {
					controller.close();
				} catch {
					// Already closed.
				}
			});
			write(': open\n\n');
		},
		cancel() {
			close();
		}
	});

	return new Response(stream, {
		headers: {
			'content-type': 'text/event-stream',
			'cache-control': 'no-store',
			'x-accel-buffering': 'no'
		}
	});
};
