// @ts-nocheck -- AudioWorkletGlobalScope (sampleRate, registerProcessor) has no TypeScript lib.
/**
 * AudioWorklet: plays the agent's 24 kHz 16-bit mono PCM from /voice/ws at the
 * context's rate, with linear interpolation (technical-plan.md §7.1, §9.3).
 *
 * Messages from the main thread:
 * - an ArrayBuffer of PCM: queued for playback;
 * - `'flush'`: drops everything queued, so the caller can talk over the agent
 *   (sent on `interrupted`).
 * It posts `{ playing: boolean }` when playback starts or runs dry, for the
 * speaking indicator. Plain JavaScript, loaded with `addModule`.
 */
const IN_RATE = 24000;
const CAPACITY = IN_RATE * 120; // two minutes of queued speech

class PlaybackProcessor extends AudioWorkletProcessor {
	constructor() {
		super();
		this.buffer = new Float32Array(CAPACITY);
		this.written = 0; // samples written, ever
		this.read = 0; // read position in input samples, fractional
		this.step = IN_RATE / sampleRate;
		this.playing = false;
		this.port.onmessage = (event) => {
			if (event.data === 'flush') {
				this.read = this.written;
				this.setPlaying(false);
				return;
			}
			const pcm = new Int16Array(event.data);
			for (let i = 0; i < pcm.length; i++) {
				this.buffer[this.written % CAPACITY] = pcm[i] / 0x8000;
				this.written++;
			}
			// If the queue overflowed, skip to the oldest sample still there.
			if (this.written - this.read > CAPACITY) this.read = this.written - CAPACITY;
		};
	}

	setPlaying(playing) {
		if (playing !== this.playing) {
			this.playing = playing;
			this.port.postMessage({ playing });
		}
	}

	process(_inputs, outputs) {
		const out = outputs[0] && outputs[0][0];
		if (!out) return true;
		for (let i = 0; i < out.length; i++) {
			if (this.read + 1 >= this.written) {
				out[i] = 0;
				continue;
			}
			const index = Math.floor(this.read);
			const fraction = this.read - index;
			const a = this.buffer[index % CAPACITY];
			const b = this.buffer[(index + 1) % CAPACITY];
			out[i] = a + (b - a) * fraction;
			this.read += this.step;
		}
		this.setPlaying(this.read + 1 < this.written);
		return true;
	}
}

registerProcessor('simo-playback', PlaybackProcessor);
