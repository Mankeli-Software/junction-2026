/**
 * A2UI v0.9 wire shapes, as Genkit's A2UI plugin (`@genkit-ai/a2ui`) sends them
 * (docs/specs/a2ui.md §2). Kept here so the page needs no Genkit or Lit package;
 * the shapes are the same, so envelopes from `a2uiEnvelopesFromParts` fit as they are.
 */

export const A2UI_MIME_TYPE = 'application/a2ui+json';

/** Our catalog's id, the `catalogId` on `createSurface` (catalog.json). */
export const SIMO_CATALOG_ID = 'https://simo.mankeli.co/a2ui/catalog/v1.json';

/** The components our renderer draws (Node.svelte); catalog.json lists the same names. */
export const SIMO_COMPONENTS = [
	'Column',
	'Row',
	'Text',
	'Notice',
	'Button',
	'RecipeDraftCard',
	'RecipeCard',
	'MenuWeek',
	'QuoteCard',
	'SentNotice'
] as const;

export type A2uiVersion = 'v0.9' | 'v0.9.1';

/** One entry of a surface's flat component list. Exactly one has `id: "root"`. */
export interface A2uiComponent {
	id: string;
	component: string;
	weight?: number;
	[prop: string]: unknown;
}

export interface CreateSurface {
	version: A2uiVersion;
	createSurface: { surfaceId: string; catalogId: string; theme?: unknown; sendDataModel?: boolean };
}

export interface UpdateComponents {
	version: A2uiVersion;
	updateComponents: { surfaceId: string; components: A2uiComponent[] };
}

export interface UpdateDataModel {
	version: A2uiVersion;
	/** `path` is a JSON Pointer; without it `value` replaces the whole model. */
	updateDataModel: { surfaceId: string; path?: string; value?: unknown };
}

export interface DeleteSurface {
	version: A2uiVersion;
	deleteSurface: { surfaceId: string };
}

export type A2uiServerEnvelope = CreateSurface | UpdateComponents | UpdateDataModel | DeleteSurface;

/** A user action from a rendered surface, sent back to the agent as the next turn. */
export interface A2uiClientAction {
	name: string;
	surfaceId: string;
	sourceComponentId: string;
	timestamp: string;
	context: Record<string, unknown>;
}

/** The Genkit data part that carries envelopes (both directions). */
export interface A2uiPart {
	data: { envelopes: (A2uiServerEnvelope | { action: A2uiClientAction })[] };
	metadata: { mimeType: typeof A2UI_MIME_TYPE };
}

/** Same as `actionToMessage` in `@genkit-ai/a2ui/client`: the name as text, the action as a data part. */
export function actionToMessage(action: A2uiClientAction): {
	role: 'user';
	content: (A2uiPart | { text: string })[];
} {
	return {
		role: 'user',
		content: [
			{ text: action.name },
			{ data: { envelopes: [{ action }] }, metadata: { mimeType: A2UI_MIME_TYPE } }
		]
	};
}
