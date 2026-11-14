/**
 * Runs the production build (`node build`) with the fixtures and the mock voice
 * relay on `/voice/ws`: `pnpm build && pnpm serve:mock`. A build defaults to the
 * API, so this opts in to DEMO_SOURCE=fixture and CONFIRMATION_SOURCE=fixture unless
 * they are set. The Playwright tests use it. Node runs this TypeScript file directly.
 */
import type { Server } from 'node:http';
import { attachMockRelay } from '../src/lib/server/demo/relay.ts';

process.env.DEMO_SOURCE ||= 'fixture';
process.env.CONFIRMATION_SOURCE ||= 'fixture';
if (process.env.DEMO_SOURCE !== 'fixture') throw new Error('serve:mock needs DEMO_SOURCE=fixture');
const build = (await import(new URL('../build/index.js', import.meta.url).href)) as { server: Server };
attachMockRelay(build.server);
