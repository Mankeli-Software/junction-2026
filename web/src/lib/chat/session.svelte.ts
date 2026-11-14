/**
 * One chat conversation in the page (#57): the message list, the A2UI surfaces, and
 * one turn at a time against a chat endpoint (`/api/v1/chat`, or the confirmation
 * page's `/api/v1/confirmations/{token}/chat`).
 */
import { SurfaceStore } from '#lib/a2ui/surfaces.svelte.js';
import type { A2uiClientAction } from '#lib/a2ui/protocol.js';
import type { Lang } from '#lib/demo/types.js';
import { t } from './i18n';
import { actionEcho, applyEvent, portionsFrom, readingErrorKey, type ChatMessage, type Working } from './messages';
import { postChat, type ChatEvent, type ChatRequest } from './stream';

export interface TurnResult {
	/** The quote id `done` carried, or null. */
	quoteId: string | null;
	/** A tool that changes the quote ran in this turn. */
	quoteTouched: boolean;
}

export interface ChatSessionOptions {
	endpoint: string;
	lang: () => Lang;
	/** After each `done`. */
	onDone?: (result: TurnResult) => void;
	/** Photo upload, or null where photos are off (the confirmation page). */
	photoEndpoint?: string | null;
	fetcher?: typeof fetch;
}

const QUOTE_TOOLS = new Set(['build_quote', 'update_quote']);

export class ChatSession {
	messages = $state<ChatMessage[]>([]);
	working = $state<Working | null>(null);
	busy = $state(false);
	/** Bumped after each `done`, so cards reload data that may have changed (context `revision`). */
	revision = $state(0);
	conversationId: string | null = null;
	readonly store: SurfaceStore;
	#options: ChatSessionOptions;
	#seq = 0;
	#photoUrls: string[] = [];

	constructor(options: ChatSessionOptions) {
		this.#options = options;
		this.store = new SurfaceStore((action) => void this.sendAction(action));
	}

	get started(): boolean {
		return this.messages.length > 0;
	}

	#id = () => `m${++this.#seq}`;

	async send(text: string): Promise<void> {
		const message = text.trim().slice(0, 2000);
		if (!message || this.busy) return;
		this.messages.push({ kind: 'buyer', id: this.#id(), text: message });
		await this.#turn({ message, action: null, attachment_draft_id: null });
	}

	async sendAction(action: A2uiClientAction): Promise<void> {
		if (this.busy) return;
		const source = this.store.surfaces[action.surfaceId]?.components[action.sourceComponentId];
		this.messages.push({ kind: 'action', id: this.#id(), text: actionEcho(this.#options.lang(), action, source) });
		await this.#turn({ message: null, action, attachment_draft_id: null });
	}

	/**
	 * A recipe photo: shown from the local file, read into a draft
	 * (`POST /api/v1/recipe-drafts/read`), then sent as a turn with the draft attached.
	 */
	async sendPhoto(file: File, text: string): Promise<void> {
		const endpoint = this.#options.photoEndpoint;
		if (!endpoint || this.busy) return;
		const words = text.trim().slice(0, 2000);
		const url = URL.createObjectURL(file);
		this.#photoUrls.push(url);
		this.messages.push({ kind: 'photo', id: this.#id(), url, text: words });
		this.busy = true;
		this.working = { kind: 'reading' };

		const form = new FormData();
		form.append('photo', file);
		const portions = portionsFrom(words);
		if (portions) form.append('portions', String(portions));
		let draftId: string | null = null;
		let status = 0;
		try {
			const response = await (this.#options.fetcher ?? fetch)(endpoint, {
				method: 'POST',
				credentials: 'same-origin',
				headers: { accept: 'application/json' },
				body: form
			});
			status = response.status;
			if (response.ok) {
				const draft = (await response.json()) as { draft_id?: unknown };
				if (typeof draft.draft_id === 'string') draftId = draft.draft_id;
				else status = 502;
			}
		} catch {
			status = 0;
		}
		if (!draftId) {
			this.messages.push({ kind: 'error', id: this.#id(), key: readingErrorKey(status) });
			this.working = null;
			this.busy = false;
			return;
		}
		this.busy = false;
		// The contract needs a message or an action: a short line when the buyer wrote nothing.
		await this.#turn({
			message: words || t(this.#options.lang(), 'photoMessage'),
			action: null,
			attachment_draft_id: draftId
		});
	}

	async #turn(body: Omit<ChatRequest, 'conversation_id'>): Promise<void> {
		this.busy = true;
		this.working = { kind: 'thinking' };
		let quoteTouched = false;
		let done: { quoteId: string | null } | null = null;
		const onEvent = (event: ChatEvent) => {
			if (event.type === 'tool' && QUOTE_TOOLS.has(event.name)) quoteTouched = true;
			const state = { messages: this.messages, working: this.working, conversationId: this.conversationId };
			const effect = applyEvent(state, event, this.#id);
			this.messages = state.messages;
			this.working = state.working;
			this.conversationId = state.conversationId;
			if (effect.envelopes) this.store.process(effect.envelopes);
			if (effect.done) done = effect.done;
		};
		try {
			await postChat(
				this.#options.endpoint,
				{ conversation_id: this.conversationId, ...body },
				onEvent,
				this.#options.fetcher
			);
		} finally {
			this.working = null;
			this.busy = false;
		}
		if (done) this.revision += 1;
		if (done) this.#options.onDone?.({ quoteId: (done as { quoteId: string | null }).quoteId, quoteTouched });
	}

	/** Frees the photo previews. */
	dispose(): void {
		for (const url of this.#photoUrls) URL.revokeObjectURL(url);
		this.#photoUrls = [];
	}
}
