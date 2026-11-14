/**
 * Engine data the cards load by id (docs/specs/a2ui.md §3), from the generated
 * OpenAPI types (`pnpm gen:api-types`). The two chat endpoints of
 * docs/plans/57-a2ui-chat.md §3 (`/chat/menus/{id}`, `/chat/sent/latest`) are typed
 * here by hand until they are in `openapi.json`: swap `ChatMenu` and `SentLatest`
 * for `components['schemas'][...]` then.
 */
import type { components } from '#lib/generated/openapi.js';

type Schemas = components['schemas'];

export type Lang = 'fi' | 'en';
export type Quote = Schemas['QuoteResponse'];
export type QuoteLine = Schemas['QuoteLine'];
export type Recipe = Schemas['Recipe'];
export type RecipeHit = Schemas['RecipeHit'];
export type RecipeDraft = Schemas['RecipeDraft'];
/** One ingredient as the API returns it (`DraftIngredient-Output`). */
export type DraftIngredient = Schemas['DraftIngredient-Output'];
/** One ingredient as the confirm body takes it (`DraftIngredient-Input`). */
export type DraftIngredientInput = Schemas['DraftIngredient-Input'];
/** The body of `POST /recipe-drafts/{id}/confirm` (the `confirm_recipe` REST twin). */
export type ConfirmDraft = Schemas['ConfirmRecipeBody'];
export type RecipeSource = RecipeDraft['source'];
export type DraftStatus = RecipeDraft['status'];

export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri';

/** One day of a menu `show_menu` stored (`GET /api/v1/chat/menus/{menuId}`). */
export interface MenuDay {
	day: Weekday;
	recipe_id: string;
	name: string;
	image_url: string | null;
	portions: number;
	/** Ingredients with a product link, when the server counts them. */
	linked_count?: number | null;
	ingredient_count?: number | null;
}

export interface ChatMenu {
	menu_id: string;
	days: MenuDay[];
}

/**
 * The latest confirmation request of this chat (`GET /api/v1/chat/sent/latest`),
 * shaped like `ConfirmationRequestResponse`. Never the link itself.
 */
export interface SentLatest {
	sent_to_masked: string | null;
	delivery_status: 'held' | 'sent' | 'failed' | 'off';
	inbox: boolean;
}

/**
 * Where the cards get their data: the REST API (`apiData`) or fixtures
 * (`fixtureData()`). The optional methods came later; a card without one shows its
 * error state or leaves the part out.
 */
export interface ChatData {
	getQuote(quoteId: string): Promise<Quote>;
	getRecipe(recipeId: string, portions: number): Promise<Recipe>;
	getDraft(draftId: string): Promise<RecipeDraft>;
	confirmDraft(draftId: string, edits: ConfirmDraft): Promise<RecipeDraft>;
	discardDraft(draftId: string): Promise<RecipeDraft>;
	/** "Edit as new draft": a new editable draft with the same content. */
	copyDraft?(draftId: string): Promise<RecipeDraft>;
	getMenu?(menuId: string): Promise<ChatMenu>;
	/** Null when nothing was sent in this chat yet. */
	getSentLatest?(): Promise<SentLatest | null>;
}
