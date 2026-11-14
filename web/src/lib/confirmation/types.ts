/**
 * Types for the confirmation page /c/[token].
 *
 * The first part mirrors the shared contract in api/app/schemas/ (#26): quote lines,
 * flags, trace and alternatives, exactly as the engine returns them. Money is in
 * cents, except the unit prices, which are exact decimals in euros.
 *
 * The second part is the confirmation view: what `GET /api/v1/confirmations/{token}`
 * returns (technical-plan.md §9.4). It wraps the contract models with the page state
 * and the buyer's acknowledgements. #47 implements it; keep the two in step.
 */

export type Lang = 'fi' | 'en';

/** `Localized` in the contract: the same text in Finnish and English. */
export type Text = Record<Lang, string>;

// --- Contract mirrors (api/app/schemas/common.py and quote.py) ---

export type RequestedUnit = 'l' | 'kg' | 'piece' | 'sales_unit' | 'package';
export type StockStatus = 'verified' | 'unverified' | 'unavailable';

export interface AskedLine {
	text: string | null;
	quantity: number;
	unit: RequestedUnit;
	package_word: string | null;
	needed_by: string;
}

export interface TraceRemoval {
	reason_code: string;
	count: number;
	text: Text;
}

export interface Trace {
	found: number;
	removed: TraceRemoval[];
	left: number;
	ranking_rule: Text;
}

export interface Alternative {
	product_id: string;
	label: Text;
	quantity_sales_units: number;
	line_total_cents: number;
}

export interface QuoteLine {
	line_id: string;
	group: string | null;
	asked: AskedLine;
	product_id: string;
	name: Text;
	image_url: string | null;
	sales_unit: string;
	sales_unit_label: Text;
	quantity_sales_units: number;
	quantity_in_asked_unit: number;
	unit_price_gross: number;
	price_per_base_unit: number | null;
	base_unit: string | null;
	line_total_cents: number;
	delivery_date: string;
	stock_status: StockStatus;
	origin: string | null;
	reason_codes: string[];
	reason_text: Text;
	trace: Trace;
	alternatives: Alternative[];
}

export interface FlagOption {
	option_id: string;
	label: Text;
	line_total_cents: number;
}

export interface Flag {
	/** Stable across re-quotes, so an acknowledgement carries over. */
	flag_key: string;
	/** A flag code from policy/messages.yaml, e.g. AVAILABILITY_UNVERIFIED. */
	code: string;
	/** Empty for order-wide flags. */
	line_ids: string[];
	kind: 'acknowledge' | 'choose';
	text: Text;
	/** Only for `choose`. */
	options: FlagOption[];
}

export interface GroupSubtotal {
	group: string;
	line_ids: string[];
	subtotal_cents: number;
}

export interface NotOrdered {
	name: string;
	quantity: number | null;
	unit: string | null;
	reason: Text;
}

export interface DeliverySummary {
	earliest: string;
	latest: string;
}

// --- The confirmation view (#47) ---

/**
 * Page states from docs/specs/confirmation-page.md §3. "Updating" is shown by the
 * page itself while an action runs, so it never comes from the server.
 */
export type PageState = 'ready' | 'requote_needed' | 'confirmed' | 'cancelled' | 'expired' | 'invalid';

export type Channel = 'phone' | 'web_chat' | 'webmcp' | 'mcp';

/** A contract flag plus what the confirmation adds to it. */
export interface ViewFlag extends Flag {
	/** The `ack` setting of the code in policy/messages.yaml; `choose` flags always need one. */
	requires_ack: boolean;
	acknowledged_at: string | null;
	/** For `choose`: the option the current quote already reflects. */
	current_option_id: string | null;
	/** New, or its text changed, since the buyer last saw the quote. */
	is_new: boolean;
}

export interface ConfirmationView {
	state: PageState;
	/** Language of the call or chat; the page starts in it. */
	lang: Lang;
	/** Null while expiry is off (the event). */
	expires_at: string | null;
	company: { name: string };
	session: { channel: Channel; started_at: string };
	exclusions: { key: string; label: Text }[];
	quote: {
		quote_id: string;
		version: number;
		/** Sent back with every action so a stale tab can't act on an old quote. */
		quote_hash: string;
		total_cents: number;
		delivery: DeliverySummary | null;
	};
	lines: QuoteLine[];
	groups: GroupSubtotal[];
	not_ordered: NotOrdered[];
	flags: ViewFlag[];
	/** What changed compared with the previous quote, after an edit or a requote. */
	change: QuoteChange | null;
	/** Present once the order is confirmed. */
	order: Order | null;
}

export interface QuoteChange {
	reason: 'edit' | 'requote';
	previous_total_cents: number;
	/** Lines that changed. */
	line_ids: string[];
	/** Shown above the order for a requote: "Stock changed since the quote...". */
	text: Text | null;
}

export interface Order {
	order_number: string;
	confirmed_at: string;
	acknowledged: { flag_key: string; code: string; at: string }[];
}

export type EditOp =
	| { op: 'set_quantity'; line_id: string; quantity: number }
	| { op: 'remove'; line_id: string }
	| { op: 'choose_alternative'; line_id: string; alternative_id: string };
