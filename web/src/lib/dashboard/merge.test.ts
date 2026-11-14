import { describe, expect, it } from 'vitest';
import overviewFixture from './fixtures/overview.json';
import recordedSteps from './fixtures/recorded/steps.json';
import { applyOrderUpdated, combineSteps, mergeStep } from './merge';
import type { OrderUpdated, OverviewResponse, Step, Totals } from './types';

const fresh = () => structuredClone(overviewFixture) as OverviewResponse;
const noFilter = { state: null, channel: null };
const totals = (confirmed: number): Totals => ({
	active: 1,
	waiting: 1,
	confirmed,
	attention: 0,
	confirmed_cents: 99,
	by_channel: { phone: 1, web_chat: 0, webmcp: 0, mcp: 0 }
});

describe('applyOrderUpdated', () => {
	it('moves the card and its company to the top and takes the totals from the event', () => {
		const data = fresh();
		const card = data.companies[2].orders[0];
		const update: OrderUpdated = {
			company: { name: data.companies[2].name, exclusions: [] },
			order: { ...card, state: 'confirmed', order_number: 'D-1050' },
			totals: totals(10)
		};
		applyOrderUpdated(data, update, noFilter);
		expect(data.companies[0].name).toBe(update.company.name);
		expect(data.companies[0].orders[0].order_number).toBe('D-1050');
		expect(data.totals).toEqual(totals(10));
	});

	it('changes nothing more when the same event comes again after a resume', () => {
		const data = fresh();
		const order = { ...data.companies[0].orders[0], session_id: 's_new' };
		const update: OrderUpdated = { company: { name: 'Puolukka Pub Oy', exclusions: [] }, order, totals: totals(3) };
		applyOrderUpdated(data, update, noFilter);
		const once = structuredClone(data);
		applyOrderUpdated(data, update, noFilter);
		expect(data).toEqual(once);
		expect(data.companies.flatMap((c) => c.orders).filter((o) => o.session_id === 's_new')).toHaveLength(1);
	});

	it('drops a card that leaves the filter, and keeps the totals without any', () => {
		const data = fresh();
		const before = structuredClone(data.totals);
		const filter = { state: 'waiting' as const, channel: null };
		data.companies = data.companies.filter((c) => c.name === 'Lihapulla ja Pojat Oy');
		const card = data.companies[0].orders[0];
		applyOrderUpdated(
			data,
			{ company: { name: 'Lihapulla ja Pojat Oy', exclusions: [] }, order: { ...card, state: 'confirmed' } },
			filter
		);
		expect(data.companies).toHaveLength(0);
		expect(data.totals).toEqual(before);
	});
});

describe('mergeStep', () => {
	const steps = recordedSteps as Step[];

	it('ignores a step sent again and keeps seq order', () => {
		const loaded = steps.slice(0, 10);
		const live = [steps[12], steps[10], steps[10], steps[11]];
		expect(combineSteps(loaded, live).map((s) => s.seq)).toEqual(steps.slice(0, 13).map((s) => s.seq));
		const out = [...loaded];
		expect(mergeStep(out, steps[3])).toBe(false);
	});
});
