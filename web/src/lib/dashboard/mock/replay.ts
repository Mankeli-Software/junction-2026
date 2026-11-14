/**
 * The fake event source for `PUBLIC_DASHBOARD_MOCK=1`: replays a short script every few
 * seconds so the overview animates without a backend. The live call (s_2611_0043) goes from
 * "in call" to confirmed, other cards change state and a new company appears. Then the
 * world resets with a fresh snapshot and the script loops.
 *
 * Runs in the browser only. New steps are hashed with the same `computeHash` as the real
 * chain, so the live call's audit log keeps verifying while it grows.
 */
import liveCallEvents from '../fixtures/live-call-events.json';
import { computeHash, payloadHash } from '../hash';
import { matchesFilter } from '../states';
import type {
	AuditEvent,
	CompanyRef,
	Localized,
	OrderCard,
	OverviewFilter,
	OverviewResponse,
	StreamMessage,
	TranscriptLine
} from '../types';
import { LIVE_CALL_SESSION_ID, mockOverview } from './backend';
import type { LiveConnection, StreamListener } from '../live.svelte';

const TICK_MS = 3500;
const PAUSE_TICKS = 3;

interface Subscriber {
	filter: OverviewFilter;
	listener: StreamListener;
}

const subscribers = new Set<Subscriber>();
let world: OverviewResponse = mockOverview();
/** Step and transcript events sent since the last reset, replayed to late subscribers. */
let backlog: StreamMessage[] = [];
let lastLive = (liveCallEvents as AuditEvent[]).at(-1)!;
let eventId = 0;
let cursor = 0;
let timer: ReturnType<typeof setInterval> | null = null;

const same = (text: string): Localized => ({ en: text, fi: text });

function send(message: StreamMessage): void {
	for (const sub of subscribers) {
		if (message.event === 'order_updated' && !matchesFilter(message.data.order, sub.filter)) continue;
		sub.listener(message);
	}
}

function findCard(sessionId: string): { company: CompanyRef; order: OrderCard } | null {
	for (const company of world.companies) {
		const order = company.orders.find((o) => o.session_id === sessionId);
		if (order) return { company: { name: company.name, exclusions: company.exclusions }, order };
	}
	return null;
}

/** Changes a card in the world and sends `order_updated`. Totals are left to the client. */
function updateCard(sessionId: string, patch: Partial<OrderCard>, company?: CompanyRef): void {
	const found = findCard(sessionId);
	const stateChanged = patch.state !== undefined && patch.state !== found?.order.state;
	const order: OrderCard = {
		...(found?.order as OrderCard),
		...patch,
		...(stateChanged ? { state_since: new Date().toISOString() } : {})
	};
	const ref = company ?? found!.company;
	for (const c of world.companies) c.orders = c.orders.filter((o) => o.session_id !== sessionId);
	world.companies = world.companies.filter((c) => c.orders.length > 0);
	const existing = world.companies.find((c) => c.name === ref.name);
	if (existing) existing.orders.unshift(order);
	else world.companies.unshift({ ...ref, orders: [order] });
	send({ event: 'order_updated', id: String(++eventId), data: { company: ref, order } });
}

async function addStep(actor: string, type: string, text: Localized, payload: Record<string, unknown>): Promise<void> {
	const seq = lastLive.seq + 1;
	const at = new Date().toISOString();
	const payload_hash = await payloadHash(payload);
	const hash = await computeHash({ prev_hash: lastLive.hash, payload_hash, seq, at, type });
	const event: AuditEvent = {
		...lastLive,
		seq,
		order_index: lastLive.order_index + 1,
		at,
		actor,
		type,
		text,
		payload,
		payload_hash,
		prev_hash: lastLive.hash,
		session_prev_hash: lastLive.hash,
		hash,
		quote_id: 'q_8c21'
	};
	lastLive = event;
	const message: StreamMessage = {
		event: 'step',
		id: String(++eventId),
		data: { session_id: LIVE_CALL_SESSION_ID, step: event }
	};
	backlog.push(message);
	send(message);
}

async function say(who: 'buyer' | 'agent', text: string): Promise<void> {
	await addStep(who, `${who}_said`, same(`"${text}"`), { text, lang: 'en', transcript: true });
	const line: TranscriptLine = { at: lastLive.at, who, text, lang: 'en' };
	const message: StreamMessage = {
		event: 'transcript',
		id: String(++eventId),
		data: { session_id: LIVE_CALL_SESSION_ID, line }
	};
	backlog.push(message);
	send(message);
}

const LIVE = LIVE_CALL_SESSION_ID;

const SCRIPT: Array<() => Promise<void> | void> = [
	async () => {
		await addStep(
			'engine',
			'line_resolved',
			{
				en: 'Chose Lactose-free butter 500 g, 4 pcs = 2 kg, 27.60 €. Flagged: butter contains milk.',
				fi: 'Valittiin Laktoositon voi 500 g, 4 kpl = 2 kg, 27,60 €. Huomio: voi sisältää maitoa.'
			},
			{ line_id: 'l2', product_id: '204010', quantity_sales_units: 4, line_total_cents: 2760 }
		);
		updateCard(LIVE, { step_text: { en: 'Chose lactose-free butter, 4 pcs', fi: 'Valittiin laktoositon voi, 4 kpl' } });
	},
	async () => {
		await addStep(
			'engine',
			'quote_built',
			{ en: 'Quote v1 ready: 2 lines, 69.50 € incl. VAT, 1 flag.', fi: 'Tarjous v1 valmis: 2 riviä, 69,50 € sis. ALV, 1 huomio.' },
			{ quote_id: 'q_8c21', version: 1, lines: 2, total_cents: 6950, flags: ['contains_milk'] }
		);
		await addStep('mcp', 'tool_returned', same('ready'), {
			call_id: 'call_2',
			tool: 'update_quote',
			result: { decision: 'ready', quote_id: 'q_8c21', lines: 2, total_cents: 6950, flags: 1 }
		});
		updateCard(LIVE, {
			state: 'quote_ready',
			total_cents: 6950,
			step_text: { en: 'Quote ready, reading it back', fi: 'Tarjous valmis, luetaan ostajalle' },
			flags: [{ code: 'contains_milk', short: { en: 'butter contains milk', fi: 'voi sisältää maitoa' } }]
		});
	},
	async () => {
		await say('agent', 'Lactose-free butter still contains milk, and your kitchen avoids milk. Two lines, 69.50 euros, arriving Monday. Shall I send it to your phone?');
	},
	() =>
		updateCard('s_2611_0044', {
			step_text: { en: 'Comparing 8 cream products', fi: 'Verrataan 8 kermatuotetta' }
		}),
	async () => {
		await say('buyer', 'Yes, send it. I will check the butter on the page.');
		await addStep(
			'mcp',
			'tool_called',
			{ en: 'request_confirmation, quote q_8c21 v1', fi: 'request_confirmation, tarjous q_8c21 v1' },
			{
				call_id: 'call_3',
				tool: 'request_confirmation',
				summary: { en: 'quote q_8c21 v1, no recipient argument', fi: 'tarjous q_8c21 v1, ei vastaanottaja-argumenttia' },
				args: { quote_id: 'q_8c21' }
			}
		);
		await addStep('mcp', 'tool_returned', { en: 'SMS queued for end of call', fi: 'SMS jonossa puhelun loppuun' }, {
			call_id: 'call_3',
			tool: 'request_confirmation',
			result: { status: 'queued', deliver: 'end_of_call', label: { en: 'SMS queued for end of call', fi: 'SMS jonossa puhelun loppuun' } }
		});
	},
	async () => {
		await addStep('relay', 'session_ended', { en: 'Call ended by buyer.', fi: 'Ostaja lopetti puhelun.' }, { ended_by: 'buyer' });
		await addStep(
			'confirmation',
			'sms_sent',
			{
				en: 'Link sent to the demo phone inbox for +358 40 *** **12.',
				fi: 'Linkki lähetettiin demopuhelimen saapuneisiin (+358 40 *** **12).'
			},
			{ to: '+358 40 *** **12', inbox: true }
		);
		updateCard(LIVE, { state: 'awaiting_confirmation', step_text: null });
	},
	() => updateCard('s_2611_0040', { state: 'link_opened' }),
	() =>
		updateCard('s_2611_0044', {
			state: 'quote_ready',
			total_cents: 9420,
			step_text: { en: 'Quote ready, 2 lines', fi: 'Tarjous valmis, 2 riviä' }
		}),
	() => updateCard('s_2611_0040', { state: 'confirmed', order_number: 'D-1045' }),
	async () => {
		await addStep('confirmation', 'link_opened', { en: 'Buyer opened the link.', fi: 'Ostaja avasi linkin.' }, { quote_id: 'q_8c21' });
		updateCard(LIVE, { state: 'link_opened' });
	},
	() =>
		updateCard(
			's_2611_0047',
			{
				session_id: 's_2611_0047',
				order_number: null,
				channel: 'mcp',
				client: 'ChatGPT',
				identity_masked: 'p***@example.com',
				state: 'in_conversation',
				state_since: new Date().toISOString(),
				title: { en: '20 kg frozen blueberries by Wednesday', fi: '20 kg pakastemustikoita keskiviikoksi' },
				step_text: { en: 'Searching products', fi: 'Haetaan tuotteita' },
				line_count: 0,
				total_cents: null,
				flags: [],
				next_step: null,
				delivery_date: '2026-11-18'
			},
			{ name: 'Puolukka Pub Oy', exclusions: [] }
		),
	async () => {
		await addStep(
			'confirmation',
			'flags_acknowledged',
			{ en: 'Buyer checked 1 flag.', fi: 'Ostaja tarkisti 1 huomion.' },
			{ quote_id: 'q_8c21', flags: [{ flag_key: 'contains_milk:l2' }] }
		);
		await addStep(
			'confirmation',
			'order_confirmed',
			{
				en: 'Order confirmed. Stock rechecked: unchanged. Order D-1046 created.',
				fi: 'Tilaus vahvistettu. Saldo tarkistettiin uudelleen: ei muutoksia. Tilaus D-1046 luotu.'
			},
			{ quote_id: 'q_8c21', order_number: 'D-1046', total_cents: 6950 }
		);
		updateCard(LIVE, { state: 'confirmed', order_number: 'D-1046' });
	},
	() => updateCard('s_2611_0044', { state: 'awaiting_confirmation', step_text: null })
];

function reset(): void {
	world = mockOverview();
	backlog = [];
	lastLive = (liveCallEvents as AuditEvent[]).at(-1)!;
	cursor = 0;
	for (const sub of subscribers) sendSnapshot(sub);
}

function sendSnapshot(sub: Subscriber): void {
	const snapshot = structuredClone(world);
	snapshot.companies = snapshot.companies
		.map((c) => ({ ...c, orders: c.orders.filter((o) => matchesFilter(o, sub.filter)) }))
		.filter((c) => c.orders.length > 0);
	sub.listener({ event: 'snapshot', id: String(eventId), data: snapshot });
}

let running = false;

async function tick(): Promise<void> {
	if (running) return;
	running = true;
	try {
		if (cursor < SCRIPT.length) await SCRIPT[cursor]();
		cursor++;
		if (cursor >= SCRIPT.length + PAUSE_TICKS) reset();
	} finally {
		running = false;
	}
}

export function connectFake(
	filter: OverviewFilter,
	listener: StreamListener,
	setUp: (up: boolean) => void
): LiveConnection {
	const sub: Subscriber = { filter, listener };
	subscribers.add(sub);
	// Connect asynchronously, like a real stream: up, snapshot, then the missed events.
	const opening = setTimeout(() => {
		setUp(true);
		sendSnapshot(sub);
		for (const message of backlog) listener(message);
	}, 150);
	timer ??= setInterval(tick, TICK_MS);
	return {
		close() {
			clearTimeout(opening);
			subscribers.delete(sub);
			setUp(false);
			if (subscribers.size === 0 && timer) {
				clearInterval(timer);
				timer = null;
			}
		}
	};
}
