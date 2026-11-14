/**
 * Types for the public dashboard API (#49, `technical-plan.md` §9.5), taken from the
 * generated contract (`src/lib/generated/openapi.ts`, from `api/app/schemas/dashboard.py`).
 * Regenerate it as `web/README.md` says after the schemas change.
 *
 * The stream's event bodies are not in the OpenAPI document, so they are written out here
 * from the generated parts, as `OrderUpdated`, `StepEvent` and `TranscriptEvent` in
 * `api/app/schemas/dashboard.py`.
 */
import type { components } from '../generated/openapi';

type Schemas = components['schemas'];

/** The same text in Finnish and English. */
export type Localized = Schemas['Localized'];
export type Lang = 'fi' | 'en';

export type Channel = Schemas['Channel'];
export const CHANNELS: readonly Channel[] = ['phone', 'web_chat', 'webmcp', 'mcp'];

/** Session states, `docs/specs/dashboard.md` §4. */
export type SessionState = Schemas['SessionState'];
/** The filter groups used by the counters and the filter chips. */
export type StateGroup = Schemas['StateGroup'];
/** Kitchen exclusions: the keys of `policy/allergen_rules.yaml`. */
export type Exclusion = Schemas['Exclusion'];
export type StockStatus = Schemas['StockStatus'];

// GET /api/v1/public/orders
export type Totals = Schemas['Totals'];
export type CardFlag = Schemas['CardFlag'];
export type OrderCard = Schemas['OrderCard'];
export type CompanyRef = Schemas['CompanyRef'];
export type CompanyGroup = Schemas['CompanyGroup'];
export type OverviewResponse = Schemas['OverviewResponse'];

export interface OverviewFilter {
	state: StateGroup | null;
	channel: Channel | null;
}

// GET /api/v1/public/orders/{session_id}
export type RemovedProduct = Schemas['RemovedProduct'];
export type TraceRemoval = Schemas['SummaryTraceRemoval'];
export type RankedCandidate = Schemas['RankedCandidate'];
/** A line's trace; `ranked` is `[]` until the engine records the candidates (#36, #39). */
export type Trace = Schemas['SummaryTrace'];
export type AskedLine = Schemas['AskedLine'];
export type SummaryLine = Schemas['SummaryLine'];
export type NotOrdered = Schemas['NotOrdered'];
export type SummaryRequest = Schemas['SummaryRequest'];
export type SummaryFlag = Schemas['SummaryFlag'];
export type QuoteRef = Schemas['QuoteRef'];
export type AgentInfo = Schemas['AgentInfo'];
/** `signature_valid` is null until quotes are signed (#40). */
export type OrderSummary = Schemas['OrderSummary'];

// GET /orders/{session_id}/steps, /transcript, /events
/** One audit event without its payload; `text` has the sentences with nulls as "". */
export type Step = Schemas['Step'];
export type TranscriptLine = Schemas['TranscriptLine'];
/**
 * A full redacted event. `payload_hash` covers `payload`, `text_fi` and `text_en` exactly
 * as sent (nulls kept). `payload` is null when it was deleted after the event.
 */
export type AuditEvent = Schemas['AuditEvent'];
export type VerifyResponse = Schemas['VerifyResult'];

// SSE /api/v1/public/stream
/** The card with its company, so a new card can be placed, and the fresh totals. */
export interface OrderUpdated {
	company: CompanyRef;
	order: OrderCard;
	/** The API always sends them; optional in its schema. */
	totals?: Totals | null;
}

export interface StepEvent {
	session_id: string;
	step: Step;
}

export interface TranscriptEvent {
	session_id: string;
	line: TranscriptLine;
}

/**
 * One stream event. `id` is the `status_events` id; one id can carry a `step`, a
 * `transcript` and an `order_updated`. The first `snapshot` has no id while nothing has
 * happened yet.
 */
export type StreamMessage =
	| { event: 'snapshot'; id: string | null; data: OverviewResponse }
	| { event: 'order_updated'; id: string | null; data: OrderUpdated }
	| { event: 'step'; id: string | null; data: StepEvent }
	| { event: 'transcript'; id: string | null; data: TranscriptEvent };
