/**
 * `ChatData` over the REST API with the session cookie (technical-plan.md §9.1, §9.6;
 * docs/plans/57-a2ui-chat.md §3). Paths as in `src/lib/generated/openapi.json`; the two
 * `/chat/...` loaders come with the chat agent (#57).
 */
import type { ChatData, ChatMenu, ConfirmDraft, Quote, Recipe, RecipeDraft, SentLatest } from './types';

/** A failed call. `status` 404 means the id is unknown to this session. */
export class ApiError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
		this.name = 'ApiError';
	}
}

/** True for "not found" (and the 422 a malformed id gets): the card says so instead of "try again". */
export function isNotFound(error: unknown): boolean {
	return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
	const response = await fetch(path, {
		...init,
		credentials: 'same-origin',
		headers: {
			accept: 'application/json',
			...(init.body ? { 'content-type': 'application/json' } : {})
		}
	});
	if (!response.ok) throw new ApiError(`${init.method ?? 'GET'} ${path}: ${response.status}`, response.status);
	return (await response.json()) as T;
}

const id = encodeURIComponent;

export const apiData: ChatData = {
	getQuote: (quoteId) => call<Quote>(`/api/v1/quotes/${id(quoteId)}`),
	getRecipe: (recipeId, portions) =>
		call<Recipe>(`/api/v1/recipes/${id(recipeId)}?portions=${encodeURIComponent(String(portions))}`),
	getDraft: (draftId) => call<RecipeDraft>(`/api/v1/recipe-drafts/${id(draftId)}`),
	confirmDraft: (draftId, edits: ConfirmDraft) =>
		call<RecipeDraft>(`/api/v1/recipe-drafts/${id(draftId)}/confirm`, {
			method: 'POST',
			body: JSON.stringify(edits)
		}),
	discardDraft: (draftId) => call<RecipeDraft>(`/api/v1/recipe-drafts/${id(draftId)}/discard`, { method: 'POST' }),
	copyDraft: (draftId) => call<RecipeDraft>(`/api/v1/recipe-drafts/${id(draftId)}/copy`, { method: 'POST' }),
	getMenu: (menuId) => call<ChatMenu>(`/api/v1/chat/menus/${id(menuId)}`),
	async getSentLatest() {
		try {
			return await call<SentLatest | null>('/api/v1/chat/sent/latest');
		} catch (error) {
			if (error instanceof ApiError && error.status === 404) return null;
			throw error;
		}
	}
};
