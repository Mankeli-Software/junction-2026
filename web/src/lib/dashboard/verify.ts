/**
 * In-browser audit chain check (#50, `docs/audit-chain.md` "Checking", `technical-plan.md` §8.5).
 *
 * Recomputes every step's hash with Web Crypto from the public fields, the same five steps
 * as the API's `verify_chain` (`api/app/services/audit/chain.py`). The server's
 * `/audit/verify` result is not used for this.
 */
import { GENESIS_HASH, computeHash, payloadHash, type ChainFields } from './hash';
import type { AuditEvent, Step } from './types';

/** The same names as `ChainCheck.reason` in the Python. */
export type BreakReason = 'seq_gap' | 'prev_hash' | 'session_prev_hash' | 'payload_hash' | 'hash';

export interface VerifyResult {
	ok: boolean;
	/** Steps checked, including the broken one. */
	checked: number;
	first_bad_seq: number | null;
	first_bad_order_index: number | null;
	reason: BreakReason | null;
}

/**
 * `session`: one session's events, with the other sessions' events in the gaps (the order
 * pages). `global`: the whole chain from `seq` 1.
 */
export type VerifyScope = 'session' | 'global';

export interface CheckedStep extends ChainFields {
	order_index: number;
	hash: string;
	/**
	 * From `/events`: when the payload and both raw sentences are there, `payload_hash` is
	 * checked against them. Not `Step.text`, which turns a null sentence into "".
	 */
	payload?: unknown;
	text_fi?: string | null;
	text_en?: string | null;
}

/**
 * The steps with each one's payload and raw sentences from `/events`, where that event was
 * loaded, so `verifyChain` checks `payload_hash` too. Steps without one (new over the stream,
 * or `/events` not loaded) are checked on their chain fields alone.
 */
export function withRecords(steps: readonly Step[], events: readonly AuditEvent[]): CheckedStep[] {
	const bySeq = new Map(events.map((e) => [e.seq, e]));
	return steps.map((step) => {
		const event = bySeq.get(step.seq);
		if (!event) return step;
		return { ...step, payload: event.payload, text_fi: event.text_fi, text_en: event.text_en };
	});
}

/**
 * For each step in `seq` order, stopping at the first that is wrong:
 * 1. `global` only: `seq` is one more than the previous step's (the first is 1).
 * 2. `prev_hash` is the previous step's `hash`, or `GENESIS_HASH` for `seq` 1. In `session`
 *    scope this applies only where two steps are next to each other in `seq`.
 * 3. `session_prev_hash` is the `hash` of the same session's previous step (null for its first,
 *    and for events with no session).
 * 4. When the payload and sentences are there, `payload_hash` matches them. A deleted
 *    payload (null) is skipped, as `docs/audit-chain.md` allows.
 * 5. `hash` matches the nine fields.
 */
export async function verifyChain(
	input: readonly CheckedStep[],
	scope: VerifyScope = 'session'
): Promise<VerifyResult> {
	const steps = [...input].sort((a, b) => a.seq - b.seq);
	const sessionLast = new Map<string, string>();
	let previous: CheckedStep | null = null;
	let checked = 0;

	for (const step of steps) {
		checked++;
		const reason = await problem(step, previous, sessionLast, scope);
		if (reason !== null) {
			return {
				ok: false,
				checked,
				first_bad_seq: step.seq,
				first_bad_order_index: step.order_index,
				reason
			};
		}
		if (step.session_id !== null) sessionLast.set(step.session_id, step.hash);
		previous = step;
	}

	return { ok: true, checked, first_bad_seq: null, first_bad_order_index: null, reason: null };
}

async function problem(
	step: CheckedStep,
	previous: CheckedStep | null,
	sessionLast: ReadonlyMap<string, string>,
	scope: VerifyScope
): Promise<BreakReason | null> {
	const adjacent = previous !== null && step.seq === previous.seq + 1;
	if (scope === 'global' && (previous === null ? step.seq !== 1 : !adjacent)) return 'seq_gap';

	if (step.seq === 1) {
		if (step.prev_hash !== GENESIS_HASH) return 'prev_hash';
	} else if (adjacent && step.prev_hash !== previous!.hash) {
		return 'prev_hash';
	}

	const expectedSessionPrev = step.session_id === null ? null : (sessionLast.get(step.session_id) ?? null);
	if (step.session_prev_hash !== expectedSessionPrev) return 'session_prev_hash';

	if (hasRecord(step)) {
		const recomputed = await payloadHash(step.payload, step.text_fi ?? null, step.text_en ?? null);
		if (recomputed !== step.payload_hash) return 'payload_hash';
	}

	if ((await computeHash(step)) !== step.hash) return 'hash';
	return null;
}

function hasRecord(step: CheckedStep): boolean {
	return (
		step.payload !== undefined && step.payload !== null && step.text_fi !== undefined && step.text_en !== undefined
	);
}
