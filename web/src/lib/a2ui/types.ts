/**
 * Engine data the cards load by id (docs/specs/a2ui.md §3), all from the generated
 * OpenAPI types (`pnpm gen:api-types`).
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

/** A menu `show_menu` stored (`GET /api/v1/chat/menus/{menuId}`). */
export type ChatMenu = Schemas['ChatMenu'];
export type MenuDay = Schemas['ChatMenuDay'];
export type Weekday = MenuDay['day'];
/**
 * The latest confirmation request of this chat (`GET /api/v1/chat/sent/latest`, 404
 * when nothing was sent). Never the link itself.
 */
export type SentLatest = Schemas['ChatSentLatest'];

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
