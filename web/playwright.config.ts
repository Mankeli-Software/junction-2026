import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests for the web app. They run against the production build with the
 * confirmation fixture (CONFIRMATION_SOURCE=fixture), so no API or database is needed.
 */
const PORT = 4173;

export default defineConfig({
	testDir: 'tests',
	fullyParallel: true,
	retries: 0,
	reporter: [['list']],
	use: {
		baseURL: `http://localhost:${PORT}`,
		trace: 'retain-on-failure'
	},
	projects: [
		{ name: 'phone', use: { ...devices['Pixel 7'] } },
		{ name: 'laptop', use: { ...devices['Desktop Chrome'] } }
	],
	webServer: {
		command: 'pnpm build && node build',
		port: PORT,
		reuseExistingServer: false,
		env: {
			PORT: String(PORT),
			ORIGIN: `http://localhost:${PORT}`,
			CONFIRMATION_SOURCE: 'fixture'
		}
	}
});
