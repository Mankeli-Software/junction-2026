/**
 * One call with S.I.MO over `/voice/ws` (technical-plan.md §9.3): microphone up as
 * binary 16 kHz PCM, agent audio down as binary 24 kHz PCM, JSON messages both ways.
 * The call screen renders this object's state.
 */
import {
	CLOSE_LIMIT,
	CLOSE_NO_SESSION,
	type AgentState,
	type EndedMessage,
	type ServerMessage,
	type TranscriptMessage
} from '#lib/demo/types.js';
import { AudioError, createAudioContext, startCallAudio, type CallAudio } from './audio.js';
import { keepScreenAwake } from './wake-lock.js';

export type CallPhase = 'connecting' | 'live' | 'ended' | 'failed';
export type CallError = 'mic_denied' | 'unsupported' | 'cannot_connect' | 'limit' | 'no_session';

export interface Caption {
	id: number;
	who: 'buyer' | 'agent';
	text: string;
	final: boolean;
	/** The caller is talking and their caption hasn't arrived yet ("Listening..."). */
	pending: boolean;
}

/** Local level above which the caller counts as talking (RMS, 0 to 1). */
const TALK_LEVEL = 0.02;
const TALK_HANGOVER_MS = 700;
/** How long a "Listening..." caption waits for the caller's words before it goes. */
const PENDING_TIMEOUT_MS = 4000;
const CONNECT_TIMEOUT_MS = 10_000;

export function voiceSocketUrl(): string {
	return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/voice/ws`;
}

export class VoiceCall {
	phase = $state<CallPhase>('connecting');
	error = $state<CallError | null>(null);
	captions = $state<Caption[]>([]);
	muted = $state(false);
	speaker = $state(true);
	/** Agent audio is queued for playback. */
	agentSpeaking = $state(false);
	/** The relay's last `agent_state`; null while the relay never sent one. */
	agentState = $state<AgentState | null>(null);
	agentTool = $state<string | null>(null);
	callerTalking = $state(false);
	wakeLock = $state(false);
	startedAt = $state<number | null>(null);
	endedAt = $state<number | null>(null);
	/** The relay's `ended` message; null when the call dropped without one. */
	ended = $state<EndedMessage | null>(null);

	#socket: WebSocket | null = null;
	#audio: CallAudio | null = null;
	#releaseWakeLock: (() => void) | null = null;
	#nextId = 1;
	#lastTalk = 0;
	#talkTimer: ReturnType<typeof setTimeout> | null = null;
	#pendingTimer: ReturnType<typeof setTimeout> | null = null;
	#connectTimer: ReturnType<typeof setTimeout> | null = null;

	/** The socket closed mid-call without `ended`. */
	lostConnection = $state(false);

	/**
	 * What the indicator shows. `agent_state` wins when the relay sends it; without it,
	 * speaking while agent audio plays and listening otherwise. The relay says
	 * `listening` when Gemini has finished generating, which can be before the
	 * browser has finished playing, so queued audio still shows as speaking.
	 */
	get activity(): AgentState {
		if (this.agentState === null || this.agentState === 'listening') {
			return this.agentSpeaking ? 'speaking' : 'listening';
		}
		return this.agentState;
	}

	get dropped(): boolean {
		return this.lostConnection || this.ended?.ended_by === 'dropped';
	}

	/** Starts the call. Call it straight from the tap on Call (audio needs the gesture). */
	async start(url = voiceSocketUrl()): Promise<void> {
		let context: AudioContext;
		try {
			context = createAudioContext();
		} catch {
			return this.#fail('unsupported');
		}
		this.#releaseWakeLock = keepScreenAwake((held) => (this.wakeLock = held));

		try {
			this.#audio = await startCallAudio(context, {
				onChunk: (pcm, level) => this.#onMicrophone(pcm, level),
				onPlaying: (playing) => (this.agentSpeaking = playing)
			});
		} catch (error) {
			void context.close().catch(() => {});
			return this.#fail(error instanceof AudioError ? error.kind : 'unsupported');
		}
		if (this.phase !== 'connecting') {
			// Hung up while the microphone prompt was open.
			void this.#audio.close();
			this.#audio = null;
			return;
		}

		let socket: WebSocket;
		try {
			socket = new WebSocket(url);
		} catch {
			return this.#fail('cannot_connect');
		}
		socket.binaryType = 'arraybuffer';
		this.#socket = socket;
		this.#connectTimer = setTimeout(() => {
			if (this.phase === 'connecting') this.#fail('cannot_connect');
		}, CONNECT_TIMEOUT_MS);

		socket.onmessage = (event: MessageEvent<ArrayBuffer | string>) => {
			if (typeof event.data === 'string') this.#onMessage(event.data);
			else if (this.phase === 'live') this.#audio?.play(event.data);
		};
		socket.onclose = (event) => this.#onClose(event.code);
	}

	hangup(): void {
		if (this.phase === 'connecting') {
			// Nothing to tell the relay yet: the call never started.
			this.#socket?.close(1000);
			this.#finish(null);
			return;
		}
		if (this.phase !== 'live') return;
		if (this.#socket?.readyState === WebSocket.OPEN) {
			this.#socket.send(JSON.stringify({ type: 'hangup' }));
			// The relay answers with `ended` and closes; don't wait forever.
			setTimeout(() => {
				if (this.phase === 'live') this.#socket?.close(1000);
			}, 3000);
		} else {
			this.#finish(null);
		}
	}

	toggleMute(): void {
		this.muted = !this.muted;
		this.#audio?.setMuted(this.muted);
	}

	toggleSpeaker(): void {
		this.speaker = !this.speaker;
		this.#audio?.setSpeaker(this.speaker);
	}

	/** Seconds since the call was answered, at `now`. */
	elapsed(now: number): number {
		if (!this.startedAt) return 0;
		return Math.max(0, ((this.endedAt ?? now) - this.startedAt) / 1000);
	}

	/** Stops everything without telling the relay, for leaving the page. */
	dispose(): void {
		if (this.phase === 'live' && this.#socket?.readyState === WebSocket.OPEN) {
			this.#socket.send(JSON.stringify({ type: 'hangup' }));
		}
		this.#socket?.close(1000);
		this.#cleanup();
	}

	#onMicrophone(pcm: ArrayBuffer, level: number): void {
		if (this.phase === 'live' && this.#socket?.readyState === WebSocket.OPEN) this.#socket.send(pcm);
		if (this.phase !== 'live' || this.muted) return;
		if (level > TALK_LEVEL) {
			this.#lastTalk = performance.now();
			if (!this.callerTalking) this.#startTalking();
		}
	}

	/**
	 * The caller's own caption only arrives when they stop (spikes/gemini-live), so
	 * while they talk the screen shows "Listening..." in their bubble.
	 */
	#startTalking(): void {
		this.callerTalking = true;
		const last = this.captions.at(-1);
		if (!this.agentSpeaking && !(last?.who === 'buyer' && !last.final)) {
			this.captions.push({ id: this.#nextId++, who: 'buyer', text: '', final: false, pending: true });
		}
		const check = () => {
			if (performance.now() - this.#lastTalk >= TALK_HANGOVER_MS) {
				this.callerTalking = false;
				this.#armPendingTimeout();
			} else {
				this.#talkTimer = setTimeout(check, 150);
			}
		};
		this.#talkTimer = setTimeout(check, TALK_HANGOVER_MS);
	}

	#armPendingTimeout(): void {
		if (this.#pendingTimer) clearTimeout(this.#pendingTimer);
		this.#pendingTimer = setTimeout(() => {
			// Nothing came: it was noise, not words.
			this.captions = this.captions.filter((c) => !(c.pending && !this.callerTalking));
		}, PENDING_TIMEOUT_MS);
	}

	#onMessage(raw: string): void {
		let message: ServerMessage;
		try {
			message = JSON.parse(raw);
		} catch {
			return;
		}
		switch (message.type) {
			case 'ready':
				if (this.#connectTimer) clearTimeout(this.#connectTimer);
				this.phase = 'live';
				this.startedAt = Date.now();
				break;
			case 'interrupted':
				this.#audio?.flush();
				this.agentSpeaking = false;
				if (this.agentState !== null) {
					this.agentState = 'listening';
					this.agentTool = null;
				}
				for (const caption of this.captions) if (caption.who === 'agent') caption.final = true;
				break;
			case 'agent_state':
				this.agentState = message.state;
				this.agentTool = message.state === 'working' ? (message.tool ?? null) : null;
				break;
			case 'transcript':
				this.#onTranscript(message);
				break;
			case 'ended':
				this.#finish(message);
				break;
		}
	}

	#onTranscript(message: TranscriptMessage): void {
		const open = this.captions.findLast((c) => c.who === message.who && !c.final);
		if (open) {
			if (message.final) {
				if (message.text) open.text = message.text;
				open.final = true;
			} else {
				open.text += message.text;
			}
			open.pending = false;
			if (!open.text) this.captions = this.captions.filter((c) => c !== open);
			return;
		}
		if (!message.text.trim()) return;
		this.captions.push({
			id: this.#nextId++,
			who: message.who,
			text: message.text.trimStart(),
			final: message.final,
			pending: false
		});
	}

	#onClose(code: number): void {
		if (this.phase === 'connecting') {
			this.#fail(code === CLOSE_LIMIT ? 'limit' : code === CLOSE_NO_SESSION ? 'no_session' : 'cannot_connect');
		} else if (this.phase === 'live') {
			this.lostConnection = true; // Dropped without `ended`.
			this.#finish(null);
		}
	}

	#finish(ended: EndedMessage | null): void {
		if (this.phase === 'ended' || this.phase === 'failed') return;
		this.ended = ended;
		this.endedAt = Date.now();
		this.phase = 'ended';
		this.#cleanup();
	}

	#fail(error: CallError): void {
		this.error = error;
		this.phase = 'failed';
		this.#cleanup();
	}

	#cleanup(): void {
		for (const timer of [this.#talkTimer, this.#pendingTimer, this.#connectTimer]) if (timer) clearTimeout(timer);
		this.callerTalking = false;
		this.agentSpeaking = false;
		this.agentState = null;
		this.agentTool = null;
		this.captions = this.captions.filter((c) => !c.pending);
		for (const caption of this.captions) caption.final = true;
		if (this.#socket) {
			this.#socket.onmessage = null;
			this.#socket.onclose = null;
			if (this.#socket.readyState === WebSocket.OPEN) this.#socket.close(1000);
		}
		void this.#audio?.close();
		this.#audio = null;
		this.#releaseWakeLock?.();
		this.#releaseWakeLock = null;
		this.wakeLock = false;
	}
}
