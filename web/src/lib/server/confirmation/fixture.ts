/**
 * In-memory stand-in for the confirmation endpoints (technical-plan.md §9.4), used
 * until #47 exists and by the Playwright tests. It mirrors the order in the design
 * screens 20 to 22 (Hassu Hauki Oy, 128,40 €) and behaves like the engine for the
 * page's purposes: acknowledgements carry over by flag key, every edit makes a new
 * quote version with a new hash, a stale hash is refused, and confirm can trigger
 * a requote.
 *
 * Tokens pick a scenario: `fx-<scenario>` or `fx-<scenario>-<anything>`, so each
 * test can use its own token. Scenarios: ready, fi, requote, confirmed, cancelled,
 * expired. Any other token is invalid.
 *
 * The data is invented, like the mock data in docs/design.
 */
import { randomBytes } from 'node:crypto';
import type {
	ConfirmationView,
	EditOp,
	Flag,
	Lang,
	Line,
	PageState,
	QuoteChange,
	Text
} from '#lib/confirmation/types.js';
import { ConfirmationError, type ConfirmationSource } from './source';

type BaseUnit = 'kg' | 'l';

interface Product {
	id: string;
	name: Text;
	/** Amount of the base unit in one sales unit. */
	size: number;
	base: BaseUnit;
	sales_unit: Text;
	price_cents: number;
	/** How it is packed, for the rounding flag: "cases of 12 x 1 l". */
	pack_text: Text;
	stock_confirmed: boolean;
	allergen_info: boolean;
	/** Another product that fits the asked amount exactly, offered on the rounding flag. */
	exact_fit?: string;
	note: Text;
}

const pcs: Text = { en: 'pcs', fi: 'kpl' };
const cases: Text = { en: 'cases', fi: 'ltk' };

const PRODUCTS: Record<string, Product> = {
	mince10: {
		id: 'mince10',
		name: { en: 'Beef mince 10 % 2,5 kg', fi: 'Naudan jauheliha 10 % 2,5 kg' },
		size: 2.5,
		base: 'kg',
		sales_unit: pcs,
		price_cents: 2095,
		pack_text: { en: '2,5 kg packs', fi: '2,5 kg pakkauksissa' },
		stock_confirmed: true,
		allergen_info: true,
		note: { en: 'In stock', fi: 'Varastossa' }
	},
	mince17: {
		id: 'mince17',
		name: { en: 'Finnish beef mince 17 % 1 kg', fi: 'Kotimainen naudan jauheliha 17 % 1 kg' },
		size: 1,
		base: 'kg',
		sales_unit: pcs,
		price_cents: 990,
		pack_text: { en: '1 kg packs', fi: '1 kg pakkauksissa' },
		stock_confirmed: true,
		allergen_info: true,
		note: { en: 'Finnish origin, in stock', fi: 'Suomalainen, varastossa' }
	},
	mince_org: {
		id: 'mince_org',
		name: { en: 'Organic beef mince 2 kg', fi: 'Luomu naudan jauheliha 2 kg' },
		size: 2,
		base: 'kg',
		sales_unit: pcs,
		price_cents: 2690,
		pack_text: { en: '2 kg packs', fi: '2 kg pakkauksissa' },
		stock_confirmed: false,
		allergen_info: true,
		note: { en: 'Stock not confirmed', fi: 'Saatavuutta ei vahvistettu' }
	},
	oat1: {
		id: 'oat1',
		name: { en: 'Oat drink 1 l', fi: 'Kaurajuoma 1 l' },
		size: 12,
		base: 'l',
		sales_unit: cases,
		price_cents: 2580,
		pack_text: { en: 'cases of 12', fi: '12 kpl laatikoissa' },
		stock_confirmed: true,
		allergen_info: true,
		exact_fit: 'oat25',
		note: { en: 'The one you usually order', fi: 'Se, jonka yleensä tilaat' }
	},
	oat25: {
		id: 'oat25',
		name: { en: 'Oat drink 2,5 l', fi: 'Kaurajuoma 2,5 l' },
		size: 2.5,
		base: 'l',
		sales_unit: pcs,
		price_cents: 575,
		pack_text: { en: '2,5 l cartons', fi: '2,5 l pakkauksissa' },
		stock_confirmed: true,
		allergen_info: true,
		note: { en: 'Other oat drink, in stock', fi: 'Toinen kaurajuoma, varastossa' }
	},
	oil5: {
		id: 'oil5',
		name: { en: 'Rapeseed oil 5 l', fi: 'Rypsiöljy 5 l' },
		size: 5,
		base: 'l',
		sales_unit: pcs,
		price_cents: 1745,
		pack_text: { en: '5 l cans', fi: '5 l kanistereissa' },
		stock_confirmed: false,
		allergen_info: false,
		note: { en: 'Stock not confirmed', fi: 'Saatavuutta ei vahvistettu' }
	},
	oil10: {
		id: 'oil10',
		name: { en: 'Rapeseed oil 10 l', fi: 'Rypsiöljy 10 l' },
		size: 10,
		base: 'l',
		sales_unit: pcs,
		price_cents: 3340,
		pack_text: { en: '10 l cans', fi: '10 l kanistereissa' },
		stock_confirmed: true,
		allergen_info: true,
		note: { en: 'In stock', fi: 'Varastossa' }
	}
};

interface FxRequest {
	id: string;
	asked: Text;
	amount: number;
	base: BaseUnit;
	alternatives: string[];
	why: Record<string, Text>;
	trace: Line['trace'];
	max_quantity: number | null;
}

const REQUESTS: FxRequest[] = [
	{
		id: 'r1',
		asked: { en: '5 kg ground beef by Monday', fi: '5 kg naudan jauhelihaa maanantaiksi' },
		amount: 5,
		base: 'kg',
		alternatives: ['mince10', 'mince17', 'mince_org'],
		why: {
			mince10: { en: 'Cheapest mince that arrives Monday', fi: 'Edullisin jauheliha, joka ehtii maanantaiksi' },
			mince17: { en: 'Finnish mince that arrives Monday', fi: 'Kotimainen jauheliha, joka ehtii maanantaiksi' },
			mince_org: { en: 'Organic mince, stock not confirmed', fi: 'Luomujauheliha, saatavuutta ei vahvistettu' }
		},
		trace: {
			found: 14,
			found_text: { en: 'mince products found', fi: 'jauhelihatuotetta löytyi' },
			removed: [
				{ count: 4, reason: { en: 'arrive after Monday', fi: 'ehtii vasta maanantain jälkeen' } },
				{ count: 3, reason: { en: 'out of stock', fi: 'loppu varastosta' } },
				{ count: 2, reason: { en: 'contain milk', fi: 'sisältää maitoa' } }
			],
			remaining: 5,
			decided_by: { en: 'safe and on time. We picked the cheapest.', fi: 'sopivaa ja ajoissa. Valitsimme edullisimman.' }
		},
		max_quantity: 40
	},
	{
		id: 'r2',
		asked: { en: 'my usual oat drink, 20 l', fi: 'tavallinen kaurajuoma, 20 l' },
		amount: 20,
		base: 'l',
		alternatives: ['oat1', 'oat25'],
		why: {
			oat1: { en: 'The one you usually order', fi: 'Se, jonka yleensä tilaat' },
			oat25: { en: 'Exactly 20 l in 2,5 l cartons', fi: 'Tasan 20 l 2,5 l pakkauksissa' }
		},
		trace: {
			found: 6,
			found_text: { en: 'oat drinks found', fi: 'kaurajuomaa löytyi' },
			removed: [{ count: 1, reason: { en: 'arrive after Monday', fi: 'ehtii vasta maanantain jälkeen' } }],
			remaining: 5,
			decided_by: { en: 'on time. You usually order this one.', fi: 'ajoissa. Tilaat yleensä tätä.' }
		},
		max_quantity: null
	},
	{
		id: 'r3',
		asked: { en: '10 l rapeseed oil', fi: '10 l rypsiöljyä' },
		amount: 10,
		base: 'l',
		alternatives: ['oil5', 'oil10'],
		why: {
			oil5: { en: 'Cheapest nut-free oil, Monday', fi: 'Edullisin pähkinätön öljy, maanantaiksi' },
			oil10: { en: 'Same oil in a 10 l can', fi: 'Sama öljy 10 l kanisterissa' }
		},
		trace: {
			found: 8,
			found_text: { en: 'oils found', fi: 'öljyä löytyi' },
			removed: [
				{ count: 3, reason: { en: 'may contain nuts', fi: 'voi sisältää pähkinää' } },
				{ count: 1, reason: { en: 'arrive after Monday', fi: 'ehtii vasta maanantain jälkeen' } }
			],
			remaining: 4,
			decided_by: { en: 'safe and on time. We picked the cheapest.', fi: 'sopivaa ja ajoissa. Valitsimme edullisimman.' }
		},
		max_quantity: null
	}
];

interface FxLine {
	id: string;
	request_id: string;
	product_id: string;
	quantity: number;
	/** The buyer set the amount by hand, so it is not a rounding. */
	manual: boolean;
}

interface FxFlag extends Flag {
	acknowledged_at: string | null;
}

interface FxState {
	token: string;
	scenario: string;
	state: PageState;
	lang: Lang;
	version: number;
	hash: string;
	lines: FxLine[];
	flags: FxFlag[];
	change: QuoteChange | null;
	requoted: boolean;
	order: ConfirmationView['order'];
}

const store = new Map<string, FxState>();
let nextOrderNumber = 1042;

const SCENARIOS = ['ready', 'fi', 'requote', 'confirmed', 'cancelled', 'expired'];

function scenarioOf(token: string): string | null {
	const match = /^fx-([a-z]+)(?:-[A-Za-z0-9_-]+)?$/.exec(token);
	return match && SCENARIOS.includes(match[1]) ? match[1] : null;
}

function newHash(): string {
	return randomBytes(16).toString('hex');
}

function num(value: number, lang: Lang): string {
	return new Intl.NumberFormat(lang === 'fi' ? 'fi-FI' : 'en-GB', {
		maximumFractionDigits: 2
	})
		.format(value)
		.replace('.', ',');
}

function euros(cents: number): string {
	return new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' }).format(cents / 100);
}

function both(fn: (lang: Lang) => string): Text {
	return { en: fn('en'), fi: fn('fi') };
}

function request(id: string): FxRequest {
	const found = REQUESTS.find((r) => r.id === id);
	if (!found) throw new Error(`Unknown request ${id}`);
	return found;
}

/** Sales units needed to cover the asked amount. */
function quantityFor(req: FxRequest, product: Product): number {
	return Math.ceil(req.amount / product.size - 1e-9);
}

function lineTotal(line: FxLine): number {
	return PRODUCTS[line.product_id].price_cents * line.quantity;
}

/** The flags the current lines call for, with acknowledgements carried over by key and text. */
function deriveFlags(s: FxState, extra: FxFlag[] = []): FxFlag[] {
	const wanted: Flag[] = [];
	for (const line of s.lines) {
		const product = PRODUCTS[line.product_id];
		const req = request(line.request_id);
		const amount = line.quantity * product.size;
		if (!product.stock_confirmed) {
			wanted.push({
				key: `stock:${product.id}`,
				kind: 'stock_not_confirmed',
				line_id: line.id,
				title: { en: 'Stock not confirmed', fi: 'Saatavuutta ei vahvistettu' },
				text: both((l) => (l === 'en' ? `${product.name.en}. We could not check the stock.` : `${product.name.fi}. Saatavuutta ei voitu tarkistaa.`)),
				acknowledged: false,
				is_new: false,
				choice: null
			});
		}
		if (amount > req.amount + 1e-9 && !line.manual) {
			const exact = product.exact_fit ? PRODUCTS[product.exact_fit] : null;
			wanted.push({
				key: `rounded:${line.id}`,
				kind: 'rounded_up',
				line_id: line.id,
				title: both((l) => `${l === 'en' ? 'Rounded up' : 'Pyöristetty ylöspäin'} ${num(req.amount, l)} ${req.base} → ${num(amount, l)} ${req.base}`),
				text: both((l) => (l === 'en' ? `${product.name.en} comes in ${product.pack_text.en}.` : `${product.name.fi} myydään ${product.pack_text.fi}.`)),
				acknowledged: false,
				is_new: false,
				choice: exact
					? {
							options: [
								{
									id: 'keep',
									alternative_id: null,
									title: both((l) => `${l === 'en' ? 'Keep' : 'Pidä'} ${num(amount, l)} ${req.base}`),
									text: both((l) => `${line.quantity} ${product.sales_unit[l]}, ${euros(lineTotal(line))}`),
									current: true
								},
								{
									id: 'exact',
									alternative_id: exact.id,
									title: both((l) => `${l === 'en' ? 'Exactly' : 'Tasan'} ${num(req.amount, l)} ${req.base}`),
									text: both((l) =>
										`${l === 'en' ? 'Other oat drink' : 'Toinen kaurajuoma'}, ${euros(exact.price_cents * quantityFor(req, exact))}`
									),
									current: false
								}
							]
						}
					: null
			});
		}
	}
	const noInfo = s.lines.filter((line) => !PRODUCTS[line.product_id].allergen_info);
	if (noInfo.length > 0) {
		const names = (l: Lang) => noInfo.map((line) => PRODUCTS[line.product_id].name[l]).join(', ');
		wanted.push({
			key: 'allergen_info',
			kind: 'no_allergen_info',
			line_id: noInfo.length === 1 ? noInfo[0].id : null,
			title: { en: 'No allergen info listed', fi: 'Allergiatietoja ei ole' },
			text: both((l) => (l === 'en' ? `${names(l)}. Check the pack if unsure.` : `${names(l)}. Tarkista pakkaus, jos olet epävarma.`)),
			acknowledged: false,
			is_new: false,
			choice: null
		});
	}

	const previous = new Map(s.flags.map((f) => [f.key, f]));
	const isFirst = s.version === 1 && s.flags.length === 0;
	return [...wanted, ...extra].map((flag) => {
		const before = previous.get(flag.key);
		const sameText = Boolean(
			before && before.text.en === flag.text.en && before.title.en === flag.title.en
		);
		const carried = Boolean(before && sameText && before.acknowledged);
		// "New" marks a flag the buyer hasn't seen in this form, until they acknowledge it.
		const isNew = isFirst ? false : sameText ? Boolean(before?.is_new) : true;
		return {
			...flag,
			acknowledged: carried,
			acknowledged_at: carried ? (before?.acknowledged_at ?? null) : null,
			is_new: isNew && !carried
		};
	});
}

function create(token: string, scenario: string): FxState {
	const s: FxState = {
		token,
		scenario,
		state: 'ready',
		lang: scenario === 'fi' ? 'fi' : 'en',
		version: 1,
		hash: newHash(),
		lines: [
			{ id: 'l1', request_id: 'r1', product_id: 'mince10', quantity: 2, manual: false },
			{ id: 'l2', request_id: 'r2', product_id: 'oat1', quantity: 2, manual: false },
			{ id: 'l3', request_id: 'r3', product_id: 'oil5', quantity: 2, manual: false }
		],
		flags: [],
		change: null,
		requoted: false,
		order: null
	};
	s.flags = deriveFlags(s);
	// As in screen 20: the stock flag was already checked.
	const stock = s.flags.find((f) => f.key === 'stock:oil5');
	if (stock) {
		stock.acknowledged = true;
		stock.acknowledged_at = new Date().toISOString();
	}
	if (scenario === 'confirmed') {
		for (const f of s.flags) {
			f.acknowledged = true;
			f.acknowledged_at ??= new Date().toISOString();
		}
		placeOrder(s);
	}
	if (scenario === 'cancelled') s.state = 'cancelled';
	if (scenario === 'expired') s.state = 'expired';
	return s;
}

function load(token: string): FxState | null {
	const existing = store.get(token);
	if (existing) return existing;
	const scenario = scenarioOf(token);
	if (!scenario) return null;
	const s = create(token, scenario);
	store.set(token, s);
	return s;
}

function total(s: FxState): number {
	return s.lines.reduce((sum, line) => sum + lineTotal(line), 0);
}

function placeOrder(s: FxState) {
	s.state = 'confirmed';
	s.order = {
		order_number: `D-${nextOrderNumber++}`,
		confirmed_at: new Date().toISOString(),
		acknowledged: s.flags.map((f) => ({
			flag_key: f.key,
			title: f.title,
			at: f.acknowledged_at ?? new Date().toISOString()
		}))
	};
	s.change = null;
}

function toView(s: FxState): ConfirmationView {
	const lineView = (line: FxLine): Line => {
		const product = PRODUCTS[line.product_id];
		const req = request(line.request_id);
		const amount = line.quantity * product.size;
		const perBase = product.price_cents / product.size;
		return {
			id: line.id,
			product: { id: product.id, name: product.name, image_url: null },
			quantity: line.quantity,
			sales_unit: product.sales_unit,
			quantity_text: both((l) => `${line.quantity} ${product.sales_unit[l]} = ${num(amount, l)} ${product.base}`),
			unit_price_text: both(
				(l) =>
					`${euros(perBase)} / ${product.base}, ${euros(product.price_cents)} / ${l === 'en' ? (product.sales_unit === cases ? 'case' : 'pcs') : product.sales_unit.fi} ${l === 'en' ? 'incl. VAT' : 'sis. alv'}`
			),
			line_total_cents: lineTotal(line),
			why: req.why[product.id],
			trace: req.trace,
			alternatives: req.alternatives.map((id) => {
				const alt = PRODUCTS[id];
				return {
					id,
					name: alt.name,
					note:
						id === product.id
							? both((l) => `${l === 'en' ? 'In your order' : 'Tilauksessasi'}, ${alt.note[l].toLowerCase()}`)
							: alt.note,
					unit_price_text: both(() => `${euros(alt.price_cents / alt.size)} / ${alt.base}`),
					in_order: id === product.id
				};
			}),
			min_quantity: 1,
			max_quantity: req.max_quantity,
			flag_keys: s.flags.filter((f) => f.line_id === line.id).map((f) => f.key)
		};
	};

	return {
		state: s.state,
		lang: s.lang,
		expires_at: s.state === 'expired' ? '2026-11-12T10:32:00+02:00' : null,
		company: { name: 'Hassu Hauki Oy' },
		session: { channel: 'phone', started_at: '2026-11-12T10:02:00+02:00' },
		exclusions: [
			{ key: 'milk', label: { en: 'Milk-free', fi: 'Maidoton' } },
			{ key: 'nuts', label: { en: 'Nut-free', fi: 'Pähkinätön' } }
		],
		quote: {
			id: `q-${s.token}-${s.version}`,
			version: s.version,
			hash: s.hash,
			total_cents: total(s),
			delivery: { date: '2026-11-16' }
		},
		requests: REQUESTS.filter((r) => s.lines.some((line) => line.request_id === r.id)).map((r) => ({
			id: r.id,
			asked: r.asked,
			lines: s.lines.filter((line) => line.request_id === r.id).map(lineView),
			not_ordered: []
		})),
		flags: s.flags.map(({ acknowledged_at: _at, ...flag }) => flag),
		change: s.change,
		order: s.order
	};
}

function requireActive(s: FxState | null, quoteHash: string): FxState {
	if (!s) throw new ConfirmationError(404);
	if (s.state === 'expired') throw new ConfirmationError(410);
	if (s.state !== 'ready' && s.state !== 'requote_needed') {
		throw new ConfirmationError(409, {
			en: 'This order is already closed.',
			fi: 'Tämä tilaus on jo käsitelty.'
		});
	}
	if (quoteHash !== s.hash) {
		throw new ConfirmationError(409, {
			en: 'The order changed in another window. This is the latest version.',
			fi: 'Tilaus muuttui toisessa ikkunassa. Tämä on uusin versio.'
		});
	}
	return s;
}

function newVersion(s: FxState, change: QuoteChange, extraFlags: FxFlag[] = []) {
	s.version += 1;
	s.hash = newHash();
	s.change = change;
	s.flags = deriveFlags(s, extraFlags);
}

export const fixtureSource: ConfirmationSource = {
	async get(token) {
		const s = load(token);
		return s ? toView(s) : null;
	},

	async acknowledge(token, quoteHash, flagKey) {
		const s = requireActive(load(token), quoteHash);
		const flag = s.flags.find((f) => f.key === flagKey);
		if (!flag) throw new ConfirmationError(422);
		if (!flag.acknowledged) {
			flag.acknowledged = true;
			flag.acknowledged_at = new Date().toISOString();
			flag.is_new = false;
		}
	},

	async edit(token, quoteHash, edit: EditOp) {
		const s = requireActive(load(token), quoteHash);
		const line = s.lines.find((l) => l.id === edit.line_id);
		if (!line) throw new ConfirmationError(422);
		const previous = total(s);
		const req = request(line.request_id);

		if (edit.op === 'set_quantity') {
			if (!Number.isInteger(edit.quantity) || edit.quantity < 1) {
				throw new ConfirmationError(422, { en: 'Choose at least 1.', fi: 'Valitse vähintään 1.' }, line.id);
			}
			if (req.max_quantity !== null && edit.quantity > req.max_quantity) {
				throw new ConfirmationError(
					422,
					{
						en: `Only ${req.max_quantity} available.`,
						fi: `Saatavilla vain ${req.max_quantity}.`
					},
					line.id
				);
			}
			line.quantity = edit.quantity;
			line.manual = true;
		} else if (edit.op === 'remove') {
			s.lines = s.lines.filter((l) => l.id !== line.id);
		} else {
			if (!req.alternatives.includes(edit.alternative_id)) throw new ConfirmationError(422);
			line.product_id = edit.alternative_id;
			line.quantity = quantityFor(req, PRODUCTS[edit.alternative_id]);
			line.manual = false;
		}
		newVersion(s, {
			reason: 'edit',
			previous_total_cents: previous,
			line_ids: edit.op === 'remove' ? [] : [line.id],
			text: null
		});
		if (s.state === 'requote_needed') s.state = 'ready';
	},

	async confirm(token, quoteHash) {
		const s = requireActive(load(token), quoteHash);
		if (s.lines.length === 0) {
			throw new ConfirmationError(422, { en: 'There is nothing left to order.', fi: 'Tilauksessa ei ole enää mitään.' });
		}
		if (s.flags.some((f) => !f.acknowledged)) {
			throw new ConfirmationError(422, {
				en: 'Check the flagged items first.',
				fi: 'Tarkista merkityt kohdat ensin.'
			});
		}
		if (s.scenario === 'requote' && !s.requoted) {
			// Availability got worse since the quote: the 5 l oil ran out.
			const oil = s.lines.find((l) => l.product_id === 'oil5');
			if (oil) {
				const previous = total(s);
				oil.product_id = 'oil10';
				oil.quantity = 1;
				s.requoted = true;
				const substitute: FxFlag = {
					key: `substitute:${oil.id}`,
					kind: 'substitute',
					line_id: oil.id,
					title: { en: 'Substitute: Rapeseed oil 10 l', fi: 'Korvaava tuote: Rypsiöljy 10 l' },
					text: {
						en: 'Rapeseed oil 5 l ran out. This is the same oil in a 10 l can.',
						fi: 'Rypsiöljy 5 l loppui. Tämä on sama öljy 10 l kanisterissa.'
					},
					acknowledged: false,
					acknowledged_at: null,
					is_new: true,
					choice: null
				};
				newVersion(
					s,
					{
						reason: 'requote',
						previous_total_cents: previous,
						line_ids: [oil.id],
						text: {
							en: 'Stock changed since the quote. Here is the updated order.',
							fi: 'Saatavuus muuttui tarjouksen jälkeen. Tässä päivitetty tilaus.'
						}
					},
					[substitute]
				);
				s.state = 'requote_needed';
				throw new ConfirmationError(409, s.change?.text ?? null);
			}
		}
		placeOrder(s);
	},

	async cancel(token, quoteHash) {
		const s = requireActive(load(token), quoteHash);
		s.state = 'cancelled';
		s.change = null;
	}
};
