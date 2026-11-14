/**
 * Where the confirmation page gets its data. Two implementations:
 * - `fixture`: an in-memory stand-in for the engine, used until the FastAPI
 *   endpoints (#47) exist, and by the Playwright tests.
 * - `api`: the FastAPI endpoints from technical-plan.md §9.4.
 * Pick one with the CONFIRMATION_SOURCE environment variable.
 */
import type { ConfirmationView, EditOp, Text } from '#lib/confirmation/types.js';

export interface ConfirmationSource {
	/** Returns null for an unknown or invalid token. Never uses the token up. */
	get(token: string): Promise<ConfirmationView | null>;
	acknowledge(token: string, quoteHash: string, flagKey: string): Promise<void>;
	edit(token: string, quoteHash: string, edit: EditOp): Promise<void>;
	confirm(token: string, quoteHash: string): Promise<void>;
	cancel(token: string, quoteHash: string): Promise<void>;
}

/**
 * An action the engine refused. `status` follows plan §9.4:
 * 404 unknown token, 409 stale quote or availability got worse, 410 expired,
 * 422 a flag is not acknowledged or the edit is not possible.
 */
export class ConfirmationError extends Error {
	constructor(
		readonly status: number,
		readonly text: Text | null = null,
		readonly lineId: string | null = null
	) {
		super(text?.en ?? `Confirmation request failed with ${status}`);
	}
}
