/**
 * A WAV file for Chromium's fake microphone (`--use-file-for-fake-audio-capture`),
 * so the call tests have a caller who talks: 3.5 s of silence, then 1.2 s of a
 * speech-like hum, over and over. The mock relay hears each hum as one utterance.
 * The silence is long enough for each scripted agent reply (at most 2.4 s) to
 * finish before the caller talks again, so the agent is not interrupted.
 */
import { writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const RATE = 48000;
export const SILENCE_S = 3.5;
export const VOICE_S = 1.2;

export function writeFakeVoice(): string {
	const silence = Math.round(SILENCE_S * RATE);
	const voice = Math.round(VOICE_S * RATE);
	const samples = silence + voice;
	const data = Buffer.alloc(samples * 2);
	let phase = 0;
	for (let i = 0; i < voice; i++) {
		const t = i / RATE;
		phase += (2 * Math.PI * (180 + 25 * Math.sin(2 * Math.PI * 1.3 * t))) / RATE;
		const tone = Math.sin(phase) + 0.6 * Math.sin(2 * phase) + 0.4 * Math.sin(3 * phase) + 0.2 * Math.sin(4 * phase);
		// Syllables, never fully silent, so the voice doesn't break up into pieces.
		const syllable = 0.55 + 0.45 * Math.abs(Math.sin(Math.PI * 3.5 * t));
		const fade = Math.min(1, t / 0.02, (VOICE_S - t) / 0.02);
		data.writeInt16LE(Math.round(tone * syllable * fade * 0.22 * 32767), (silence + i) * 2);
	}
	const header = Buffer.alloc(44);
	header.write('RIFF', 0);
	header.writeUInt32LE(36 + data.length, 4);
	header.write('WAVE', 8);
	header.write('fmt ', 12);
	header.writeUInt32LE(16, 16);
	header.writeUInt16LE(1, 20); // PCM
	header.writeUInt16LE(1, 22); // mono
	header.writeUInt32LE(RATE, 24);
	header.writeUInt32LE(RATE * 2, 28);
	header.writeUInt16LE(2, 32);
	header.writeUInt16LE(16, 34);
	header.write('data', 36);
	header.writeUInt32LE(data.length, 40);
	const path = join(tmpdir(), 'simo-fake-voice.wav');
	writeFileSync(path, Buffer.concat([header, data]));
	return path;
}
