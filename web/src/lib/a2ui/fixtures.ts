/**
 * A fixture `ChatData` for tests, the chat panel's Playwright specs and a preview,
 * shaped exactly like the generated API types. Each `fixtureData()` keeps its own
 * copy, so confirming or discarding a draft in one test never leaks into another.
 *
 * Ids: drafts `rd_notebook` (two low-confidence rows) and `rd_dish` (a dish photo with
 * a matched recipe); quotes `q_question` (groups, a flag, "not ordered", one
 * clarification), `q_ready` (ready to send) and `q_rejected`; recipe `r_1188`;
 * menu `m_week`. Any other id answers 404.
 */
import { ApiError } from './api';
import type { A2uiServerEnvelope } from './protocol';
import { SIMO_CATALOG_ID } from './protocol';
import type {
	ChatData,
	ChatMenu,
	ConfirmDraft,
	DraftIngredient,
	Quote,
	QuoteLine,
	Recipe,
	RecipeDraft,
	RecipeHit,
	SentLatest
} from './types';

// --- Recipe drafts --------------------------------------------------------------------

function ingredient(index: number, text: string, amount: number | null, unit: string | null, extra: Partial<DraftIngredient> = {}): DraftIngredient {
	return { index, text, amount, unit, confidence: 'high', note: null, order: true, product_id: null, ...extra };
}

function scale(list: DraftIngredient[], portions: number, servings: number | null): DraftIngredient[] {
	return list.map((i) => ({
		...i,
		amount: i.amount == null || !servings ? (i.amount ?? null) : Math.round(((i.amount * portions) / servings) * 100) / 100
	}));
}

const notebookIngredients: DraftIngredient[] = [
	ingredient(0, 'vettä', 2, 'dl', { order: false }),
	ingredient(1, 'ruisjauhoja', 3, 'dl'),
	ingredient(2, 'vehnäjauhoja', 1, 'dl'),
	ingredient(3, 'suolaa', 1, 'tl'),
	ingredient(4, 'puuroriisiä', 2.5, 'dl'),
	ingredient(5, 'maitoa', 1, 'l', { confidence: 'low', note: '1 l or 7 l?' }),
	ingredient(6, 'voita', 100, 'g', { confidence: 'low', note: 'Hard to read' }),
	ingredient(7, 'kananmunia', 4, 'kpl')
];

export const fixtureNotebookDraft: RecipeDraft = {
	draft_id: 'rd_notebook',
	status: 'draft',
	source: 'notebook',
	is_guess: false,
	dish: 'Karjalanpiirakat',
	portions: 120,
	servings_on_source: 20,
	ingredients: notebookIngredients,
	scaled: scale(notebookIngredients, 120, 20),
	matched_recipe: null,
	ai_reading: null,
	speak: {
		fi: 'Luin reseptistä Karjalanpiirakat 8 ainesosaa.',
		en: 'I read 8 ingredients for Karjalanpiirakat.'
	}
};

export const fixtureRecipeHit: RecipeHit = {
	recipe_id: 'r_1188',
	name: 'Kermainen lohikeitto',
	image_url: null,
	default_portions: 10,
	diet_tags: ['Gluteeniton', 'Laktoositon']
};

const recipeIngredients: DraftIngredient[] = [
	ingredient(0, 'Laktoositon ruokakerma', 0.5, 'l', { product_id: '6408430000123' }),
	ingredient(1, 'Voi', 50, 'g', { product_id: '6408430000456' }),
	ingredient(2, 'Laktoositon maito', 0.75, 'l', { product_id: '6408430000789' }),
	ingredient(3, 'Lohi', 1, 'kg'),
	ingredient(4, 'Peruna', 1.25, 'kg'),
	ingredient(5, 'Sipuli', 0.2, 'kg'),
	ingredient(6, 'Kalaliemi', 1.5, 'l'),
	ingredient(7, 'Tilli', 20, 'g')
];

const dishReading: DraftIngredient[] = [
	ingredient(0, 'lohta', null, null),
	ingredient(1, 'perunaa', null, null),
	ingredient(2, 'kermaa', null, null, { confidence: 'low', note: 'Could be milk' }),
	ingredient(3, 'tilliä', null, null)
];

export const fixtureDishDraft: RecipeDraft = {
	draft_id: 'rd_dish',
	status: 'draft',
	source: 'dish_photo',
	is_guess: true,
	dish: 'Lohikeitto',
	portions: 80,
	servings_on_source: 10,
	ingredients: recipeIngredients,
	scaled: scale(recipeIngredients, 80, 10),
	matched_recipe: fixtureRecipeHit,
	ai_reading: dishReading,
	speak: {
		fi: 'Tämä on arvaus kuvasta: Lohikeitto. Löysin reseptin Kermainen lohikeitto ja aloitin siitä.',
		en: 'This is a guess from the picture: Lohikeitto. I found our recipe Kermainen lohikeitto and started from it.'
	}
};

// --- Recipes --------------------------------------------------------------------------

export const fixtureRecipe: Recipe = {
	recipe_id: 'r_1188',
	name: 'Kermainen lohikeitto',
	image_url: null,
	portions: 10,
	ingredients: recipeIngredients.map((i) => ({
		index: i.index,
		name: i.text,
		quantity: i.amount ?? null,
		unit: i.unit ?? null,
		product_id: i.product_id ?? null
	}))
};

// --- Quotes ---------------------------------------------------------------------------

function line(over: Partial<QuoteLine> & Pick<QuoteLine, 'line_id' | 'name' | 'line_total_cents'>): QuoteLine {
	return {
		group: null,
		asked: { text: null, quantity: 1, unit: 'sales_unit', package_word: null, needed_by: '2026-11-17' },
		product_id: '6408430000000',
		image_url: null,
		sales_unit: 'PCE',
		sales_unit_label: { fi: 'kpl', en: 'pcs' },
		quantity_sales_units: 1,
		quantity_in_asked_unit: 1,
		unit_price_gross: over.line_total_cents / 100,
		price_per_base_unit: null,
		base_unit: null,
		delivery_date: '2026-11-17',
		stock_status: 'verified',
		origin: 'FI',
		reason_codes: ['CHEAPEST_ON_TIME'],
		reason_text: { fi: 'Halvin, joka ehtii tiistaiksi', en: 'Cheapest that arrives Tuesday' },
		trace: {
			found: 14,
			removed: [
				{ reason_code: 'LATE', count: 4, text: { fi: 'Ei ehdi tiistaiksi', en: 'Arrive after Tuesday' }, products: [] }
			],
			left: 10,
			ranking_rule: { fi: 'Halvin litrahinta', en: 'Lowest price per litre' },
			ranked: []
		},
		alternatives: [],
		...over
	};
}

const milkLine = line({
	line_id: 'p5',
	group: 'Karjalanpiirakat',
	asked: { text: 'maitoa', quantity: 6, unit: 'l', package_word: null, needed_by: '2026-11-17' },
	product_id: '6408430000111',
	name: { fi: 'Valio kevytmaito 1 l', en: 'Valio light milk 1 l' },
	sales_unit_label: { fi: 'tölkkiä', en: 'cartons' },
	quantity_sales_units: 6,
	quantity_in_asked_unit: 6,
	unit_price_gross: 1.29,
	price_per_base_unit: 1.29,
	base_unit: 'l',
	line_total_cents: 774,
	reason_text: { fi: 'Halvin maito, joka ehtii tiistaiksi', en: 'Cheapest milk that arrives Tuesday' }
});

const butterLine = line({
	line_id: 'p6',
	group: 'Karjalanpiirakat',
	asked: { text: 'voita', quantity: 0.6, unit: 'kg', package_word: null, needed_by: '2026-11-17' },
	product_id: '6408430000222',
	name: { fi: 'Valio voi 500 g', en: 'Valio butter 500 g' },
	sales_unit_label: { fi: 'pakettia', en: 'packs' },
	quantity_sales_units: 2,
	quantity_in_asked_unit: 1,
	unit_price_gross: 5.49,
	line_total_cents: 1098,
	reason_codes: ['ROUNDED_UP'],
	reason_text: { fi: 'Myydään 500 g paketeissa, joten 400 g ylimääräistä', en: 'Sold in 500 g packs, so 400 g extra' }
});

const lactoseFreeLine = line({
	line_id: 'l1',
	asked: { text: '60 l lactose-free milk', quantity: 60, unit: 'l', package_word: null, needed_by: '2026-11-17' },
	product_id: '6408430000333',
	name: { fi: 'Valio laktoositon kevytmaito 1,5 l', en: 'Valio lactose-free light milk 1.5 l' },
	sales_unit_label: { fi: 'kpl', en: 'pcs' },
	quantity_sales_units: 40,
	quantity_in_asked_unit: 60,
	unit_price_gross: 3.12,
	line_total_cents: 12480,
	reason_text: { fi: 'Varastossa tiistaiksi', en: 'In stock for Tuesday' }
});

const quoteBase = {
	speak: { fi: 'Tilauksesi tähän asti.', en: 'Your order so far.' },
	rules_ref: 'rules-2026-11-14',
	version: 1,
	parent_quote_id: null,
	expires_at: '2026-11-15T10:00:00Z',
	quote_hash: null
} satisfies Partial<Quote>;

export const fixtureQuestionQuote: Quote = {
	...quoteBase,
	quote_id: 'q_question',
	decision: 'needs_clarification',
	status: 'needs_clarification',
	lines: [milkLine, butterLine, lactoseFreeLine],
	groups: [
		{
			group: 'Karjalanpiirakat',
			line_ids: ['p5', 'p6'],
			subtotal_cents: 1872,
			source: 'photo',
			recipe_draft_id: 'rd_notebook'
		}
	],
	flags: [
		{
			flag_key: 'ROUNDED_UP:p6',
			code: 'ROUNDED_UP',
			line_ids: ['p6'],
			kind: 'acknowledge',
			text: {
				fi: 'Voi pyöristetään 1 kg:aan, koska sitä myydään 500 g paketeissa.',
				en: 'Butter is rounded up to 1 kg because it is sold in 500 g packs.'
			},
			options: []
		}
	],
	clarification: {
		line_id: 'p5',
		question: {
			fi: 'Tarvitset 6 l maitoa. Kuusi 1 l tölkkiä vai yksi 10 l pussi?',
			en: 'You need 6 l of milk. Six 1 l cartons, or one 10 l bag?'
		},
		options: [
			{ product_id: '6408430000111', label: { fi: 'Kuusi 1 l tölkkiä', en: 'Six 1 l cartons' }, quantity_sales_units: 6, line_total_cents: 774 },
			{
				product_id: '6408430000444',
				label: { fi: 'Yksi 10 l pussi, 4 l ylimääräistä', en: 'One 10 l bag, 4 l extra' },
				quantity_sales_units: 1,
				line_total_cents: 1290
			}
		]
	},
	rejections: [],
	not_ordered: ['ruisjauhoja', 'vehnäjauhoja', 'puuroriisiä', 'suolaa', 'kananmunia'].map((name) => ({
		name,
		quantity: null,
		unit: null,
		reason: {
			fi: 'Hanki nämä muualta. Tilaamme vain reseptiin linkitetyt Valion tuotteet.',
			en: 'Get these elsewhere. We only order Valio products linked to the recipe.'
		}
	})),
	total_cents: 14352,
	delivery: { earliest: '2026-11-17', latest: '2026-11-17' }
};

export const fixtureReadyQuote: Quote = {
	...fixtureQuestionQuote,
	quote_id: 'q_ready',
	version: 2,
	parent_quote_id: 'q_question',
	decision: 'ready',
	status: 'ready',
	clarification: null
};

export const fixtureRejectedQuote: Quote = {
	...quoteBase,
	quote_id: 'q_rejected',
	decision: 'rejected',
	status: 'rejected',
	lines: [],
	groups: [],
	flags: [],
	clarification: null,
	rejections: [
		{
			line_id: 'l1',
			reason_code: 'NOT_BY_DATE',
			text: { fi: 'Kerma ei ehdi maanantaiksi.', en: 'Cream can’t arrive by Monday.' },
			next_step: { fi: 'Seuraava toimitus keskiviikkona 18.11.', en: 'Next delivery Wednesday 18 Nov.' }
		}
	],
	not_ordered: [],
	total_cents: 0,
	delivery: null
};

// --- Menu and sent --------------------------------------------------------------------

export const fixtureMenu: ChatMenu = {
	menu_id: 'm_week',
	days: [
		{ day: 'mon', recipe_id: 'r_2001', name: 'Broileri-kookoscurry', image_url: null, portions: 80, linked_count: 2, ingredient_count: 9 },
		{ day: 'tue', recipe_id: 'r_2002', name: 'Lihapullat ja perunamuusi', image_url: null, portions: 80, linked_count: 3, ingredient_count: 10 },
		{ day: 'wed', recipe_id: 'r_1188', name: 'Kermainen lohikeitto', image_url: null, portions: 80, linked_count: 3, ingredient_count: 8 },
		{ day: 'thu', recipe_id: 'r_2004', name: 'Hernekeitto', image_url: null, portions: 80, linked_count: 1, ingredient_count: 6 },
		{ day: 'fri', recipe_id: 'r_2005', name: 'Lasagne', image_url: null, portions: 80, linked_count: 4, ingredient_count: 11 }
	]
};

export const fixtureSent: SentLatest = { sent_to_masked: '+358 40 *** **12', delivery_status: 'sent', inbox: true };

// --- The ChatData ---------------------------------------------------------------------

export interface FixtureOptions {
	/** Milliseconds every call waits, to see the loading state. Default 0. */
	delay?: number;
	/** What `getSentLatest` answers. Default: a real SMS went (`fixtureSent`). */
	sent?: SentLatest | null;
	/** Ids whose calls fail with a 500, to see the error state. */
	failing?: string[];
}

export interface FixtureChatData extends ChatData {
	copyDraft(draftId: string): Promise<RecipeDraft>;
	getMenu(menuId: string): Promise<ChatMenu>;
	getSentLatest(): Promise<SentLatest | null>;
	/** Every call made, for assertions: `confirmDraft rd_notebook`. */
	calls: { method: string; id: string; body?: unknown }[];
}

export function fixtureData(options: FixtureOptions = {}): FixtureChatData {
	const drafts = new Map<string, RecipeDraft>(
		[fixtureNotebookDraft, fixtureDishDraft].map((d) => [d.draft_id, structuredClone(d)])
	);
	const quotes = new Map<string, Quote>(
		[fixtureQuestionQuote, fixtureReadyQuote, fixtureRejectedQuote].map((q) => [q.quote_id, structuredClone(q)])
	);
	const calls: FixtureChatData['calls'] = [];
	let copies = 0;

	async function answer<T>(method: string, id: string, make: () => T, body?: unknown): Promise<T> {
		calls.push({ method, id, ...(body === undefined ? {} : { body }) });
		if (options.delay) await new Promise((resolve) => setTimeout(resolve, options.delay));
		if (options.failing?.includes(id)) throw new ApiError(`${method} ${id}: 500`, 500);
		return structuredClone(make());
	}

	function draft(id: string): RecipeDraft {
		const value = drafts.get(id);
		if (!value) throw new ApiError(`draft ${id}: 404`, 404);
		return value;
	}

	return {
		calls,
		getQuote: (id) =>
			answer('getQuote', id, () => {
				const q = quotes.get(id);
				if (!q) throw new ApiError(`quote ${id}: 404`, 404);
				return q;
			}),
		getRecipe: (id, portions) =>
			answer('getRecipe', id, () => {
				if (id !== fixtureRecipe.recipe_id) throw new ApiError(`recipe ${id}: 404`, 404);
				const factor = portions / fixtureRecipe.portions;
				return {
					...fixtureRecipe,
					portions,
					ingredients: fixtureRecipe.ingredients.map((i) => ({
						...i,
						quantity: i.quantity == null ? null : Math.round(i.quantity * factor * 100) / 100
					}))
				};
			}),
		getDraft: (id) => answer('getDraft', id, () => draft(id)),
		confirmDraft: (id, body: ConfirmDraft) =>
			answer(
				'confirmDraft',
				id,
				() => {
					const d = draft(id);
					if (d.status === 'discarded') throw new ApiError('discarded: 409', 409);
					if (d.status === 'confirmed') return d;
					let list = d.ingredients;
					let servings = d.servings_on_source;
					let matched = d.matched_recipe;
					if (body.use_ai_reading && d.ai_reading) {
						list = d.ai_reading;
						servings = null;
						matched = null;
					}
					if (body.ingredients) {
						list = body.ingredients.map((i) => ({
							index: i.index,
							text: i.text,
							amount: typeof i.amount === 'string' ? Number(i.amount) : (i.amount ?? null),
							unit: i.unit ?? null,
							confidence: i.confidence,
							note: i.note ?? null,
							order: i.order,
							product_id: i.product_id ?? null
						}));
					}
					const portions = body.portions ?? d.portions;
					const next: RecipeDraft = {
						...d,
						status: 'confirmed',
						portions,
						servings_on_source: servings,
						ingredients: list,
						scaled: scale(list, portions, servings),
						matched_recipe: matched
					};
					drafts.set(id, next);
					return next;
				},
				body
			),
		discardDraft: (id) =>
			answer('discardDraft', id, () => {
				const d = draft(id);
				if (d.status === 'confirmed') throw new ApiError('confirmed: 409', 409);
				const next: RecipeDraft = { ...d, status: 'discarded' };
				drafts.set(id, next);
				return next;
			}),
		copyDraft: (id) =>
			answer('copyDraft', id, () => {
				const d = draft(id);
				const next: RecipeDraft = { ...structuredClone(d), draft_id: `${id}_copy${++copies}`, status: 'draft' };
				drafts.set(next.draft_id, next);
				return next;
			}),
		getMenu: (id) =>
			answer('getMenu', id, () => {
				if (id !== fixtureMenu.menu_id) throw new ApiError(`menu ${id}: 404`, 404);
				return fixtureMenu;
			}),
		getSentLatest: () => answer('getSentLatest', 'latest', () => (options.sent === undefined ? fixtureSent : options.sent))
	};
}

// --- Envelopes ------------------------------------------------------------------------

/**
 * The envelopes of one surface holding one card, as the agent would stream them:
 * `cardEnvelopes('s1', 'QuoteCard', { quoteId: 'q_ready' })`.
 */
export function cardEnvelopes(surfaceId: string, component: string, props: Record<string, unknown> = {}): A2uiServerEnvelope[] {
	return [
		{ version: 'v0.9', createSurface: { surfaceId, catalogId: SIMO_CATALOG_ID } },
		{
			version: 'v0.9',
			updateComponents: {
				surfaceId,
				components: [
					{ id: 'root', component: 'Column', children: ['card'] },
					{ id: 'card', component, ...props }
				]
			}
		}
	];
}
