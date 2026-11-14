/**
 * Browser audio for the call (technical-plan.md §7.1): the microphone with echo
 * cancellation, downsampled to 16 kHz 16-bit mono by an AudioWorklet, and a second
 * worklet that plays the agent's 24 kHz PCM and can be flushed on `interrupted`.
 */
import captureUrl from './capture-worklet.js?url&no-inline';
import playbackUrl from './playback-worklet.js?url&no-inline';

export type AudioErrorKind = 'mic_denied' | 'unsupported';

export class AudioError extends Error {
	constructor(readonly kind: AudioErrorKind, cause?: unknown) {
		super(kind, { cause });
	}
}

export interface CallAudio {
	/** Mutes the microphone: the relay then hears silence, like a phone's mute. */
	setMuted(muted: boolean): void;
	/** Turns the agent's voice on or off (captions keep going). */
	setSpeaker(on: boolean): void;
	/** Queues 24 kHz 16-bit mono PCM for playback. */
	play(pcm: ArrayBuffer): void;
	/** Drops queued agent audio (on `interrupted`). */
	flush(): void;
	close(): Promise<void>;
}

export interface CallAudioHandlers {
	/** 20 ms of 16 kHz PCM and its level (RMS, 0 to 1). */
	onChunk(pcm: ArrayBuffer, level: number): void;
	/** The agent's audio started or ran dry. */
	onPlaying(playing: boolean): void;
}

/** True when this browser has everything the call needs. */
export function audioSupported(): boolean {
	return (
		typeof window !== 'undefined' &&
		window.isSecureContext &&
		!!navigator.mediaDevices?.getUserMedia &&
		typeof AudioContext !== 'undefined' &&
		typeof AudioWorkletNode !== 'undefined' &&
		typeof WebSocket !== 'undefined'
	);
}

/**
 * Creates the audio context. Call it straight from the tap on Call, before any
 * `await`, so mobile Safari lets the audio start.
 */
export function createAudioContext(): AudioContext {
	if (!audioSupported()) throw new AudioError('unsupported');
	const context = new AudioContext({ latencyHint: 'interactive' });
	void context.resume();
	return context;
}

/** Asks for the microphone (the browser's own prompt) and wires both worklets. */
export async function startCallAudio(context: AudioContext, handlers: CallAudioHandlers): Promise<CallAudio> {
	let stream: MediaStream;
	try {
		stream = await navigator.mediaDevices.getUserMedia({
			audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 }
		});
	} catch (error) {
		const name = error instanceof DOMException ? error.name : '';
		throw new AudioError(name === 'NotAllowedError' || name === 'SecurityError' ? 'mic_denied' : 'unsupported', error);
	}

	try {
		await Promise.all([context.audioWorklet.addModule(captureUrl), context.audioWorklet.addModule(playbackUrl)]);
	} catch (error) {
		stream.getTracks().forEach((track) => track.stop());
		throw new AudioError('unsupported', error);
	}
	await context.resume();

	const source = context.createMediaStreamSource(stream);
	const capture = new AudioWorkletNode(context, 'simo-capture', { numberOfInputs: 1, numberOfOutputs: 0 });
	capture.port.onmessage = (event: MessageEvent<{ pcm: ArrayBuffer; level: number }>) =>
		handlers.onChunk(event.data.pcm, event.data.level);
	source.connect(capture);

	const playback = new AudioWorkletNode(context, 'simo-playback', {
		numberOfInputs: 0,
		numberOfOutputs: 1,
		outputChannelCount: [1]
	});
	playback.port.onmessage = (event: MessageEvent<{ playing: boolean }>) => handlers.onPlaying(event.data.playing);
	const volume = context.createGain();
	playback.connect(volume).connect(context.destination);

	return {
		setMuted(muted) {
			for (const track of stream.getAudioTracks()) track.enabled = !muted;
		},
		setSpeaker(on) {
			volume.gain.setTargetAtTime(on ? 1 : 0, context.currentTime, 0.02);
		},
		play(pcm) {
			playback.port.postMessage(pcm, [pcm]);
		},
		flush() {
			playback.port.postMessage('flush');
		},
		async close() {
			stream.getTracks().forEach((track) => track.stop());
			source.disconnect();
			capture.port.onmessage = null;
			playback.port.onmessage = null;
			playback.disconnect();
			if (context.state !== 'closed') await context.close().catch(() => {});
		}
	};
}
