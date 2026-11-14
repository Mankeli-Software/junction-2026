import { describe, expect, it } from 'vitest';
import events from './fixtures/d1042-events.json';
import tampered from './fixtures/d1042-events-tampered.json';
import { GENESIS_HASH, computeHash, payloadHash } from './hash';
import type { Step } from './types';
import { verifyChain } from './verify';

const chain = events as Step[];

/**
 * The shared test vector for #41. Expected values computed in Python with
 *   payload_hash = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
 *   hash = sha256(prev_hash + payload_hash + str(seq) + at + type)
 * PENDING #41: replace with the vector #41 publishes once it documents the byte format.
 */
const VECTOR = {
	payload: { channel: 'phone', company: 'Hassu Hauki Oy', note: 'Sienimetsä' },
	payload_hash: '696538225c026be4a3ec4a39cc38ab7c04e8b1d92c0927aa8aaae8e5f88349ba',
	prev_hash: GENESIS_HASH,
	seq: 1,
	at: '2026-11-12T10:02:14+02:00',
	type: 'session_started',
	hash: 'a5a3c17abf1ffdda8fc00f96d438f79563724ed76611b919e2c8cbf42bfc9318'
};

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
		expect(result.reason).toBe('session_link');
	});

	it('catches a changed timestamp', async () => {
		const changed = chain.map((s) => (s.order_index === 3 ? { ...s, at: '2026-11-12T10:02:25+02:00' } : s));
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

describe('shared test vector (#41)', () => {
	it('matches the payload hash computed in Python', async () => {
		expect(await payloadHash(VECTOR.payload)).toBe(VECTOR.payload_hash);
	});

	it('matches the event hash computed in Python', async () => {
		expect(await computeHash(VECTOR)).toBe(VECTOR.hash);
	});

	it('verifies as a one-event chain starting from genesis', async () => {
		const step = { ...VECTOR, order_index: 1, session_prev_hash: null };
		expect((await verifyChain([step])).ok).toBe(true);
	});
});
