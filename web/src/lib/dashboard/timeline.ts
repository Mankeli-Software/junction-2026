/**
 * Builds the full-flow timeline (screen 32) from the steps, the full events and the transcript.
 *
 * One row per step, except:
 * - a tool call and its result are one box; when only a clarification sits between them
 *   it goes into the box too ("#3–5"), otherwise the steps between keep their own rows;
 * - consecutive search steps (searched, filtered, availability) are one engine row ("#9–11");
 * - the end of a call and the link going out are one row, as are opening the link and
 *   checking the flags.
 */
import type { AuditEvent, Localized, Step, TranscriptLine } from './types';

export type RowKind = 'buyer' | 'agent' | 'tool' | 'engine' | 'system' | 'confirmation';
export type TimelineFilter = 'everything' | 'conversation' | 'agent_engine';

export interface SayRow {
	kind: 'buyer' | 'agent';
	at: string;
	refs: number[];
	text: string;
	transcript: boolean;
}

export interface ToolRow {
	kind: 'tool';
	at: string;
	refs: number[];
	tool: string;
	summary: Localized | null;
	decision: { code: string; label: Localized | null } | null;
	notes: Localized[];
	args: unknown;
	response: unknown;
	hasDetails: boolean;
}

export interface NoteRow {
	kind: 'engine' | 'system' | 'confirmation';
	at: string;
	refs: number[];
	types: string[];
	texts: Localized[];
}

export type TimelineRow = SayRow | ToolRow | NoteRow;

const CONFIRMATION_TYPES = new Set([
	'link_opened',
	'flags_acknowledged',
	'quote_edited',
	'order_confirmed',
	'order_cancelled',
	'quote_expired'
]);

const MERGE_CLASS: Record<string, string> = {
	products_searched: 'search',
	candidates_filtered: 'search',
	availability_checked: 'search',
	session_ended: 'call_end',
	inbox_delivered: 'call_end',
	sms_sent: 'call_end',
	sms_failed: 'call_end',
	link_opened: 'page',
	flags_acknowledged: 'page'
};

export function rowKindOf(step: Pick<Step, 'type' | 'actor'>): RowKind {
	if (step.type === 'buyer_said') return 'buyer';
	if (step.type === 'agent_said') return 'agent';
	if (step.type === 'tool_called' || step.type === 'tool_returned') return 'tool';
	if (CONFIRMATION_TYPES.has(step.type)) return 'confirmation';
	if (step.actor === 'engine') return 'engine';
	return 'system';
}

export function rowMatchesFilter(row: TimelineRow, filter: TimelineFilter): boolean {
	if (filter === 'everything') return true;
	if (filter === 'conversation') return row.kind === 'buyer' || row.kind === 'agent';
	return row.kind === 'tool' || row.kind === 'engine' || row.kind === 'system';
}

/** "#3–5", "#8, #13" or "#12". */
export function formatRefs(refs: readonly number[]): string {
	if (refs.length === 0) return '';
	const sorted = [...refs].sort((a, b) => a - b);
	const contiguous = sorted.every((n, i) => i === 0 || n === sorted[i - 1] + 1);
	if (sorted.length === 1) return `#${sorted[0]}`;
	if (contiguous) return `#${sorted[0]}–${sorted[sorted.length - 1]}`;
	return sorted.map((n) => `#${n}`).join(', ');
}

function obj(value: unknown): Record<string, unknown> {
	return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function isLocalized(value: unknown): value is Localized {
	const o = obj(value);
	return typeof o.en === 'string' && typeof o.fi === 'string';
}

function unquote(text: string): string {
	return text.replace(/^"(.*)"$/s, '$1');
}

/**
 * The words after the tool name: the payload's own `summary` when it has one, else the part
 * of the step's sentence after the first comma ("build_quote, 1 line: ..."). The API's
 * sentence, "The agent called build_quote", says no more than the name, so then nothing.
 */
function toolSummary(step: Step, called: Record<string, unknown>): Localized | null {
	if (isLocalized(called.summary)) return called.summary;
	const rest = (text: string) => (text.includes(',') ? text.replace(/^[^,]*,\s*/, '') : '');
	const summary = { en: rest(step.text.en), fi: rest(step.text.fi) };
	return summary.en || summary.fi ? summary : null;
}

/**
 * The pill on a tool box: the engine's decision (`response.decision`), an error, or the
 * result's own sentence. The API's bare "build_quote returned" shows as "Returned".
 */
function toolDecision(
	tool: string,
	returned: Step,
	payload: Record<string, unknown>
): { code: string; label: Localized | null } {
	const response = obj(payload.response);
	if (typeof response.decision === 'string') return { code: response.decision, label: null };
	const status = typeof response.status === 'string' ? response.status : null;
	if (status && isLocalized(response.label)) return { code: status, label: response.label };
	if (payload.error !== undefined) return { code: 'error', label: returned.text };
	if (!returned.text.en || returned.text.en === `${tool} returned`) return { code: status ?? 'returned', label: null };
	return { code: status ?? 'returned', label: returned.text };
}

export function buildTimeline(
	steps: readonly Step[],
	events: readonly AuditEvent[],
	transcript: readonly TranscriptLine[]
): TimelineRow[] {
	const ordered = [...steps].sort((a, b) => a.seq - b.seq);
	const eventBySeq = new Map(events.map((e) => [e.seq, e]));
	const payloadOf = (step: Step) => obj(eventBySeq.get(step.seq)?.payload);
	const used = new Set<number>();
	const rows: TimelineRow[] = [];

	for (let i = 0; i < ordered.length; i++) {
		const step = ordered[i];
		if (used.has(step.seq)) continue;
		used.add(step.seq);
		const kind = rowKindOf(step);

		if (kind === 'buyer' || kind === 'agent') {
			const line = transcript.find((l) => l.who === kind && l.at === step.at);
			const payload = payloadOf(step);
			const text = line?.text ?? (typeof payload.text === 'string' ? payload.text : unquote(step.text.en));
			const transcriptFlag = line !== undefined || payload.transcript === true;
			rows.push({ kind, at: step.at, refs: [step.order_index], text, transcript: transcriptFlag });
			continue;
		}

		if (step.type === 'tool_called') {
			const called = payloadOf(step);
			const callId = called.call_id;
			let j = -1;
			for (let k = i + 1; k < ordered.length; k++) {
				const candidate = ordered[k];
				if (candidate.type !== 'tool_returned' || used.has(candidate.seq)) continue;
				const id = payloadOf(candidate).call_id;
				if (callId === undefined || id === undefined || id === callId) {
					j = k;
					break;
				}
			}
			const refs = [step.order_index];
			const notes: Localized[] = [];
			let returned: Step | null = null;
			if (j >= 0) {
				returned = ordered[j];
				const between = ordered.slice(i + 1, j);
				const absorb = between.every((s) => s.type === 'clarification_asked');
				if (absorb) {
					for (const s of between) {
						used.add(s.seq);
						refs.push(s.order_index);
						notes.push(s.text);
					}
				}
				used.add(returned.seq);
				refs.push(returned.order_index);
			}
			const toolName =
				typeof called.tool === 'string' ? called.tool : (step.text.en.split(',')[0] ?? step.type);
			const answer = returned ? payloadOf(returned) : null;
			rows.push({
				kind: 'tool',
				at: step.at,
				refs,
				tool: toolName,
				summary: toolSummary(step, called),
				decision: returned && answer ? toolDecision(toolName, returned, answer) : null,
				notes,
				args: called.arguments,
				response: answer ? (answer.response ?? answer.error ?? null) : null,
				hasDetails: eventBySeq.has(step.seq)
			});
			continue;
		}

		const row: NoteRow = {
			kind: kind === 'tool' ? 'system' : kind,
			at: step.at,
			refs: [step.order_index],
			types: [step.type],
			texts: [step.text]
		};
		const cls = MERGE_CLASS[step.type];
		if (cls) {
			while (i + 1 < ordered.length && MERGE_CLASS[ordered[i + 1].type] === cls) {
				const next = ordered[++i];
				used.add(next.seq);
				row.refs.push(next.order_index);
				row.types.push(next.type);
				row.texts.push(next.text);
			}
		}
		rows.push(row);
	}
	return rows;
}

/** How many steps a set of rows covers, for "Show 12 more steps". */
export function stepCount(rows: readonly TimelineRow[]): number {
	return rows.reduce((n, row) => n + row.refs.length, 0);
}

export const COLLAPSE_OVER = 14;
export const KEEP_HEAD = 9;
export const KEEP_TAIL = 4;

/** Long sessions show the first and last rows, with the middle behind one button. */
export function collapse(rows: readonly TimelineRow[]): {
	head: TimelineRow[];
	hidden: TimelineRow[];
	tail: TimelineRow[];
} {
	if (rows.length <= COLLAPSE_OVER) return { head: [...rows], hidden: [], tail: [] };
	return {
		head: rows.slice(0, KEEP_HEAD),
		hidden: rows.slice(KEEP_HEAD, rows.length - KEEP_TAIL),
		tail: rows.slice(rows.length - KEEP_TAIL)
	};
}
