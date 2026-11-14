// @ts-nocheck -- AudioWorkletGlobalScope (sampleRate, registerProcessor) has no TypeScript lib.
/**
 * AudioWorklet: microphone audio at the context's rate (often 44.1 or 48 kHz) to
 * 16 kHz 16-bit mono PCM for /voice/ws (technical-plan.md §7.1, §9.3).
 *
 * Each output sample is the average of the input samples it covers (a box filter,
 * enough against aliasing for speech). Every 20 ms it posts
 * `{ pcm: ArrayBuffer, level: number }` to the main thread, with `level` the RMS of
 * the chunk between 0 and 1. Plain JavaScript, loaded with `addModule`.
 */
const OUT_RATE = 16000;
const CHUNK = 320; // 20 ms at 16 kHz

class CaptureProcessor extends AudioWorkletProcessor {
	constructor() {
		super();
		this.ratio = sampleRate / OUT_RATE;
		this.position = 0;
		this.sum = 0;
		this.count = 0;
		this.out = new Int16Array(CHUNK);
		this.filled = 0;
		this.energy = 0;
	}

	process(inputs) {
		const input = inputs[0] && inputs[0][0];
		if (!input) return true;
		for (let i = 0; i < input.length; i++) {
			this.sum += input[i];
			this.count++;
			this.position += 1;
			if (this.position >= this.ratio) {
				this.position -= this.ratio;
				this.emit(this.sum / this.count);
				this.sum = 0;
				this.count = 0;
			}
		}
		return true;
	}

	emit(sample) {
		const clamped = Math.max(-1, Math.min(1, sample));
		this.out[this.filled++] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
		this.energy += clamped * clamped;
		if (this.filled === CHUNK) {
			const level = Math.sqrt(this.energy / CHUNK);
			const pcm = this.out.buffer;
			this.port.postMessage({ pcm, level }, [pcm]);
			this.out = new Int16Array(CHUNK);
			this.filled = 0;
			this.energy = 0;
		}
	}
}

registerProcessor('simo-capture', CaptureProcessor);
