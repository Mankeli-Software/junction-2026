/**
 * The mock dashboard backend, used by the `load` functions when `PUBLIC_DASHBOARD_MOCK=1`.
 * Serves the fixtures that reproduce screens 30 to 33, with the same interface as `api.ts`.
 */
import { NotFoundError, type DashboardApi } from '../api';
import d1042Events from '../fixtures/d1042-events.json';
import d1042Tampered from '../fixtures/d1042-events-tampered.json';
import d1042Summary from '../fixtures/d1042-summary.json';
import d1042Transcript from '../fixtures/d1042-transcript.json';
import liveCallEvents from '../fixtures/live-call-events.json';
import liveCallTranscript from '../fixtures/live-call-transcript.json';
import overviewFixture from '../fixtures/overview.json';
import { computeHash, payloadHash, sha256Hex } from '../hash';
import { matchesFilter } from '../states';
import type {
	AuditEvent,
	CompanyRef,
	OrderCard,
	OrderSummary,
	OverviewResponse,
	Step,
	TranscriptLine
} from '../types';

/** The tampered copy of D-1042, reachable at /dashboard/s_2611_0042_tampered/audit. */
export const TAMPERED_SESSION_ID = 's_2611_0042_tampered';
export const D1042_SESSION_ID = 's_2611_0042';
export const LIVE_CALL_SESSION_ID = 's_2611_0043';

const overview = overviewFixture as OverviewResponse;

/** Seconds in the current state for the cards whose timer runs, so "Waiting, 2 min" stays true. */
const AGE_SECONDS: Record<string, number> = {
	s_2611_0043: 72,
	s_2611_0044: 40,
	s_2611_0040: 120,
	s_2611_0041: 360,
	s_2611_0038: 900
};

function freshOverview(now = Date.now()): OverviewResponse {
	const copy = structuredClone(overview);
	for (const company of copy.companies) {
		for (const order of company.orders) {
			const age = AGE_SECONDS[order.session_id];
			if (age !== undefined) order.state_since = new Date(now - age * 1000).toISOString();
		}
	}
	return copy;
}

export function mockOverview(): OverviewResponse {
	return freshOverview();
}

function findCard(sessionId: string): { company: CompanyRef; order: OrderCard } | null {
	for (const company of overview.companies) {
		const order = company.orders.find((o) => o.session_id === sessionId);
		if (order) return { company: { name: company.name, exclusions: company.exclusions }, order };
	}
	return null;
}

function toStep(event: AuditEvent): Step {
	const { seq, order_index, at, actor, type, text, payload_hash, prev_hash, session_prev_hash, hash } = event;
	return { seq, order_index, at, actor, type, text, payload_hash, prev_hash, session_prev_hash, hash };
}

// A short chain for every other card, so each one opens and verifies.
const generated = new Map<string, Promise<AuditEvent[]>>();

interface GenSpec {
	type: string;
	actor: string;
	en: string;
	fi: string;
	payload: Record<string, unknown>;
}

function genericSpecs(card: OrderCard, company: CompanyRef): GenSpec[] {
	const quoteId = `q_${card.session_id.slice(-4)}`;
	const specs: GenSpec[] = [
		{
			type: 'session_started',
			actor: card.channel === 'phone' ? 'relay' : 'mcp',
			en: `Session started. ${company.name}, ${card.client}.`,
			fi: `Istunto alkoi. ${company.name}, ${card.client}.`,
			payload: { channel: card.channel, client: card.client, company: company.name }
		},
		{
			type: 'tool_called',
			actor: 'mcp',
			en: `build_quote, ${card.title.en}`,
			fi: `build_quote, ${card.title.fi}`,
			payload: { call_id: 'call_1', tool: 'build_quote', summary: card.title, args: { request: card.title.en } }
		}
	];
	if (card.total_cents !== null) {
		specs.push(
			{
				type: 'quote_built',
				actor: 'engine',
				en: `Quote v1 ready: ${card.line_count} lines.`,
				fi: `Tarjous v1 valmis: ${card.line_count} riviä.`,
				payload: { quote_id: quoteId, version: 1, lines: card.line_count, total_cents: card.total_cents }
			},
			{
				type: 'tool_returned',
				actor: 'mcp',
				en: 'ready',
				fi: 'ready',
				payload: { call_id: 'call_1', tool: 'build_quote', result: { decision: 'ready', quote_id: quoteId } }
			}
		);
	}
	const waitingOrLater = ['awaiting_confirmation', 'link_opened', 'confirmed'].includes(card.state);
	if (waitingOrLater) {
		specs.push({
			type: 'sms_sent',
			actor: 'confirmation',
			en: `Link sent to the demo phone inbox${card.identity_masked ? ` for ${card.identity_masked}` : ''}.`,
			fi: `Linkki lähetettiin demopuhelimen saapuneisiin${card.identity_masked ? ` (${card.identity_masked})` : ''}.`,
			payload: { to: card.identity_masked, inbox: true }
		});
	}
	if (card.state === 'link_opened' || card.state === 'confirmed') {
		specs.push({
			type: 'link_opened',
			actor: 'confirmation',
			en: 'Buyer opened the link.',
			fi: 'Ostaja avasi linkin.',
			payload: { quote_id: quoteId }
		});
	}
	if (card.state === 'confirmed') {
		specs.push({
			type: 'order_confirmed',
			actor: 'confirmation',
			en: `Order confirmed. Order ${card.order_number ?? ''} created.`.replace(' .', '.'),
			fi: `Tilaus vahvistettu. Tilaus ${card.order_number ?? ''} luotu.`.replace(' .', '.'),
			payload: { quote_id: quoteId, order_number: card.order_number }
		});
	}
	if (card.state === 'sms_failed') {
		specs.push({
			type: 'sms_failed',
			actor: 'confirmation',
			en: 'SMS delivery failed. The link is still in the demo phone inbox.',
			fi: 'Tekstiviestin toimitus epäonnistui. Linkki on yhä demopuhelimen saapuneissa.',
			payload: { to: card.identity_masked, error: 'undelivered' }
		});
	}
	return specs;
}

async function generateEvents(sessionId: string): Promise<AuditEvent[]> {
	const found = findCard(sessionId);
	if (!found) throw new NotFoundError('Order');
	const { order, company } = found;
	const specs = genericSpecs(order, company);
	const index = overview.companies.flatMap((c) => c.orders).findIndex((o) => o.session_id === sessionId);
	const end = Date.parse(order.state_since);
	let seq = 2000 + index * 100;
	let prev = await sha256Hex(new TextEncoder().encode(`before ${sessionId}`));
	let sessionPrev: string | null = null;
	const events: AuditEvent[] = [];
	for (const [i, spec] of specs.entries()) {
		seq++;
		const at = new Date(end - (specs.length - 1 - i) * 7000).toISOString().replace('.000Z', '+00:00');
		const payload_hash = await payloadHash(spec.payload);
		const hash = await computeHash({ prev_hash: prev, payload_hash, seq, at, type: spec.type });
		events.push({
			seq,
			order_index: i + 1,
			at,
			actor: spec.actor,
			type: spec.type,
			text: { en: spec.en, fi: spec.fi },
			payload_hash,
			prev_hash: prev,
			session_prev_hash: sessionPrev,
			hash,
			session_id: sessionId,
			channel: order.channel,
			identity_masked: order.identity_masked,
			quote_id: null,
			payload: spec.payload
		});
		prev = hash;
		sessionPrev = hash;
	}
	return events;
}

async function eventsFor(sessionId: string): Promise<AuditEvent[]> {
	if (sessionId === D1042_SESSION_ID) return d1042Events as AuditEvent[];
	if (sessionId === TAMPERED_SESSION_ID) {
		return (d1042Tampered as AuditEvent[]).map((e) => ({ ...e, session_id: TAMPERED_SESSION_ID }));
	}
	if (sessionId === LIVE_CALL_SESSION_ID) return liveCallEvents as AuditEvent[];
	let cached = generated.get(sessionId);
	if (!cached) {
		cached = generateEvents(sessionId);
		generated.set(sessionId, cached);
		cached.catch(() => generated.delete(sessionId));
	}
	return cached;
}

function genericSummary(sessionId: string): OrderSummary {
	const found = findCard(sessionId);
	if (!found) throw new NotFoundError('Order');
	const { order, company } = found;
	const fresh = freshOverview()
		.companies.flatMap((c) => c.orders)
		.find((o) => o.session_id === sessionId)!;
	return {
		session_id: order.session_id,
		order_number: order.order_number,
		company,
		channel: order.channel,
		client: order.client,
		identity_masked: order.identity_masked,
		state: order.state,
		state_since: fresh.state_since,
		status_line: order.next_step ?? order.step_text,
		delivery_date: order.delivery_date ?? null,
		total_cents: order.total_cents,
		requests: [],
		flags: [],
		quote: null,
		signature_valid: null,
		agent:
			order.channel === 'phone'
				? { name: { en: 'Gemini voice agent', fi: 'Gemini-puheagentti' }, prompt_version: 'v7' }
				: null
	};
}

export const mockApi: DashboardApi = {
	async overview(filter) {
		const data = freshOverview();
		data.companies = data.companies
			.map((c) => ({ ...c, orders: c.orders.filter((o) => matchesFilter(o, filter)) }))
			.filter((c) => c.orders.length > 0);
		return data;
	},
	async summary(sessionId) {
		if (sessionId === D1042_SESSION_ID) return d1042Summary as OrderSummary;
		if (sessionId === TAMPERED_SESSION_ID) {
			return { ...(d1042Summary as OrderSummary), session_id: TAMPERED_SESSION_ID };
		}
		return genericSummary(sessionId);
	},
	async steps(sessionId) {
		return (await eventsFor(sessionId)).map(toStep);
	},
	async transcript(sessionId) {
		if (sessionId === D1042_SESSION_ID || sessionId === TAMPERED_SESSION_ID) {
			return d1042Transcript as TranscriptLine[];
		}
		if (sessionId === LIVE_CALL_SESSION_ID) return liveCallTranscript as TranscriptLine[];
		await eventsFor(sessionId);
		return [];
	},
	async events(sessionId) {
		return eventsFor(sessionId);
	}
};
