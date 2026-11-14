/**
 * Types for the demo start page and the phone page (/phone, issue #54).
 *
 * The HTTP shapes follow technical-plan.md §9.2 and the WebSocket messages §9.3, so
 * the fixture (DEMO_SOURCE=fixture) and the real backend (DEMO_SOURCE=api) are
 * interchangeable. Contract mirrors come from api/app/schemas/.
 *
 * This file has no imports, so the mock relay can load it straight from Node.
 */

export type Lang = 'fi' | 'en';

/** `Localized` in the contract: the same text in Finnish and English. */
export type Text = Record<Lang, string>;

/** `Exclusion` in api/app/schemas/common.py: the keys of policy/allergen_rules.yaml. */
export type Exclusion =
	| 'milk_free'
	| 'lactose_free'
	| 'gluten_free'
	| 'nut_free'
	| 'egg_free'
	| 'fish_free'
	| 'vegan';

export const EXCLUSIONS: readonly Exclusion[] = [
	'milk_free',
	'lactose_free',
	'gluten_free',
	'nut_free',
	'egg_free',
	'fish_free',
	'vegan'
];

export function isExclusion(value: unknown): value is Exclusion {
	return typeof value === 'string' && (EXCLUSIONS as readonly string[]).includes(value);
}

/** `KitchenType` in api/app/schemas/common.py: chosen by the server from the number (#32). */
export type KitchenType =
	| 'pizza_restaurant'
	| 'school_kitchen'
	| 'lunch_restaurant'
	| 'bar'
	| 'vegan_catering'
	| 'cafe'
	| 'tech_office';

/** What the visitor typed in the number entry (the phone's set-up and the webshop). */
export interface SetupValues {
	countryCode: string;
	number: string;
	exclusions: Exclusion[];
}

/** `UsualItem` in api/app/schemas/engine.py. */
export interface UsualItem {
	product_id: string;
	name: Text;
	quantity: number;
	unit: string;
}

/** Body of `POST /api/v1/demo/accounts`. */
export interface DemoAccountRequest {
	phone_e164: string;
	exclusions: Exclusion[];
	lang: Lang;
	kitchen_type?: KitchenType | null;
}

/**
 * Response of `POST /api/v1/demo/accounts`: `DemoAccount` in
 * api/app/services/accounts.py, field for field, except the session token and its
 * expiry, which travel in the `simo_session` cookie instead.
 */
export interface DemoAccount {
	user_id: string;
	company_id: string;
	company_name: string;
	phone_masked: string;
	exclusions: Exclusion[];
	usual_items: UsualItem[];
	/** The number's company was made by this request. */
	new_company: boolean;
	/** This browser got a new user (a new, empty inbox). */
	new_user: boolean;
	/**
	 * The kind of kitchen. A new company of a type with default exclusions (vegan
	 * catering: Vegan) gets them when the visitor chose none (#81).
	 */
	kitchen_type?: KitchenType | null;
}

/** Response of `GET /api/v1/me`: `Account` in api/app/services/accounts.py. */
export interface Me {
	user_id: string;
	company_id: string;
	company_name: string;
	phone_masked: string;
	exclusions: Exclusion[];
	lang: Lang;
	kitchen_type?: KitchenType | null;
}

/** One message in the simulated phone inbox (`GET /api/v1/private/inbox`). */
export interface InboxMessage {
	id: string;
	at: string;
	text: string;
	link: string;
}

// --- /voice/ws (technical-plan.md §9.3) ---

export type EndedBy = 'visitor' | 'agent' | 'time_limit' | 'dropped';
export type DeliveryStatus = 'sent' | 'failed' | 'off' | 'none';

export interface EndedMessage {
	type: 'ended';
	duration_s: number;
	ended_by: EndedBy;
	quote_id: string | null;
	total_cents: number | null;
	delivery_status: DeliveryStatus;
	inbox: boolean;
	/** A link was still being sent when the call ended; it may still reach the inbox (#88). */
	link_pending: boolean;
}

/**
 * A caption. `who` is `buyer` or `agent`. As the relay (#52) sends it: a message with
 * `final: false` carries the next piece of the current utterance (a delta); a
 * message with `final: true` closes it, and when it carries text, that text is the
 * whole utterance and replaces the pieces. Gemini sends the caller's text in one
 * piece at the end (spikes/gemini-live), so buyer captions are normally one final.
 */
export interface TranscriptMessage {
	type: 'transcript';
	who: 'buyer' | 'agent';
	text: string;
	final: boolean;
}

/**
 * What S.I.MO is doing, sent by the relay when it changes (#54, #52,
 * technical-plan.md §9.3):
 * - `listening`: waiting for the caller (after `ready`, after each agent turn, after `interrupted`);
 * - `thinking`: the caller's utterance ended, or a tool result went back, and no audio yet;
 * - `working`: Gemini called a tool, named in `tool`, until its result goes back;
 * - `speaking`: the first audio chunk of the turn arrived.
 * `tool` is null except for `working`. A relay that never sends it still works:
 * the browser then infers speaking or listening from the audio it plays.
 */
export type AgentState = 'listening' | 'thinking' | 'working' | 'speaking';

export interface AgentStateMessage {
	type: 'agent_state';
	state: AgentState;
	tool: string | null;
}

export type ServerMessage =
	| { type: 'ready' }
	| { type: 'interrupted' }
	| AgentStateMessage
	| TranscriptMessage
	| EndedMessage;

export type ClientMessage = { type: 'hangup' };

/**
 * WebSocket close codes the call screen understands when no `ended` arrived, as the
 * relay (#52) sends them: 4401 no session (set up the phone again), 4429 the demo
 * limit (docs/specs/call-screen.md §3; for now, this user already has a call). Any
 * other code before `ready`, such as 1011 when Gemini can't be reached, is "could not
 * connect".
 */
export const CLOSE_NO_SESSION = 4401;
export const CLOSE_LIMIT = 4429;
