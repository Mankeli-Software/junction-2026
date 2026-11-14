import { describe, expect, it } from 'vitest';
import events from './fixtures/d1042-events.json';
import transcript from './fixtures/d1042-transcript.json';
import overviewFixture from './fixtures/overview.json';
import { applyOrderUpdated, rememberGroups, type KnownGroups } from './merge';
import { buildTimeline, collapse, formatRefs, stepCount } from './timeline';
import type { AuditEvent, OrderCard, OverviewResponse, TranscriptLine } from './types';

describe('buildTimeline', () => {
	const rows = buildTimeline(events as AuditEvent[], events as AuditEvent[], transcript as TranscriptLine[]);
	const refs = rows.map((r) => formatRefs(r.refs));

	it('groups the steps as screen 32 does', () => {
		expect(refs.slice(0, 7)).toEqual(['#1', '#2', '#3–5', '#6', '#7', '#8, #13', '#9–11']);
		expect(refs.slice(-4)).toEqual(['#25–26', '#27–28', '#29–30', '#31']);
		expect(stepCount(rows)).toBe(31);
	});

	it('puts the tool arguments and the response in one box', () => {
		const box = rows[5];
		expect(box.kind).toBe('tool');
		if (box.kind !== 'tool') return;
		expect(box.tool).toBe('update_quote');
		expect(box.decision?.code).toBe('ready');
		expect(box.args).toEqual({ quote_id: 'q_7f3a', answer: { needed_by: '2026-11-16' } });
		expect((box.response as { total_cents: number }).total_cents).toBe(4190);
	});

	it('takes conversation text from the transcript', () => {
		const buyer = rows[1];
		expect(buyer.kind === 'buyer' && buyer.text).toBe('I need five kilos of ground beef for tomorrow.');
	});

	it('collapses the middle of a long session', () => {
		const { head, hidden, tail } = collapse(rows);
		expect(head).toHaveLength(9);
		expect(tail).toHaveLength(4);
		expect(stepCount(hidden)).toBe(10);
	});
});

describe('applyOrderUpdated', () => {
	const fresh = () => structuredClone(overviewFixture) as OverviewResponse;
	const noFilter = { state: null, channel: null };

	it('moves a confirmed card and its company to the top and adjusts the counters', () => {
		const data = fresh();
		const known: KnownGroups = new Map();
		rememberGroups(data, known);
		const card = data.companies[2].orders[0];
		applyOrderUpdated(
			data,
			{ company: { name: 'Lihapulla ja Pojat Oy', exclusions: [] }, order: { ...card, state: 'confirmed' } },
			noFilter,
			known
		);
		expect(data.companies[0].name).toBe('Lihapulla ja Pojat Oy');
		expect(data.totals.waiting).toBe(1);
		expect(data.totals.confirmed).toBe(10);
		expect(data.totals.confirmed_cents).toBe(421000 + 115000);
	});

	it('adds a new company and counts the new session', () => {
		const data = fresh();
		const known: KnownGroups = new Map();
		rememberGroups(data, known);
		const order: OrderCard = { ...data.companies[0].orders[0], session_id: 's_new', channel: 'mcp' };
		applyOrderUpdated(data, { company: { name: 'Puolukka Pub Oy', exclusions: [] }, order }, noFilter, known);
		expect(data.companies[0].name).toBe('Puolukka Pub Oy');
		expect(data.totals.active).toBe(3);
		expect(data.totals.by_channel.mcp).toBe(3);
	});

	it('drops a card that leaves the filter', () => {
		const data = fresh();
		const known: KnownGroups = new Map();
		const filter = { state: 'waiting' as const, channel: null };
		data.companies = data.companies.filter((c) => c.name === 'Lihapulla ja Pojat Oy');
		rememberGroups(data, known);
		const card = data.companies[0].orders[0];
		applyOrderUpdated(
			data,
			{ company: { name: 'Lihapulla ja Pojat Oy', exclusions: [] }, order: { ...card, state: 'confirmed' } },
			filter,
			known
		);
		expect(data.companies).toHaveLength(0);
	});
});
