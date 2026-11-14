/**
 * A scripted S.I.MO for the webshop chat tests (#57): answers `POST /api/v1/chat` with
 * the SSE events of docs/plans/57-a2ui-chat.md §3, and the paths the cards load
 * (quotes, recipe drafts, menus, the sent notice) with engine-shaped data, all with
 * `page.route`, so no FastAPI or Gemini is needed. Each turn is picked by what the
 * page sent: the buyer's words, a card action or an attached recipe draft.
 */
import type { Page, Route } from '@playwright/test';

export const CATALOG = 'https://simo.mankeli.co/a2ui/catalog/v1.json';

type Sse = [event: string, data: unknown][];

export interface ChatBody {
	conversation_id: string | null;
	message: string | null;
	action: { name: string; surfaceId: string; sourceComponentId: string; context: Record<string, unknown> } | null;
	attachment_draft_id: string | null;
}

const loc = (en: string, fi = en) => ({ en, fi });

function line(id: string, asked: string, quantity: number, name: string, cents: number, group: string | null = null) {
	return {
		line_id: id,
		group,
		asked: { text: asked, quantity, unit: 'l', package_word: null, needed_by: '2026-11-16' },
		product_id: `p-${id}`,
		name: loc(name),
		image_url: null,
		sales_unit: 'pcs',
		sales_unit_label: loc('carton', 'tölkki'),
		quantity_sales_units: quantity,
		quantity_in_asked_unit: quantity,
		unit_price_gross: Math.round(cents / quantity) / 100,
		price_per_base_unit: Math.round(cents / quantity) / 100,
		base_unit: 'l',
		line_total_cents: cents,
		delivery_date: '2026-11-16',
		stock_status: 'verified',
		origin: 'FI',
		reason_codes: ['cheapest_on_time'],
		reason_text: loc('Cheapest that arrives Monday', 'Halvin, joka ehtii maanantaiksi'),
		trace: { found: 14, removed: [], left: 5, ranking_rule: loc('Cheapest first', 'Halvin ensin'), ranked: [] },
		alternatives: []
	};
}

export function quote(id: string, lines: ReturnType<typeof line>[], extra: Record<string, unknown> = {}) {
	return {
		quote_id: id,
		version: 1,
		parent_quote_id: null,
		status: 'ready',
		decision: 'ready',
		lines,
		groups: [],
		flags: [],
		clarification: null,
		rejections: [],
		not_ordered: [],
		total_cents: lines.reduce((sum, l) => sum + l.line_total_cents, 0),
		delivery: { earliest: '2026-11-16', latest: '2026-11-16' },
		speak: loc('Your order is ready.', 'Tilauksesi on valmis.'),
		rules_ref: 'rules-v1',
		expires_at: null,
		quote_hash: `hash-${id}`,
		...extra
	};
}

export const MILK_QUOTE = quote('q-milk', [line('l1', 'lactose-free milk', 1000, 'Valio lactose-free milk 1 l', 129000)]);

export const MENU_QUOTE = quote(
	'q-menu',
	[
		line('m1', 'oat cream', 8, 'Valio Oddlygood oat cooking base 2 l', 4392, 'Chicken and vegetable curry'),
		line('m2', 'rapeseed oil', 4, 'Rapeseed oil 1 l', 1596, 'Salmon soup, milk-free')
	],
	{
		groups: [
			{ group: 'Chicken and vegetable curry', line_ids: ['m1'], subtotal_cents: 4392 },
			{ group: 'Salmon soup, milk-free', line_ids: ['m2'], subtotal_cents: 1596 }
		],
		not_ordered: [{ name: 'salt', quantity: null, unit: null, reason: loc('Not linked to a product', 'Ei linkitetty tuotteeseen') }]
	}
);

export const RECIPE_QUOTE = quote('q-recipe', [line('r1', 'maitoa', 6, 'Valio light milk 1 l', 774, 'Karjalanpiirakat')], {
	groups: [{ group: 'Karjalanpiirakat', line_ids: ['r1'], subtotal_cents: 774, source: 'photo', recipe_draft_id: 'd-1' }]
});

const DAYS = [
	['mon', 'Chicken and vegetable curry'],
	['tue', 'Meatballs, mashed potato with oat cream'],
	['wed', 'Pea soup and pancakes'],
	['thu', 'Pea soup and pancakes'],
	['fri', 'Minced meat lasagne, milk-free']
] as const;

export function menu(swapped = false) {
	return {
		menu_id: 'menu-1',
		days: DAYS.map(([day, name], i) => ({
			day,
			recipe_id: `rec-${i}`,
			name: swapped && day === 'wed' ? 'Salmon soup, milk-free' : name,
			image_url: null,
			portions: 80,
			linked_count: 3,
			ingredient_count: 6
		}))
	};
}

export function draft(status: 'draft' | 'confirmed' = 'draft') {
	const ingredients = [
		{ index: 0, text: 'ruisjauho', amount: 1.2, unit: 'kg', confidence: 'high', note: null, order: true, product_id: null },
		{ index: 1, text: 'maito', amount: 6, unit: 'l', confidence: 'high', note: null, order: true, product_id: null },
		{ index: 2, text: 'vesi', amount: 2, unit: 'l', confidence: 'low', note: null, order: false, product_id: null }
	];
	return {
		draft_id: 'd-1',
		status,
		source: 'notebook',
		is_guess: false,
		dish: 'Karjalanpiirakat',
		portions: 120,
		servings_on_source: 120,
		ingredients,
		scaled: ingredients,
		matched_recipe: null,
		ai_reading: null,
		speak: loc('I read Karelian pies for 120.', 'Luin karjalanpiirakat 120 annokselle.')
	};
}

/** A surface with one card as its root. */
export function card(surfaceId: string, component: Record<string, unknown>): Sse[number] {
	return [
		'a2ui',
		{
			envelopes: [
				{ version: 'v0.9', createSurface: { surfaceId, catalogId: CATALOG } },
				{ version: 'v0.9', updateComponents: { surfaceId, components: [{ id: 'root', ...component }] } }
			]
		}
	];
}

export function sse(events: Sse): string {
	return events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join('');
}

/** One scripted turn: S.I.MO's text, the tool it "ran", its cards and the quote id. */
export function turn(text: string, opts: { tool?: string; cards?: Sse; quoteId?: string | null } = {}): Sse {
	return [
		['start', { conversation_id: 'conv-1' }],
		...(opts.tool
			? ([
					['tool', { name: opts.tool, status: 'started' }],
					['tool', { name: opts.tool, status: 'done' }]
				] as Sse)
			: []),
		['text', { delta: text.slice(0, 6) }],
		['text', { delta: text.slice(6) }],
		...(opts.cards ?? []),
		['done', { quote_id: opts.quoteId ?? null }]
	];
}

export interface FakeChat {
	/** Every chat request body, in order. */
	bodies: ChatBody[];
	/** Every photo upload (the multipart body's size). */
	uploads: number[];
	/** The quote `GET /api/v1/quotes/current` answers with, or null for 404. */
	current: { value: Record<string, unknown> | null };
}

/**
 * Routes the chat and the cards' data. `script` returns the turn for a request; the
 * quotes, drafts and menus it mentions are served from `data`.
 */
export async function fakeChat(
	page: Page,
	script: (body: ChatBody, fake: FakeChat) => Sse,
	data: { quotes?: Record<string, unknown>[]; menu?: () => unknown; draft?: () => unknown } = {}
): Promise<FakeChat> {
	const fake: FakeChat = { bodies: [], uploads: [], current: { value: null } };
	const quotes = new Map((data.quotes ?? []).map((q) => [q.quote_id as string, q]));

	await page.route('**/api/v1/chat', async (route: Route) => {
		const body = route.request().postDataJSON() as ChatBody;
		fake.bodies.push(body);
		await route.fulfill({
			status: 200,
			headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-store' },
			body: sse(script(body, fake))
		});
	});
	await page.route('**/api/v1/quotes/*', async (route) => {
		const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop()!);
		if (id === 'current') {
			if (fake.current.value) await route.fulfill({ json: fake.current.value });
			else await route.fulfill({ status: 404, json: { detail: 'No quote yet' } });
			return;
		}
		const found = quotes.get(id);
		if (found) await route.fulfill({ json: found });
		else await route.fulfill({ status: 404, json: { detail: 'Not found' } });
	});
	await page.route('**/api/v1/chat/sent/latest', (route) =>
		route.fulfill({ json: { sent_to_masked: '+358 40 *** **12', delivery_status: 'off', inbox: true } })
	);
	await page.route('**/api/v1/chat/menus/*', (route) => route.fulfill({ json: data.menu?.() ?? menu() }));
	// Later routes win in Playwright, so the general draft route goes first.
	await page.route(/\/api\/v1\/recipe-drafts\/[^/]+$/, (route) =>
		route.request().method() === 'GET' ? route.fulfill({ json: data.draft?.() ?? draft() }) : route.fallback()
	);
	await page.route('**/api/v1/recipe-drafts/read', async (route) => {
		fake.uploads.push(route.request().postDataBuffer()?.length ?? 0);
		await route.fulfill({ json: data.draft?.() ?? draft() });
	});
	await page.route('**/api/v1/recipe-drafts/*/confirm', (route) => route.fulfill({ json: draft('confirmed') }));
	return fake;
}
