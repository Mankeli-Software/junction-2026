/**
 * Hand-written types for the public dashboard API (#49, `technical-plan.md` §9.5).
 *
 * Replace with types generated from `/api/v1/openapi.json` by `openapi-typescript`
 * once #49's schemas (`api/app/schemas/dashboard.py`) are on `main`. Fields that #49
 * does not list yet are marked "Assumed" so they are easy to find and agree on.
 */

/** The same text in Finnish and English (`Localized` in `api/app/schemas/common.py`). */
export interface Localized {
	fi: string;
	en: string;
}

export type Lang = 'fi' | 'en';

/** Assumed channel values, one per channel tile on the overview. */
export type Channel = 'phone' | 'web_chat' | 'webmcp' | 'mcp';

export const CHANNELS: readonly Channel[] = ['phone', 'web_chat', 'webmcp', 'mcp'];

/** Session states, `docs/specs/dashboard.md` §4. */
export type SessionState =
	| 'in_conversation'
	| 'needs_clarification'
	| 'quote_ready'
	| 'awaiting_confirmation'
	| 'link_opened'
	| 'confirmed'
	| 'cancelled'
	| 'expired'
	| 'rejected'
	| 'sms_failed'
	| 'callback_requested'
	| 'requote_needed'
	| 'abandoned';

/** The filter groups used by the counters and the filter chips (#49, "States and totals"). */
export type StateGroup = 'active' | 'waiting' | 'confirmed' | 'attention';

/** Kitchen exclusions: the keys of `policy/allergen_rules.yaml` (`Exclusion` in common.py). */
export type Exclusion =
	| 'milk_free'
	| 'lactose_free'
	| 'gluten_free'
	| 'nut_free'
	| 'egg_free'
	| 'fish_free'
	| 'vegan';

// ---------------------------------------------------------------------------
// GET /api/v1/public/orders
// ---------------------------------------------------------------------------

export interface Totals {
	active: number;
	waiting: number;
	confirmed: number;
	attention: number;
	confirmed_cents: number;
	by_channel: Record<Channel, number>;
}

/** A short flag on a card, for "2 flags: stock not confirmed, new product". */
export interface CardFlag {
	code: string;
	/** Assumed: a short label, a few words. */
	short: Localized;
}

export interface OrderCard {
	session_id: string;
	/** "D-1042", null until an order exists. */
	order_number: string | null;
	channel: Channel;
	/** `phone`, `web chat`, `browser agent`, or the OAuth `client_name` ("Claude"). */
	client: string;
	/** Masked as received (`+358 40 *** **12`, `j***@example.com`); never reformatted. */
	identity_masked: string | null;
	state: SessionState;
	/** ISO 8601 timestamp of the last state change. */
	state_since: string;
	title: Localized;
	/** The live activity line while active ("Checking stock for 6 products"). */
	step_text: Localized | null;
	line_count: number;
	total_cents: number | null;
	flags: CardFlag[];
	/** The next step for attention states ("Next: the agent offers to resend the link"). */
	next_step: Localized | null;
	/** Assumed: delivery date (YYYY-MM-DD), drawn on every card in screen 30. */
	delivery_date?: string | null;
	/** Assumed: number of recipes for recipe orders ("5 recipes, 14 lines"). */
	recipe_count?: number | null;
}

export interface CompanyRef {
	name: string;
	exclusions: Exclusion[];
}

export interface CompanyGroup extends CompanyRef {
	orders: OrderCard[];
}

export interface OverviewResponse {
	/** The demo clock, ISO 8601 ("Demo time Thu 12 Nov 09:00"). */
	business_now: string;
	totals: Totals;
	companies: CompanyGroup[];
}

export interface OverviewFilter {
	state: StateGroup | null;
	channel: Channel | null;
}

// ---------------------------------------------------------------------------
// GET /api/v1/public/orders/{session_id}
// ---------------------------------------------------------------------------

export type StockStatus = 'verified' | 'unverified' | 'unavailable';

export interface RemovedProduct {
	product_id: string;
	name: Localized;
}

export interface TraceRemoval {
	reason_code: string;
	count: number;
	text: Localized;
	/** Assumed: the products this filter removed, for the drill-down. */
	products?: RemovedProduct[];
}

export interface RankedCandidate {
	rank: number;
	product_id: string;
	name: Localized;
	price_per_base_unit: number | null;
	stock_status: StockStatus;
	chosen: boolean;
}

/** `Trace` from #26, plus the ranked candidates #49 lists for the summary. */
export interface Trace {
	found: number;
	removed: TraceRemoval[];
	left: number;
	ranking_rule: Localized;
	/** Assumed field name: the remaining candidates in ranked order. */
	ranked?: RankedCandidate[];
}

export interface AskedLine {
	text: string | null;
	quantity: number;
	unit: 'l' | 'kg' | 'piece' | 'sales_unit' | 'package';
	package_word: string | null;
	needed_by: string;
}

/** A quote line, as `QuoteLine` in `api/app/schemas/quote.py` (the fields the dashboard reads). */
export interface SummaryLine {
	line_id: string;
	product_id: string;
	name: Localized;
	image_url: string | null;
	sales_unit: string;
	sales_unit_label: Localized;
	quantity_sales_units: number;
	quantity_in_asked_unit: number;
	unit_price_gross: number;
	price_per_base_unit: number | null;
	base_unit: string | null;
	line_total_cents: number;
	delivery_date: string;
	stock_status: StockStatus;
	reason_text: Localized;
	trace: Trace;
}

export interface NotOrdered {
	name: string;
	quantity: number | null;
	unit: string | null;
	reason: Localized;
}

/** One request ("what was asked") with the lines added for it. Assumed grouping. */
export interface SummaryRequest {
	request_id: string;
	asked: AskedLine;
	/** The asked text as shown ("5 kg ground beef, by Monday"). */
	asked_text: Localized;
	/** Recipe or split group name, when several lines answer one request. */
	group: Localized | null;
	lines: SummaryLine[];
	not_ordered: NotOrdered[];
}

export interface SummaryFlag {
	flag_key: string;
	code: string;
	text: Localized;
	/** Assumed: the second line ("Rapeseed oil 5 l", "Kept 24 l over the exact-fit option"). */
	detail: Localized | null;
	acknowledged_at: string | null;
}

export interface QuoteRef {
	id: string;
	version: number;
	hash: string;
}

export interface AgentInfo {
	/** "Gemini voice agent". */
	name: Localized;
	prompt_version: string | null;
}

export interface OrderSummary {
	session_id: string;
	order_number: string | null;
	company: CompanyRef;
	channel: Channel;
	client: string;
	identity_masked: string | null;
	state: SessionState;
	state_since: string;
	/** "by the buyer, after checking 3 flags". */
	status_line: Localized | null;
	delivery_date: string | null;
	total_cents: number | null;
	requests: SummaryRequest[];
	flags: SummaryFlag[];
	quote: QuoteRef | null;
	/** Null until #40 signs quotes. */
	signature_valid: boolean | null;
	/** Assumed: the agent and prompt version that ran the session, when known. */
	agent?: AgentInfo | null;
}

// ---------------------------------------------------------------------------
// GET /orders/{session_id}/steps, /transcript, /events
// ---------------------------------------------------------------------------

/** Assumed actor values. */
export type Actor = 'buyer' | 'agent' | 'mcp' | 'engine' | 'relay' | 'confirmation' | (string & {});

export interface Step {
	/** Place in the global chain. */
	seq: number;
	/** Number within the order ("#1" to "#31"). */
	order_index: number;
	/** ISO 8601 with offset, exactly as hashed. */
	at: string;
	actor: Actor;
	type: string;
	text: Localized;
	payload_hash: string;
	prev_hash: string;
	/** Hash of the previous event in the same session; null for the session's first event. */
	session_prev_hash: string | null;
	hash: string;
}

export interface TranscriptLine {
	at: string;
	who: 'buyer' | 'agent';
	text: string;
	lang: Lang;
}

/** A full redacted event, as `/events` returns it. Payload shapes depend on `type`. */
export interface AuditEvent extends Step {
	session_id: string;
	channel: Channel;
	identity_masked: string | null;
	quote_id: string | null;
	payload: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// SSE /api/v1/public/stream
// ---------------------------------------------------------------------------

/** Assumed: `order_updated` carries the company with the card, so a new card can be placed. */
export interface OrderUpdated {
	company: CompanyRef;
	order: OrderCard;
	/** Assumed: fresh totals, when the server sends them. Otherwise the client adjusts its own. */
	totals?: Totals;
}

export interface StepEvent {
	session_id: string;
	step: Step;
}

export interface TranscriptEvent {
	session_id: string;
	line: TranscriptLine;
}

export type StreamMessage =
	| { event: 'snapshot'; id: string | null; data: OverviewResponse }
	| { event: 'order_updated'; id: string | null; data: OrderUpdated }
	| { event: 'step'; id: string | null; data: StepEvent }
	| { event: 'transcript'; id: string | null; data: TranscriptEvent };
