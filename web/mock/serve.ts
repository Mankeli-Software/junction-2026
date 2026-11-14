/**
 * Runs the production build (`node build`) with the mock voice relay on
 * `/voice/ws`, for DEMO_SOURCE=fixture: `pnpm build && pnpm serve:mock`.
 * The Playwright tests use it. Node runs this TypeScript file directly.
 */
import type { Server } from 'node:http';
import { attachMockRelay } from '../src/lib/server/demo/relay.ts';

process.env.DEMO_SOURCE ??= 'fixture';
const build = (await import(new URL('../build/index.js', import.meta.url).href)) as { server: Server };
attachMockRelay(build.server);
