/**
 * The audit chain's hash, as `docs/audit-chain.md` specifies it (#41). The browser's copy
 * of `api/app/services/audit/chain.py`; both are tested against `docs/audit-chain-vectors.json`.
 *
 * Change the byte format only together with the doc, the vectors and the Python. Then
 * regenerate the fixtures with `pnpm fixtures`.
 *
 * No imports, so the fixture generator (`scripts/generate-dashboard-fixtures.ts`) can run
 * it directly under Node.
 */

/** `prev_hash` of the first event in the global chain (`seq` 1): 64 zeros. */
export const GENESIS_HASH = '0'.repeat(64);

/** Everything `hash` covers, in its order. The payload and sentences are in via `payload_hash`. */
export interface ChainFields {
	prev_hash: string;
	/** `hash` of the session's previous event; null for its first event and for events with no session. */
	session_prev_hash: string | null;
	seq: number;
	/** `formatAt()` output, exactly as the API sends it. */
	at: string;
	type: string;
	actor: string;
	session_id: string | null;
	quote_id: string | null;
	payload_hash: string;
}

/**
 * The hashed form of a timestamp: UTC, exactly six fractional digits and `Z`
 * (`2026-11-14T10:23:45.123456Z`). A `Date` has only milliseconds, so its last three
 * digits are zeros.
 */
export function formatAt(at: Date): string {
	const iso = at.toISOString(); // 2026-11-14T10:23:45.123Z
	return `${iso.slice(0, -1)}000Z`;
}

/**
 * The bytes `hash` is SHA-256 of, as text: the nine fields joined with `\n` in this order,
 * a null as the empty string, `seq` in decimal, no newline at the end.
 */
export function chainHashInput(fields: ChainFields): string {
	const parts = [
		fields.prev_hash,
		fields.session_prev_hash,
		String(fields.seq),
		fields.at,
		fields.type,
		fields.actor,
		fields.session_id,
		fields.quote_id,
		fields.payload_hash
	];
	return parts.map((part) => part ?? '').join('\n');
}

export async function sha256Hex(bytes: Uint8Array): Promise<string> {
	const digest = await crypto.subtle.digest('SHA-256', bytes as Uint8Array<ArrayBuffer>);
	return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** The event's `hash`: SHA-256 over the UTF-8 bytes of `chainHashInput()`. */
export function computeHash(fields: ChainFields): Promise<string> {
	return sha256Hex(new TextEncoder().encode(chainHashInput(fields)));
}

/**
 * RFC 8785 canonical JSON: keys sorted by UTF-16 code units, no whitespace, strings and
 * numbers written the way `JSON.stringify` writes them (RFC 8785 takes both from ECMAScript).
 */
export function canonicalJson(value: unknown): string {
	if (typeof value === 'number' && !Number.isFinite(value)) {
		throw new TypeError('canonical JSON has no NaN or Infinity');
	}
	if (value === null || typeof value !== 'object') return JSON.stringify(value);
	if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
	const entries = Object.entries(value as Record<string, unknown>)
		.filter(([, v]) => v !== undefined)
		.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
	return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(',')}}`;
}

/** `payload_hash`: SHA-256 over the canonical JSON of the payload and both sentences. */
export function payloadHash(payload: unknown, text_fi: string | null, text_en: string | null): Promise<string> {
	const document = { payload, text_fi, text_en };
	return sha256Hex(new TextEncoder().encode(canonicalJson(document)));
}
