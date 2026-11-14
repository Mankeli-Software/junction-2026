/**
 * In-browser audit chain check for one order (#50, `technical-plan.md` §8.5, §9.5).
 *
 * Recomputes every step's hash with Web Crypto from the public fields only, so it needs
 * no payloads and no login. The server's `/audit/verify` result is not used for this.
 */
import { GENESIS_HASH, computeHash } from './hash';
import type { Step } from './types';

export type BreakReason = 'hash' | 'global_link' | 'session_link';

export interface VerifyResult {
	ok: boolean;
	/** Steps recomputed, including the broken one. */
	checked: number;
	first_bad_seq: number | null;
	first_bad_order_index: number | null;
	reason: BreakReason | null;
}

type ChainFields = Pick<
	Step,
	'seq' | 'order_index' | 'at' | 'type' | 'payload_hash' | 'prev_hash' | 'session_prev_hash' | 'hash'
>;

/**
 * For each step in `seq` order:
 * 1. its `hash` must equal the hash recomputed from `prev_hash`, `payload_hash`, `seq`, `at`, `type`;
 * 2. `session_prev_hash` must be the previous step's `hash` (null for the first one);
 * 3. where two steps are next to each other in the global chain (`seq` differs by one),
 *    `prev_hash` must be the previous step's `hash`. Other sessions' events sit in the gaps,
 *    so a gap is fine; the session link covers it. The very first global event links to
 *    `GENESIS_HASH`.
 */
export async function verifyChain(input: readonly ChainFields[]): Promise<VerifyResult> {
	const steps = [...input].sort((a, b) => a.seq - b.seq);
	let previous: ChainFields | null = null;
	let checked = 0;

	for (const step of steps) {
		checked++;
		const fail = (reason: BreakReason): VerifyResult => ({
			ok: false,
			checked,
			first_bad_seq: step.seq,
			first_bad_order_index: step.order_index,
			reason
		});

		const recomputed = await computeHash(step);
		if (recomputed !== step.hash.toLowerCase()) return fail('hash');

		if (previous === null) {
			if (step.session_prev_hash !== null && step.session_prev_hash !== GENESIS_HASH) {
				return fail('session_link');
			}
			if (step.seq === 1 && step.prev_hash !== GENESIS_HASH) return fail('global_link');
		} else {
			if (step.session_prev_hash !== previous.hash) return fail('session_link');
			if (step.seq === previous.seq + 1 && step.prev_hash !== previous.hash) {
				return fail('global_link');
			}
		}
		previous = step;
	}

	return { ok: true, checked, first_bad_seq: null, first_bad_order_index: null, reason: null };
}
