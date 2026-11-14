/**
 * The confirmation data source for this server, from the environment:
 * - CONFIRMATION_SOURCE=fixture (default until #47 lands): the in-memory fixture.
 * - CONFIRMATION_SOURCE=api: FastAPI at API_BASE_URL (default http://localhost:8000).
 */
import { apiSource } from './api';
import { fixtureSource } from './fixture';
import type { ConfirmationSource } from './source';

export { ConfirmationError } from './source';
export type { ConfirmationSource } from './source';

let source: ConfirmationSource | null = null;

export function confirmationSource(): ConfirmationSource {
	if (source) return source;
	const kind = process.env.CONFIRMATION_SOURCE ?? 'fixture';
	if (kind === 'api') {
		source = apiSource(process.env.API_BASE_URL ?? 'http://localhost:8000');
	} else if (kind === 'fixture') {
		source = fixtureSource;
	} else {
		throw new Error(`CONFIRMATION_SOURCE must be "fixture" or "api", not "${kind}"`);
	}
	return source;
}
