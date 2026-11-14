/** Merging live stream events into the page state (#50: replace on snapshot, merge by session). */
import { matchesFilter } from './states';
import type { OrderUpdated, OverviewFilter, OverviewResponse, Step, TranscriptLine } from './types';

/**
 * Applies one `order_updated`: replaces the card, moves it and its company to the top
 * (newest activity first), drops it when it no longer matches the filter, and takes the
 * counters from the event (the API always sends them). Mutates `data` (a `$state` proxy on
 * the page). Applying the same event twice, as after a resume, changes nothing more.
 */
export function applyOrderUpdated(data: OverviewResponse, update: OrderUpdated, filter: OverviewFilter): void {
	const id = update.order.session_id;
	for (const company of data.companies) {
		const index = company.orders.findIndex((o) => o.session_id === id);
		if (index >= 0) company.orders.splice(index, 1);
	}
	data.companies = data.companies.filter((c) => c.orders.length > 0);
	if (update.totals) data.totals = update.totals;

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
