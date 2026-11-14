import { defineConfig, devices } from '@playwright/test';

/**
 * Screenshots of a real call: the phone page against the real voice relay (#52), Gemini
 * Live and FastAPI, for pull requests. Not part of `pnpm test:e2e`, which runs on the
 * mocks. Each run opens one Gemini Live session per project, so run it rarely.
 *
 * Needs a running stack: FastAPI with Postgres, a catalogue and GEMINI_API_KEY, and the web
 * dev server with DEMO_SOURCE=api and CONFIRMATION_SOURCE=api at VOICE_LIVE_BASE_URL. The
 * caller is a WAV file for Chromium's fake microphone, written by
 * `scripts/voice_smoke_test.py --browser-wav <file>`:
 *
 *   SCREENSHOTS=1 VOICE_LIVE_AUDIO=<file> VOICE_LIVE_BASE_URL=http://localhost:5173 \
 *     pnpm exec playwright test -c playwright.voice-live.config.ts --project phone
 */
const audio = process.env.VOICE_LIVE_AUDIO ?? '';

export default defineConfig({
	testDir: 'tests',
	testMatch: 'voice-live-screenshots.spec.ts',
	retries: 0,
	reporter: [['list']],
	use: {
		baseURL: process.env.VOICE_LIVE_BASE_URL ?? 'http://localhost:5173',
		trace: 'retain-on-failure',
		launchOptions: {
			args: [
				'--use-fake-ui-for-media-stream',
				'--use-fake-device-for-media-stream',
				`--use-file-for-fake-audio-capture=${audio}`,
				'--autoplay-policy=no-user-gesture-required'
			]
		}
	},
	projects: [
		{ name: 'phone', use: { ...devices['Pixel 7'] } },
		{ name: 'laptop', use: { ...devices['Desktop Chrome'] } }
	]
});
