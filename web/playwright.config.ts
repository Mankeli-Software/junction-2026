import { defineConfig, devices } from '@playwright/test';
import { writeFakeVoice } from './tests/support/fake-voice';

/**
 * End-to-end tests for the web app. They run against the production build with the
 * fixtures (CONFIRMATION_SOURCE=fixture, DEMO_SOURCE=fixture) and the mock voice
 * relay on /voice/ws (mock/serve.ts), so no API, database or Gemini is needed.
 *
 * With E2E_API_URL set, the confirmation page reads that FastAPI instead
 * (CONFIRMATION_SOURCE=api), for tests/confirmation-api.spec.ts only.
 *
 * Chromium gets a fake microphone that plays a speech-like WAV file, and the
 * microphone prompt is accepted automatically, so the call works headless.
 */
const PORT = 4173;
const E2E_API_URL = process.env.E2E_API_URL;

export default defineConfig({
	testDir: 'tests',
	fullyParallel: true,
	retries: 0,
	reporter: [['list']],
	use: {
		baseURL: `http://localhost:${PORT}`,
		trace: 'retain-on-failure',
		launchOptions: {
			args: [
				'--use-fake-ui-for-media-stream',
				'--use-fake-device-for-media-stream',
				`--use-file-for-fake-audio-capture=${writeFakeVoice()}`,
				'--autoplay-policy=no-user-gesture-required'
			]
		}
	},
	projects: [
		{ name: 'phone', use: { ...devices['Pixel 7'] } },
		{ name: 'laptop', use: { ...devices['Desktop Chrome'] } }
	],
	webServer: {
		command: 'pnpm build && node mock/serve.ts',
		port: PORT,
		reuseExistingServer: false,
		env: {
			PORT: String(PORT),
			ORIGIN: `http://localhost:${PORT}`,
			CONFIRMATION_SOURCE: E2E_API_URL ? 'api' : 'fixture',
			...(E2E_API_URL ? { API_BASE_URL: E2E_API_URL } : {}),
			DEMO_SOURCE: 'fixture'
		}
	}
});
