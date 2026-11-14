/**
 * The chat's message list and how stream events change it (docs/plans/57-a2ui-chat.md
 * §3, §4.C). Plain functions over plain data, so they are tested without a page:
 * `ChatSession` (session.svelte.ts) keeps the same shapes in `$state`.
 */
import type { A2uiClientAction, A2uiComponent, A2uiServerEnvelope } from '#lib/a2ui/protocol.js';
import type { Lang } from '#lib/demo/types.js';
import { dayName, t, type ChatKey } from './i18n';
import type { ChatEvent } from './stream';

export type ChatMessage =
	/** What the buyer typed. */
	| { kind: 'buyer'; id: string; text: string }
	/** A card button the buyer pressed, in plain words (outlined bubble). */
	| { kind: 'action'; id: string; text: string }
	/** A recipe photo from the local file, with what the buyer wrote next to it. */
	| { kind: 'photo'; id: string; url: string; text: string }
	/** S.I.MO's words, built from `text` deltas. */
	| { kind: 'agent'; id: string; text: string }
	/** An A2UI surface, where its `createSurface` came in the stream. */
	| { kind: 'surface'; id: string; surfaceId: string }
	/** A turn that failed. `key` is the text to show. */
	| { kind: 'error'; id: string; key: ChatKey };

/** What the "working" line says: a tool's name, or one of the panel's own states. */
export type Working = { kind: 'thinking' } | { kind: 'reading' } | { kind: 'tool'; name: string };

export interface ChatState {
	messages: ChatMessage[];
	working: Working | null;
	conversationId: string | null;
}

/** What the session does after an event, beyond the state change. */
export interface EventEffect {
	envelopes?: A2uiServerEnvelope[];
	done?: { quoteId: string | null };
	error?: string;
}

/** Applies one stream event to the state (mutating it) and says what else to do. */
export function applyEvent(state: ChatState, event: ChatEvent, newId: () => string): EventEffect {
	switch (event.type) {
		case 'start':
			state.conversationId = event.conversation_id;
			return {};
		case 'text': {
			if (event.delta === '') return {};
			state.working = null;
			const last = state.messages[state.messages.length - 1];
			if (last?.kind === 'agent') last.text += event.delta;
			else state.messages.push({ kind: 'agent', id: newId(), text: event.delta });
			return {};
		}
		case 'a2ui': {
			for (const envelope of event.envelopes) {
				if ('createSurface' in envelope && typeof envelope.createSurface?.surfaceId === 'string') {
					const surfaceId = envelope.createSurface.surfaceId;
					if (!state.messages.some((m) => m.kind === 'surface' && m.surfaceId === surfaceId)) {
						state.messages.push({ kind: 'surface', id: newId(), surfaceId });
					}
				} else if ('deleteSurface' in envelope && typeof envelope.deleteSurface?.surfaceId === 'string') {
					const surfaceId = envelope.deleteSurface.surfaceId;
					state.messages = state.messages.filter((m) => !(m.kind === 'surface' && m.surfaceId === surfaceId));
				}
			}
			return { envelopes: event.envelopes };
		}
		case 'tool':
			state.working = event.status === 'started' ? { kind: 'tool', name: event.name } : { kind: 'thinking' };
			return {};
		case 'done':
			state.working = null;
			return { done: { quoteId: event.quote_id } };
		case 'error':
			state.working = null;
			state.messages.push({ kind: 'error', id: newId(), key: errorKey(event.code) });
			return { error: event.code };
	}
}

export function errorKey(code: string): ChatKey {
	switch (code) {
		case 'not_configured':
			return 'errorNotConfigured';
		case 'busy':
			return 'errorBusy';
		case 'network':
			return 'errorNetwork';
		case 'signed_out':
			return 'errorSignedOut';
		default:
			return 'errorFailed';
	}
}

/** The short sentence for a refused `POST /api/v1/recipe-drafts/read`. */
export function readingErrorKey(status: number): ChatKey {
	switch (status) {
		case 413:
			return 'read413';
		case 415:
			return 'read415';
		case 422:
			return 'read422';
		case 502:
			return 'read502';
		case 503:
			return 'read503';
		case 504:
			return 'read504';
		case 401:
		case 403:
			return 'errorSignedOut';
		case 0:
			return 'errorNetwork';
		default:
			return 'errorFailed';
	}
}

const TOOL_WORKING: Record<string, ChatKey> = {
	build_quote: 'building',
	update_quote: 'building',
	search_products: 'products',
	search_recipes: 'recipes',
	get_recipe: 'recipes',
	show_menu: 'recipes',
	propose_recipe: 'reading',
	confirm_recipe: 'building',
	request_confirmation: 'sending',
	get_customer_context: 'kitchen',
	get_order_status: 'status'
};

export function workingKey(working: Working): ChatKey {
	if (working.kind === 'thinking') return 'thinking';
	if (working.kind === 'reading') return 'reading';
	return TOOL_WORKING[working.name] ?? 'working';
}

const str = (value: unknown): string | null => (typeof value === 'string' && value.trim() !== '' ? value.trim() : null);

/**
 * A card action as the buyer's turn, in plain words in the shop's language. Known
 * actions (plan §3) have their own sentence; a layout `Button` shows its label, as in
 * the design (UI-02, "Buyer action echo"); anything else its name in words.
 */
export function actionEcho(
	lang: Lang,
	action: A2uiClientAction,
	source: A2uiComponent | undefined
): string {
	const context = action.context ?? {};
	const label = source?.component === 'Button' ? str(source.label) : null;
	switch (action.name) {
		case 'send_for_confirmation':
			return t(lang, 'actionSend');
		case 'recipe_confirmed':
			return t(lang, 'actionRecipeConfirmed');
		case 'recipe_discarded':
			return t(lang, 'actionRecipeDiscarded');
		case 'recipe_edit_as_new':
			return t(lang, 'actionRecipeEditAsNew');
		case 'recipe_selected': {
			const portions = Number(context.portions);
			return Number.isInteger(portions) && portions > 0
				? t(lang, 'actionRecipeSelected', { n: portions })
				: t(lang, 'actionRecipeSelectedPlain');
		}
		case 'recipe_swap':
			return t(lang, 'actionRecipeSwap');
		case 'clarification_answered':
			return str(context.label) ?? label ?? t(lang, 'actionClarification');
		case 'menu_swap_day': {
			const day = dayName(lang, context.day);
			return day ? t(lang, 'actionMenuSwap', { day }) : t(lang, 'actionMenuSwapPlain');
		}
		case 'menu_build':
			return t(lang, 'actionMenuBuild');
	}
	if (label) return label;
	const words = action.name.replace(/[_.-]+/g, ' ').trim();
	return words ? words[0].toUpperCase() + words.slice(1) : '...';
}

/**
 * The portion count in what the buyer wrote next to a photo ("for 120 please",
 * "80 annosta"), for the reading's `portions`. Null when there is none.
 */
export function portionsFrom(text: string): number | null {
	const match =
		/(\d{1,4})\s*(?:portions?|people|persons|servings|guests|annosta|annokselle|annoksen|hengelle|henkeä|hengen|hlö)/i.exec(text) ??
		/\b(?:for|varten)\s+(\d{1,4})\b/i.exec(text);
	if (!match) return null;
	const n = Number(match[1]);
	return n >= 1 && n <= 1000 ? n : null;
}

/**
 * Agent text with any confirmation link taken out. The server already drops text
 * with `/c/` (plan §3); this is the page's own guard, because a browser agent reads
 * this page (vision §8). Text is never turned into links anyway.
 */
export function withoutLinks(lang: Lang, text: string): string {
	return text.replace(/(?:https?:\/\/\S*)?\/c\/[^\s)"'<>]+/gi, t(lang, 'linkHidden'));
}
