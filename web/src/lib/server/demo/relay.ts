/**
 * Mock voice relay for `/voice/ws` (technical-plan.md §9.3), used with
 * DEMO_SOURCE=fixture until the real Gemini Live relay (#52) exists.
 *
 * It speaks the same protocol as the real relay:
 * - takes binary frames of 16 kHz 16-bit mono PCM from the browser;
 * - sends `ready`, then scripted agent turns as 24 kHz 16-bit mono PCM (a
 *   speech-like hum) with `transcript` messages for both sides;
 * - notices the caller speaking from the audio level, and sends `interrupted`
 *   when the caller talks over the agent;
 * - sends `agent_state` as S.I.MO listens, thinks (about 0.8 s after each caller
 *   line), works on a tool (`build_quote` when the order is put together,
 *   `request_confirmation` before the link) and speaks;
 * - on `hangup` (or when the agent ends the call, or the socket drops) sends
 *   `ended` and, if the caller agreed to the link, drops a message with a
 *   `/c/fx-ready-<id>` link into the fixture inbox.
 *
 * The caller's words are not recognised: each time the caller says something, the
 * next scripted line is shown as their caption. The caller agrees to the link on
 * their second turn, like `request_confirmation` after a clear yes.
 *
 * With the cookie `simo_mock_agent_state=off`, it never sends `agent_state`, like a
 * relay without it, so tests can check the browser's fallback.
 *
 * Attached to the HTTP server by vite.config.ts (dev and preview) and by
 * mock/serve.ts (the production build). Not part of the SvelteKit app.
 * Imports use `.ts` so Node can load this file directly.
 */
import type { IncomingMessage, Server } from 'node:http';
import type { Duplex } from 'node:stream';
import { WebSocketServer, type RawData, type WebSocket } from 'ws';
import {
	CLOSE_LIMIT,
	CLOSE_NO_SESSION,
	type AgentState,
	type EndedBy,
	type Lang,
	type ServerMessage
} from '../../demo/types.ts';
import { accountFor, deliverConfirmation, SESSION_COOKIE } from './fixture.ts';

const IN_RATE = 16000;
const OUT_RATE = 24000;
const CHUNK_MS = 100;
/** Int16 RMS above this counts as the caller's voice. */
const VOICE_RMS = 500;
/** Voice this long starts an utterance; silence this long ends it. */
const ONSET_MS = 150;
const END_SILENCE_MS = 600;
const MAX_CALL_MS = 10 * 60 * 1000;
/** S.I.MO thinks this long after each caller line, and briefly again after a tool result. */
const THINK_MS = 800;
const AFTER_TOOL_MS = 200;
const AGENT_STATE_COOKIE = 'simo_mock_agent_state';

interface Turn {
	buyer: string;
	agent: string;
	agrees?: boolean;
	endsCall?: boolean;
	/** A tool S.I.MO calls before it answers, and how long it takes. */
	tool?: { name: string; ms: number };
}

const SCRIPT: Record<Lang, { greeting: (company: string) => string; turns: Turn[]; more: Turn }> = {
	en: {
		greeting: (company) => `Hi ${company}! I'm S.I.MO, Valio Aimo's AI helper. What can I get you?`,
		turns: [
			{
				buyer: 'I need five kilos of ground beef for Monday.',
				agent: 'Beef mince 10 %, two 2.5 kg packs, 41,90 euros, arriving Monday. Shall I send the link to confirm?',
				tool: { name: 'build_quote', ms: 1500 }
			},
			{
				buyer: 'Yes, send it.',
				agent: 'Done. The link comes to your phone when we hang up. Anything else?',
				agrees: true,
				tool: { name: 'request_confirmation', ms: 800 }
			},
			{ buyer: "No, that's all.", agent: "I'll send the link to your phone now. Bye!", endsCall: true }
		],
		more: { buyer: 'Hmm, one more thing.', agent: 'Sure, go ahead.' }
	},
	fi: {
		greeting: (company) => `Hei ${company}! Olen S.I.MO, Valio Aimon tekoälyavustaja. Mitä saisi olla?`,
		turns: [
			{
				buyer: 'Tarvitsen viisi kiloa jauhelihaa maanantaiksi.',
				agent: 'Naudan jauheliha 10 %, kaksi 2,5 kilon pakkausta, 41,90 euroa, perillä maanantaina. Lähetänkö vahvistuslinkin?',
				tool: { name: 'build_quote', ms: 1500 }
			},
			{
				buyer: 'Kyllä, lähetä.',
				agent: 'Selvä. Linkki tulee puhelimeesi, kun lopetamme puhelun. Muuta?',
				agrees: true,
				tool: { name: 'request_confirmation', ms: 800 }
			},
			{ buyer: 'Ei muuta.', agent: 'Lähetän linkin puhelimeesi nyt. Hei hei!', endsCall: true }
		],
		more: { buyer: 'Vielä yksi asia.', agent: 'Kerro vain.' }
	}
};

export function attachMockRelay(server: Server, path = '/voice/ws'): void {
	const wss = new WebSocketServer({ noServer: true });
	server.on('upgrade', (request: IncomingMessage, socket: Duplex, head: Buffer) => {
		const url = new URL(request.url ?? '/', 'http://localhost');
		if (url.pathname !== path) return; // Vite's own HMR socket and anything else.
		const sendStates = cookie(request, AGENT_STATE_COOKIE) !== 'off';
		wss.handleUpgrade(request, socket, head, (ws) => runCall(ws, cookie(request, SESSION_COOKIE), sendStates));
	});
}

function cookie(request: IncomingMessage, wanted: string): string | null {
	for (const part of (request.headers.cookie ?? '').split(';')) {
		const [name, ...value] = part.trim().split('=');
		if (name === wanted) return decodeURIComponent(value.join('='));
	}
	return null;
}

function runCall(ws: WebSocket, sessionId: string | null, sendStates: boolean): void {
	const account = accountFor(sessionId);
	if (!sessionId || !account) {
		ws.close(CLOSE_NO_SESSION, 'No demo session');
		return;
	}
	if (account.phone.endsWith('0429')) {
		ws.close(CLOSE_LIMIT, 'Demo limit reached');
		return;
	}
	const script = SCRIPT[account.lang];
	const startedAt = Date.now();
	let ended = false;
	let agreed = false;
	let buyerTurns = 0;
	const timers = new Set<ReturnType<typeof setTimeout>>();

	// The agent's current turn, if it is speaking.
	let speech: { words: string[]; sent: number; stop: () => void } | null = null;

	// Caller voice detection.
	let onsetMs = 0;
	let inUtterance = false;
	let silenceMs = 0;

	const send = (message: ServerMessage) => {
		if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(message));
	};
	const later = (ms: number, fn: () => void) => {
		const timer = setTimeout(() => {
			timers.delete(timer);
			if (!ended) fn();
		}, ms);
		timers.add(timer);
	};

	// `agent_state`, sent only when it changes.
	let agentState: AgentState | null = null;
	let agentTool: string | null = null;
	const setState = (state: AgentState, tool: string | null = null) => {
		if (!sendStates || (state === agentState && tool === agentTool)) return;
		agentState = state;
		agentTool = tool;
		send({ type: 'agent_state', state, tool });
	};

	function speak(text: string, after?: () => void): void {
		const words = text.split(' ');
		const durationMs = Math.min(2000, Math.max(1000, words.length * 150));
		const pcm = speechLike(durationMs / 1000);
		const bytesPerChunk = (OUT_RATE * 2 * CHUNK_MS) / 1000;
		let offset = 0;
		let elapsed = 0;
		const current = {
			words,
			sent: 0,
			stop: () => clearInterval(interval)
		};
		speech = current;
		const interval = setInterval(() => {
			if (ended || ws.readyState !== ws.OPEN) return clearInterval(interval);
			if (offset < pcm.length) {
				if (offset === 0) setState('speaking');
				ws.send(pcm.subarray(offset, offset + bytesPerChunk));
				offset += bytesPerChunk;
			}
			elapsed += CHUNK_MS;
			// Captions keep pace with the audio, one word at a time.
			const due = Math.min(words.length, Math.ceil((elapsed / durationMs) * words.length));
			while (current.sent < due) {
				send({ type: 'transcript', who: 'agent', text: (current.sent ? ' ' : '') + words[current.sent], final: false });
				current.sent++;
			}
			if (offset >= pcm.length && current.sent >= words.length) {
				clearInterval(interval);
				send({ type: 'transcript', who: 'agent', text, final: true });
				speech = null;
				setState('listening');
				after?.();
			}
		}, CHUNK_MS);
	}

	function interrupt(): void {
		if (!speech) return;
		speech.stop();
		send({ type: 'interrupted' });
		setState('listening');
		send({ type: 'transcript', who: 'agent', text: speech.words.slice(0, speech.sent).join(' '), final: true });
		speech = null;
	}

	function onUtterance(): void {
		const turn = script.turns[buyerTurns] ?? script.more;
		buyerTurns++;
		send({ type: 'transcript', who: 'buyer', text: turn.buyer, final: true });
		if (turn.agrees) agreed = true;
		const answer = () => speak(turn.agent, turn.endsCall ? () => later(400, () => finish('agent')) : undefined);
		setState('thinking');
		later(THINK_MS, () => {
			if (!turn.tool) return answer();
			const tool = turn.tool;
			setState('working', tool.name);
			later(tool.ms, () => {
				setState('thinking'); // The tool result went back to Gemini.
				later(AFTER_TOOL_MS, answer);
			});
		});
	}

	function onAudio(data: Buffer): void {
		const samples = Math.floor(data.length / 2);
		if (samples === 0) return;
		let sum = 0;
		for (let i = 0; i < samples; i++) {
			const value = data.readInt16LE(i * 2);
			sum += value * value;
		}
		const frameMs = (samples / IN_RATE) * 1000;
		const voice = Math.sqrt(sum / samples) > VOICE_RMS;
		if (!inUtterance) {
			onsetMs = voice ? onsetMs + frameMs : Math.max(0, onsetMs - frameMs / 2);
			if (onsetMs >= ONSET_MS) {
				inUtterance = true;
				silenceMs = 0;
				interrupt(); // The caller talks over the agent.
			}
			return;
		}
		silenceMs = voice ? 0 : silenceMs + frameMs;
		if (silenceMs >= END_SILENCE_MS) {
			inUtterance = false;
			onsetMs = 0;
			onUtterance();
		}
	}

	function finish(by: EndedBy): void {
		if (ended) return;
		speech?.stop();
		speech = null;
		ended = true;
		for (const timer of timers) clearTimeout(timer);
		const delivery = agreed ? deliverConfirmation(sessionId!) : null;
		send({
			type: 'ended',
			duration_s: Math.round((Date.now() - startedAt) / 1000),
			ended_by: by,
			quote_id: delivery?.quoteId ?? null,
			total_cents: delivery?.totalCents ?? null,
			delivery_status: delivery?.deliveryStatus ?? 'none',
			inbox: delivery !== null
		});
		if (ws.readyState === ws.OPEN) ws.close(1000, 'Call ended');
	}

	ws.on('message', (data: RawData, isBinary: boolean) => {
		if (ended) return;
		if (isBinary) return onAudio(toBuffer(data));
		try {
			const message = JSON.parse(data.toString());
			if (message?.type === 'hangup') finish('visitor');
		} catch {
			// Not JSON: ignore, like the real relay would.
		}
	});
	ws.on('close', () => finish('dropped'));

	later(300, () => {
		send({ type: 'ready' });
		setState('listening');
		later(200, () => speak(script.greeting(account.company_name)));
	});
	later(MAX_CALL_MS, () => finish('time_limit'));
}

function toBuffer(data: RawData): Buffer {
	if (Buffer.isBuffer(data)) return data;
	if (Array.isArray(data)) return Buffer.concat(data);
	return Buffer.from(data);
}

/** A hum with a voice's pitch and syllable rhythm, as 24 kHz 16-bit little-endian PCM. */
function speechLike(seconds: number): Buffer {
	const count = Math.floor(seconds * OUT_RATE);
	const out = Buffer.alloc(count * 2);
	let phase = 0;
	for (let i = 0; i < count; i++) {
		const t = i / OUT_RATE;
		const pitch = 150 + 20 * Math.sin(2 * Math.PI * 0.7 * t) + 10 * Math.sin(2 * Math.PI * 3.1 * t);
		phase += (2 * Math.PI * pitch) / OUT_RATE;
		const tone = Math.sin(phase) + 0.5 * Math.sin(2 * phase) + 0.3 * Math.sin(3 * phase) + 0.15 * Math.sin(5 * phase);
		const syllable = Math.pow(Math.abs(Math.sin(Math.PI * 4.2 * t)), 0.6);
		const fade = Math.min(1, t / 0.03, (seconds - t) / 0.05);
		out.writeInt16LE(Math.round(tone * syllable * fade * 0.18 * 32767 * 0.5), i * 2);
	}
	return out;
}
