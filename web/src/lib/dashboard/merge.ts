/** Merging live stream events into the page state (#50: replace on snapshot, merge by session). */
import { matchesFilter, stateGroup } from './states';
import type { OrderUpdated, OverviewFilter, OverviewResponse, Step, StateGroup, TranscriptLine } from './types';

/** The group each session was last seen in, so totals can be adjusted without a refetch. */
export type KnownGroups = Map<string, StateGroup | null>;

export function rememberGroups(data: OverviewResponse, known: KnownGroups): void {
	for (const company of data.companies) {
		for (const order of company.orders) known.set(order.session_id, stateGroup(order.state));
	}
}

function adjustTotals(
	data: OverviewResponse,
	update: OrderUpdated,
	previous: { group: StateGroup | null; total_cents: number | null } | undefined
): void {
	const totals = data.totals;
	const nextGroup = stateGroup(update.order.state);
	if (previous === undefined) totals.by_channel[update.order.channel] = (totals.by_channel[update.order.channel] ?? 0) + 1;
	const prevGroup = previous?.group ?? null;
	if (prevGroup !== nextGroup) {
		if (prevGroup) totals[prevGroup] = Math.max(0, totals[prevGroup] - 1);
		if (nextGroup) totals[nextGroup] += 1;
		if (prevGroup === 'confirmed') totals.confirmed_cents -= previous?.total_cents ?? 0;
		if (nextGroup === 'confirmed') totals.confirmed_cents += update.order.total_cents ?? 0;
	}
}

/**
 * Applies one `order_updated`: replaces the card, moves it and its company to the top
 * (newest activity first), drops it when it no longer matches the filter, and keeps the
 * counters right. Mutates `data` (a `$state` proxy on the page).
 *
 * Totals: taken from the event when the server sends them. Otherwise adjusted from the
 * card's previous group. A session never seen before counts as new, except while a filter
 * is on, when it may just have been filtered out; then the totals are left alone.
 */
export function applyOrderUpdated(
	data: OverviewResponse,
	update: OrderUpdated,
	filter: OverviewFilter,
	known: KnownGroups
): void {
	const id = update.order.session_id;
	let previousCard: { group: StateGroup | null; total_cents: number | null } | undefined;

	for (const company of data.companies) {
		const index = company.orders.findIndex((o) => o.session_id === id);
		if (index >= 0) {
			const [old] = company.orders.splice(index, 1);
			previousCard = { group: stateGroup(old.state), total_cents: old.total_cents };
		}
	}
	data.companies = data.companies.filter((c) => c.orders.length > 0);

	if (update.totals) {
		data.totals = update.totals;
	} else if (previousCard || known.has(id)) {
		adjustTotals(data, update, previousCard ?? { group: known.get(id) ?? null, total_cents: null });
	} else if (!filter.state && !filter.channel) {
		adjustTotals(data, update, undefined);
	}
	known.set(id, stateGroup(update.order.state));

	if (!matchesFilter(update.order, filter)) return;

	const existing = data.companies.findIndex((c) => c.name === update.company.name);
	const company =
		existing >= 0
			? data.companies.splice(existing, 1)[0]
			: { name: update.company.name, exclusions: update.company.exclusions, orders: [] };
	company.exclusions = update.company.exclusions;
	company.orders.unshift(update.order);
	data.companies.unshift(company);
}

/** Adds a step if it is new, keeping `seq` order. Returns true if it was added. */
export function mergeStep(steps: Step[], step: Step): boolean {
	if (steps.some((s) => s.seq === step.seq)) return false;
	const at = steps.findIndex((s) => s.seq > step.seq);
	if (at === -1) steps.push(step);
	else steps.splice(at, 0, step);
	return true;
}

export function mergeTranscript(lines: TranscriptLine[], line: TranscriptLine): boolean {
	if (lines.some((l) => l.at === line.at && l.who === line.who && l.text === line.text)) return false;
	lines.push(line);
	lines.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
	return true;
}

/** The loaded steps plus the ones that came over the stream since, in `seq` order. */
export function combineSteps(loaded: readonly Step[], live: readonly Step[]): Step[] {
	const out = [...loaded];
	for (const step of live) mergeStep(out, step);
	return out;
}

/** The loaded transcript plus the lines that came over the stream since. */
export function combineTranscript(
	loaded: readonly TranscriptLine[],
	live: readonly TranscriptLine[]
): TranscriptLine[] {
	const out = [...loaded];
	for (const line of live) mergeTranscript(out, line);
	return out;
}
