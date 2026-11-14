import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import type { Plugin } from 'vite';
import { defineConfig } from 'vitest/config';
import { attachMockRelay } from './src/lib/server/demo/relay.ts';

/**
 * DEMO_SOURCE=fixture (the default in `pnpm dev`): `/voice/ws` is the mock relay,
 * attached to Vite's own server. `vite preview` serves a build, which defaults to
 * the API, so there the relay is attached only when DEMO_SOURCE=fixture is set.
 * DEMO_SOURCE=api: `/voice` goes to FastAPI at API_BASE_URL, as Caddy does on the
 * VM (src/lib/server/demo/index.ts).
 */
const demoSource = process.env.DEMO_SOURCE || 'fixture';
const previewFixture = process.env.DEMO_SOURCE === 'fixture';
const apiBaseUrl = process.env.API_BASE_URL ?? 'http://localhost:8000';

function mockRelay(): Plugin {
	return {
		name: 'simo-mock-relay',
		configureServer(server) {
			if (server.httpServer) attachMockRelay(server.httpServer as import('node:http').Server);
		},
		configurePreviewServer(server) {
			if (previewFixture) attachMockRelay(server.httpServer as import('node:http').Server);
		}
	};
}

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter()
		}),
		demoSource === 'fixture' ? mockRelay() : null
	],
	server:
		demoSource === 'api' ? { proxy: { '/voice': { target: apiBaseUrl, ws: true, changeOrigin: true } } } : undefined,
	test: {
		// Unit tests only. The Playwright specs in tests/ run with `pnpm test:e2e`.
		include: ['src/**/*.test.ts']
	}
});
