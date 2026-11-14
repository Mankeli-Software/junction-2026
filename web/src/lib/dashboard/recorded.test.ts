/**
 * The dashboard helpers on responses recorded from the real API (#49): a webshop order
 * built with `POST /api/v1/quotes`, sent for confirmation and confirmed on the page, saved
 * from `/api/v1/public/...` in `fixtures/recorded/`. The mock's fixtures are checked to have
 * the same shapes, so both paths go through the same code.
 */
import { describe, expect, it } from 'vitest';
import d1042Events from './fixtures/d1042-events.json';
import d1042Summary from './fixtures/d1042-summary.json';
import d1042Transcript from './fixtures/d1042-transcript.json';
import mockOverview from './fixtures/overview.json';
import events from './fixtures/recorded/events.json';
import overview from './fixtures/recorded/overview.json';
import steps from './fixtures/recorded/steps.json';
import summary from './fixtures/recorded/summary.json';
import verify from './fixtures/recorded/verify.json';
import { buildTimeline } from './timeline';
import type { AuditEvent, OrderSummary, OverviewResponse, Step, TranscriptLine } from './types';
import { verifyChain, withRecords } from './verify';

const recordedSteps = steps as Step[];
const recordedEvents = events as AuditEvent[];

describe('the in-browser check on the recorded order', () => {
	it('agrees with the API on /steps alone', async () => {
		const result = await verifyChain(recordedSteps);
		expect(result.ok).toBe(true);
		expect(result.checked).toBe(verify.checked);
	});

	it('checks payload_hash with the raw sentences from /events', async () => {
		const result = await verifyChain(withRecords(recordedSteps, recordedEvents));
		expect(result).toMatchObject({ ok: true, checked: recordedSteps.length });
	});

	it('finds a sentence changed in /events', async () => {
		const changed = recordedEvents.map((e) => (e.order_index === 9 ? { ...e, text_en: 'The quote is ready.' } : e));
		const result = await verifyChain(withRecords(recordedSteps, changed));
		expect(result).toMatchObject({ ok: false, first_bad_order_index: 9, reason: 'payload_hash' });
	});

	it('finds a payload changed in /events, and skips a deleted one', async () => {
		const edited = recordedEvents.map((e) =>
			e.order_index === 4 ? { ...e, payload: { ...e.payload, lines: [] } } : e
		);
		expect((await verifyChain(withRecords(recordedSteps, edited))).reason).toBe('payload_hash');
		const deleted = recordedEvents.map((e) => (e.order_index === 4 ? { ...e, payload: null } : e));
		expect((await verifyChain(withRecords(recordedSteps, deleted))).ok).toBe(true);
	});

	it('checks a step the stream added after /events was loaded on its chain fields', async () => {
		const result = await verifyChain(withRecords(recordedSteps, recordedEvents.slice(0, 10)));
		expect(result.ok).toBe(true);
	});
});

describe('the full flow of the recorded order', () => {
	const rows = buildTimeline(recordedSteps, recordedEvents, []);
	const tools = rows.filter((r) => r.kind === 'tool');

	it('pairs each tool call with its result and reads the API payload names', () => {
		expect(tools.map((t) => t.kind === 'tool' && t.tool)).toEqual(['build_quote', 'request_confirmation']);
		const [build, confirm] = tools;
		if (build.kind !== 'tool' || confirm.kind !== 'tool') return;
		expect(build.decision).toEqual({ code: 'ready', label: null });
		expect(build.args).toMatchObject({ lines: [{ text: 'maito' }, { text: 'arla' }] });
		expect((build.response as { decision: string }).decision).toBe('ready');
		expect(build.summary).toBeNull();
		expect(confirm.decision).toEqual({ code: 'returned', label: null });
		expect(confirm.response).toMatchObject({ inbox: true });
	});

	it('covers every step once', () => {
		expect(rows.flatMap((r) => r.refs).sort((a, b) => a - b)).toEqual(recordedSteps.map((s) => s.order_index));
	});

	it('shows a failed tool call as an error', () => {
		const failed = recordedEvents.map((e) =>
			e.order_index === 12
				? { ...e, text_en: 'request_confirmation failed: no', payload: { tool: 'request_confirmation', error: 'no' } }
				: e
		);
		const stepsWithText = recordedSteps.map((s) =>
			s.order_index === 12 ? { ...s, text: { fi: 'virhe', en: 'request_confirmation failed: no' } } : s
		);
		const row = buildTimeline(stepsWithText, failed, []).filter((r) => r.kind === 'tool')[1];
		expect(row.kind === 'tool' && row.decision?.code).toBe('error');
		expect(row.kind === 'tool' && row.response).toBe('no');
	});
});

describe('the recorded summary', () => {
	const order = summary as OrderSummary;

	it('has the fields the real API leaves empty for now', () => {
		expect(order.order_number).toBe('D-1042');
		expect(order.signature_valid).toBeNull();
		expect(order.requests.flatMap((r) => r.lines).every((l) => l.trace.ranked.length === 0)).toBe(true);
	});
});

/**
 * Where two values differ in shape: keys only one of them has, compared down to where
 * either is null, an empty array or a free-form `payload`.
 */
function shapeDiff(mock: unknown, real: unknown, path = ''): string[] {
	if (Array.isArray(mock) && Array.isArray(real)) {
		return mock.length && real.length ? shapeDiff(mock[0], real[0], `${path}[]`) : [];
	}
	const isObject = (v: unknown) => v !== null && typeof v === 'object' && !Array.isArray(v);
	if (!isObject(mock) || !isObject(real) || path.endsWith('.payload')) return [];
	const m = mock as Record<string, unknown>;
	const r = real as Record<string, unknown>;
	const keys = new Set([...Object.keys(m), ...Object.keys(r)]);
	return [...keys].flatMap((key) =>
		key in m && key in r ? shapeDiff(m[key], r[key], `${path}.${key}`) : [`${path}.${key}`]
	);
}

describe('the mock has the API shapes', () => {
	it('for an overview card', () => {
		const real = (overview as OverviewResponse).companies[0].orders[0];
		for (const company of (mockOverview as OverviewResponse).companies) {
			for (const card of company.orders) expect(shapeDiff(card, real), card.session_id).toEqual([]);
		}
		expect(shapeDiff(mockOverview, overview)).toEqual([]);
	});

	it('for the summary', () => {
		expect(shapeDiff(d1042Summary, summary)).toEqual([]);
	});

	it('for a step and an event', () => {
		for (const event of d1042Events) expect(shapeDiff(event, recordedEvents[0])).toEqual([]);
		const stepKeys = Object.keys(recordedSteps[0]);
		expect(Object.keys(recordedEvents[0]).filter((k) => stepKeys.includes(k)).sort()).toEqual(stepKeys.sort());
	});

	it('for a transcript line', () => {
		const line = (d1042Transcript as TranscriptLine[])[0];
		expect(Object.keys(line).sort()).toEqual(['at', 'lang', 'text', 'who']);
	});
});
