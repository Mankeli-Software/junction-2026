/**
 * Live updates for the order pages (summary, full flow, audit log).
 *
 * Steps and transcript lines for this session are handed to the page as they arrive, so the
 * timeline and the chain grow at once. Everything else (the summary, the full event records)
 * is refreshed by rerunning the page's `load` shortly after the last change.
 */
import { refreshAll } from '$app/navigation';
import { connectStream } from './live.svelte';
import type { Step, TranscriptLine } from './types';

export interface SessionLiveHandlers {
	onStep?: (step: Step) => void;
	onTranscript?: (line: TranscriptLine) => void;
	/** A later snapshot: the stream reconnected or (in the mock) the world reset. */
	onReset?: () => void;
}

const REFRESH_DELAY_MS = 800;

/** Call during component init. Reconnects when the session id changes. */
export function sessionLive(getSessionId: () => string, handlers: SessionLiveHandlers): void {
	$effect(() => {
		const sessionId = getSessionId();
		let firstSnapshot = true;
		let timer: ReturnType<typeof setTimeout> | undefined;
		const refreshSoon = () => {
			clearTimeout(timer);
			timer = setTimeout(() => refreshAll(), REFRESH_DELAY_MS);
		};

		const live = connectStream({ state: null, channel: null }, (message) => {
			switch (message.event) {
				case 'snapshot':
					if (!firstSnapshot) {
						handlers.onReset?.();
						refreshSoon();
					}
					firstSnapshot = false;
					break;
				case 'order_updated':
					if (message.data.order.session_id === sessionId) refreshSoon();
					break;
				case 'step':
					if (message.data.session_id === sessionId) {
						handlers.onStep?.(message.data.step);
						refreshSoon();
					}
					break;
				case 'transcript':
					if (message.data.session_id === sessionId) handlers.onTranscript?.(message.data.line);
					break;
			}
		});

		return () => {
			clearTimeout(timer);
			live.close();
		};
	});
}
