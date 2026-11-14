import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import events from './fixtures/d1042-events.json';
import tampered from './fixtures/d1042-events-tampered.json';
import { GENESIS_HASH, canonicalJson, chainHashInput, computeHash, formatAt, payloadHash } from './hash';
import type { Step } from './types';
import { verifyChain, type CheckedStep } from './verify';

const chain = events as Step[];

interface Vector {
	seq: number;
	at: string;
	type: string;
	actor: string;
	session_id: string | null;
	quote_id: string | null;
	payload: unknown;
	text_fi: string | null;
	text_en: string | null;
	payload_hash: string;
	prev_hash: string;
	session_prev_hash: string | null;
	hash_input: string;
	hash: string;
}

/** The vectors the Python tests check too (#41), read from the file so the two can't drift. */
const vectors = JSON.parse(
	readFileSync(new URL('../../../../docs/audit-chain-vectors.json', import.meta.url), 'utf-8')
) as { genesis_hash: string; events: Vector[] };

/** A vector as a step with its payload, so `verifyChain` checks `payload_hash` too. */
const asStep = (v: Vector, order_index: number): CheckedStep => ({
	...v,
	order_index,
	text: v.text_fi === null && v.text_en === null ? null : { fi: v.text_fi ?? '', en: v.text_en ?? '' }
});

describe('verifyChain', () => {
	it('passes the D-1042 fixture', async () => {
		const result = await verifyChain(chain);
		expect(result).toEqual({
			ok: true,
			checked: 31,
			first_bad_seq: null,
			first_bad_order_index: null,
			reason: null
		});
	});

	it('fails the tampered fixture at event #17', async () => {
		const result = await verifyChain(tampered as Step[]);
		const bad = chain.find((s) => s.order_index === 17)!;
		expect(result.ok).toBe(false);
		expect(result.first_bad_order_index).toBe(17);
		expect(result.first_bad_seq).toBe(bad.seq);
		expect(result.reason).toBe('hash');
		expect(result.checked).toBe(17);
	});

	it('catches a removed event through the session link', async () => {
		const withoutFive = chain.filter((s) => s.order_index !== 5);
		const result = await verifyChain(withoutFive);
		expect(result.ok).toBe(false);
		expect(result.first_bad_order_index).toBe(6);
		expect(result.reason).toBe('session_prev_hash');
	});

	it('catches a changed timestamp', async () => {
		const changed = chain.map((s) => (s.order_index === 3 ? { ...s, at: '2026-11-12T08:02:25.000000Z' } : s));
		const result = await verifyChain(changed);
		expect(result.first_bad_order_index).toBe(3);
		expect(result.reason).toBe('hash');
	});

	it('checks steps in seq order, whatever order they arrive in', async () => {
		const result = await verifyChain([...chain].reverse());
		expect(result.ok).toBe(true);
	});

	it('passes an empty chain', async () => {
		expect((await verifyChain([])).ok).toBe(true);
	});
});

describe('shared test vectors (docs/audit-chain-vectors.json)', () => {
	it('has vectors to check', () => {
		expect(vectors.events.length).toBeGreaterThan(0);
	});

	it('uses the same genesis hash', () => {
		expect(GENESIS_HASH).toBe(vectors.genesis_hash);
	});

	describe.each(vectors.events.map((v) => [v.seq, v] as const))('event %i', (_seq, v) => {
		it('matches payload_hash', async () => {
			expect(await payloadHash(v.payload, v.text_fi, v.text_en)).toBe(v.payload_hash);
		});

		it('matches hash_input byte for byte', () => {
			expect(chainHashInput(v)).toBe(v.hash_input);
		});

		it('matches hash', async () => {
			expect(await computeHash(v)).toBe(v.hash);
		});
	});

	it('verifies as a global chain', async () => {
		const steps = vectors.events.map((v, i) => asStep(v, i + 1));
		expect(await verifyChain(steps, 'global')).toEqual({
			ok: true,
			checked: steps.length,
			first_bad_seq: null,
			first_bad_order_index: null,
			reason: null
		});
	});

	it('verifies one session on its own', async () => {
		const sid = vectors.events.find((v) => v.session_id !== null)!.session_id;
		const steps = vectors.events.filter((v) => v.session_id === sid).map((v, i) => asStep(v, i + 1));
		expect(steps.length).toBeGreaterThan(0);
		expect((await verifyChain(steps, 'session')).ok).toBe(true);
	});

	it('finds a changed sentence through payload_hash', async () => {
		const steps = vectors.events.map((v, i) => asStep(v, i + 1));
		const last = steps[steps.length - 1];
		steps[steps.length - 1] = { ...last, text: { fi: 'muutettu', en: 'changed' } };
		const result = await verifyChain(steps, 'global');
		expect(result.reason).toBe('payload_hash');
		expect(result.first_bad_seq).toBe(last.seq);
	});

	it('finds a missing event in the global chain', async () => {
		const steps = vectors.events.filter((v) => v.seq !== 1).map((v, i) => asStep(v, i + 1));
		const result = await verifyChain(steps, 'global');
		expect(result.reason).toBe('seq_gap');
		expect(result.first_bad_seq).toBe(steps[0].seq);
	});
});

describe('formatAt', () => {
	it('writes UTC with six fractional digits and Z', () => {
		expect(formatAt(new Date('2026-11-12T10:02:14.5+02:00'))).toBe('2026-11-12T08:02:14.500000Z');
	});
});

describe('canonicalJson', () => {
	it('sorts keys and writes numbers the way JSON.stringify does', () => {
		expect(canonicalJson({ b: [1.195, 1e21, -0], a: 'ä' })).toBe('{"a":"ä","b":[1.195,1e+21,0]}');
	});
});
