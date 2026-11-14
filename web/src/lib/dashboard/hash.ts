/**
 * The audit chain's hash function, shared by the in-browser verify and the fixtures.
 *
 * No imports, so the fixture generator (`scripts/generate-dashboard-fixtures.ts`) can run
 * it directly under Node.
 */

/** `prev_hash` of the very first event in the global chain. Assumed, until #41 documents it. */
export const GENESIS_HASH = '0'.repeat(64);

export interface HashFields {
	prev_hash: string;
	payload_hash: string;
	seq: number;
	at: string;
	type: string;
}

/**
 * ASSUMED BYTE FORMAT, change it here only.
 *
 * `technical-plan.md` §8.5 says `hash = SHA-256(prev_hash + payload_hash + seq, at, type)`.
 * #41 has not documented the exact bytes yet, so this takes it literally: the UTF-8 bytes
 * of the plain concatenation of lowercase hex `prev_hash`, lowercase hex `payload_hash`,
 * `seq` in decimal, `at` exactly as the API sends it (ISO 8601 string) and `type`, with no
 * separators. When #41 settles the format, change this function and regenerate the fixtures
 * (`pnpm fixtures`); the shared test vector in `verify.test.ts` must then match Python.
 */
export function hashInput(fields: HashFields): Uint8Array {
	const text = `${fields.prev_hash}${fields.payload_hash}${fields.seq}${fields.at}${fields.type}`;
	return new TextEncoder().encode(text);
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
	const digest = await crypto.subtle.digest('SHA-256', bytes as Uint8Array<ArrayBuffer>);
	return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

export function computeHash(fields: HashFields): Promise<string> {
	return sha256Hex(hashInput(fields));
}

/**
 * Canonical JSON for `payload_hash`: sorted keys, no whitespace. Used only by the fixture
 * generator and the mock; the browser verify does not need payloads (§8.5). Assumed to
 * match Python's `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
 * for the integers and strings used in the fixtures.
 */
export function canonicalJson(value: unknown): string {
	if (value === null || typeof value !== 'object') return JSON.stringify(value);
	if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
	const entries = Object.entries(value as Record<string, unknown>)
		.filter(([, v]) => v !== undefined)
		.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
	return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(',')}}`;
}

export function payloadHash(payload: unknown): Promise<string> {
	return sha256Hex(new TextEncoder().encode(canonicalJson(payload)));
}
