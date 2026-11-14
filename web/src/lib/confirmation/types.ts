/**
 * The confirmation view: what `GET /api/v1/confirmations/{token}` returns
 * (technical-plan.md §9.4) and what the page at /c/[token] renders.
 *
 * Plan §9.4 names only the top-level fields. The shapes of requests, lines, flags,
 * alternatives and the trace are proposed here (issue #55) and are meant to be
 * aligned with the contract in api/app/schemas/ (#26) once it exists.
 *
 * Every text the buyer reads comes from the engine in both languages (`Text`).
 * Money is in cents, gross (VAT included). Times are ISO 8601 with offset.
 */

export type Lang = 'fi' | 'en';

/** A text the engine wrote in both page languages. */
export type Text = Record<Lang, string>;

/**
 * Page states from docs/specs/confirmation-page.md §3. "Updating" is shown by the
 * page itself while an action runs, so it never comes from the server.
 */
export type PageState =
	| 'ready'
	| 'requote_needed'
	| 'confirmed'
	| 'cancelled'
	| 'expired'
	| 'invalid';

export type Channel = 'phone' | 'web_chat' | 'webmcp' | 'mcp';

export interface ConfirmationView {
	state: PageState;
	/** Language of the call or chat; the page starts in it. */
	lang: Lang;
	/** Null while expiry is off (the event). */
	expires_at: string | null;
	company: { name: string };
	session: { channel: Channel; started_at: string };
	/** The kitchen's exclusions, e.g. milk-free. */
	exclusions: { key: string; label: Text }[];
	quote: {
		id: string;
		version: number;
		/** Sent back with every action so a stale tab can't act on an old quote. */
		hash: string;
		total_cents: number;
		delivery: { date: string };
	};
	requests: OrderRequest[];
	flags: Flag[];
	/** What changed compared with the previous quote, after an edit or a requote. */
	change: QuoteChange | null;
	/** Present once the order is confirmed. */
	order: Order | null;
}

/** One thing the buyer asked for, with the line or lines chosen for it. */
export interface OrderRequest {
	id: string;
	/** What we understood, in the buyer's terms: "5 kg ground beef by Monday". */
	asked: Text;
	lines: Line[];
	/** Recipe ingredients that were not ordered ("salt, flour"). */
	not_ordered: Text[];
}

export interface Line {
	id: string;
	product: { id: string; name: Text; image_url: string | null };
	/** Quantity in sales units. */
	quantity: number;
	/** The sales unit, e.g. "pcs" or "cases". */
	sales_unit: Text;
	/** Sales units and the asked unit together: "2 cases = 24 l". */
	quantity_text: Text;
	/** Unit prices for the sheet: "8,38 € / kg, 20,95 € / pcs incl. VAT". */
	unit_price_text: Text;
	line_total_cents: number;
	/** One line on why this product: "Cheapest mince that arrives Monday". */
	why: Text;
	trace: Trace;
	/** The offered alternatives, including the product in the order (`in_order`). */
	alternatives: Alternative[];
	min_quantity: number;
	/** Null when there is no known upper limit. */
	max_quantity: number | null;
	/** Keys of the flags about this line. */
	flag_keys: string[];
}

/** The buyer-facing "why this product" trace. */
export interface Trace {
	found: number;
	/** "mince products found" */
	found_text: Text;
	removed: { count: number; reason: Text }[];
	remaining: number;
	/** "safe and on time. We picked the cheapest." */
	decided_by: Text;
}

export interface Alternative {
	id: string;
	name: Text;
	/** "In your order, in stock", "Stock not confirmed". */
	note: Text;
	/** "8,38 € / kg" */
	unit_price_text: Text;
	in_order: boolean;
}

export type FlagKind =
	| 'unusual_quantity'
	| 'substitute'
	| 'rounded_up'
	| 'stock_not_confirmed'
	| 'no_allergen_info'
	| 'new_product'
	| 'possible_duplicate'
	| 'pack_size_from_name'
	| 'exact_fit_available';

export interface Flag {
	/** Stable across quote versions, so an acknowledgement carries over. */
	key: string;
	kind: FlagKind;
	/** The line it is about; null for order-wide flags. */
	line_id: string | null;
	title: Text;
	text: Text;
	acknowledged: boolean;
	/** New or changed since the buyer last saw the quote. */
	is_new: boolean;
	/** A flag that asks the buyer to pick, e.g. keep the rounded amount or take an exact fit. */
	choice: FlagChoice | null;
}

export interface FlagChoice {
	options: FlagOption[];
}

export interface FlagOption {
	id: string;
	/** The alternative to switch to; null means "keep what is in the quote". */
	alternative_id: string | null;
	title: Text;
	text: Text;
	/** True for the option that is already in the quote. */
	current: boolean;
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
	acknowledged: { flag_key: string; title: Text; at: string }[];
}

export type EditOp =
	| { op: 'set_quantity'; line_id: string; quantity: number }
	| { op: 'remove'; line_id: string }
	| { op: 'choose_alternative'; line_id: string; alternative_id: string };
