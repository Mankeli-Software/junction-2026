/**
 * In-memory stand-in for the confirmation endpoints (technical-plan.md §9.4), used
 * by `pnpm dev` and the Playwright tests. Lines and flags have the shapes of the
 * contract in api/app/schemas/ (#26), and flag codes and texts follow
 * policy/messages.yaml. It mirrors the order in the design screens 20 to 22
 * (Hassu Hauki Oy, 128,40 €) and behaves like the engine for the page's purposes:
 * acknowledgements carry over by flag key and text, every edit makes a new quote
 * version with a new hash, a stale hash is refused, and confirm can trigger a requote.
 *
 * Tokens pick a scenario: `fx-<scenario>` or `fx-<scenario>-<anything>`, so each
 * test can use its own token. Scenarios: ready, fi, requote, confirmed, cancelled,
 * expired, recipe (the first two lines ordered for one of our recipes, a group with the
 * recipe's image). Any other token is invalid.
 *
 * The products and prices are invented, like the mock data in docs/design.
 */
import { randomBytes } from 'node:crypto';
import type {
	AskedLine,
	ConfirmationView,
	EditOp,
	Lang,
	PageState,
	QuoteChange,
	QuoteLine,
	Text,
	Trace,
	ViewFlag
} from '#lib/confirmation/types.js';
import { ConfirmationError, type ConfirmationSource } from './source';

type BaseUnit = 'kg' | 'l';

interface Product {
	id: string;
	name: Text;
	/** Amount of the base unit in one sales unit. */
	size: number;
	base: BaseUnit;
	sales_unit: string;
	sales_unit_label: Text;
	price_cents: number;
	stock_verified: boolean;
	allergen_info: boolean;
	/** Another product that fits the asked amount exactly, offered on the rounding flag. */
	exact_fit?: string;
}

const PCS: Text = { en: 'pcs', fi: 'kpl' };
const CASES: Text = { en: 'cases', fi: 'ltk' };

const PRODUCTS: Record<string, Product> = {
	mince10: {
		id: 'mince10',
		name: { en: 'Beef mince 10 % 2,5 kg', fi: 'Naudan jauheliha 10 % 2,5 kg' },
		size: 2.5,
		base: 'kg',
		sales_unit: 'ST',
		sales_unit_label: PCS,
		price_cents: 2095,
		stock_verified: true,
		allergen_info: true
	},
	mince17: {
		id: 'mince17',
		name: { en: 'Finnish beef mince 17 % 1 kg', fi: 'Kotimainen naudan jauheliha 17 % 1 kg' },
		size: 1,
		base: 'kg',
		sales_unit: 'ST',
		sales_unit_label: PCS,
		price_cents: 990,
		stock_verified: true,
		allergen_info: true
	},
	mince_org: {
		id: 'mince_org',
		name: { en: 'Organic beef mince 2 kg', fi: 'Luomu naudan jauheliha 2 kg' },
		size: 2,
		base: 'kg',
		sales_unit: 'ST',
		sales_unit_label: PCS,
		price_cents: 2690,
		stock_verified: false,
		allergen_info: true
	},
	oat1: {
		id: 'oat1',
		name: { en: 'Oat drink 1 l', fi: 'Kaurajuoma 1 l' },
		size: 12,
		base: 'l',
		sales_unit: 'LTK',
		sales_unit_label: CASES,
		price_cents: 2580,
		stock_verified: true,
		allergen_info: true,
		exact_fit: 'oat25'
	},
	oat25: {
		id: 'oat25',
		name: { en: 'Oat drink 2,5 l', fi: 'Kaurajuoma 2,5 l' },
		size: 2.5,
		base: 'l',
		sales_unit: 'ST',
		sales_unit_label: PCS,
		price_cents: 575,
		stock_verified: true,
		allergen_info: true
	},
	oil5: {
		id: 'oil5',
		name: { en: 'Rapeseed oil 5 l', fi: 'Rypsiöljy 5 l' },
		size: 5,
		base: 'l',
		sales_unit: 'ST',
		sales_unit_label: PCS,
		price_cents: 1745,
		stock_verified: false,
		allergen_info: false
	},
	oil10: {
		id: 'oil10',
		name: { en: 'Rapeseed oil 10 l', fi: 'Rypsiöljy 10 l' },
		size: 10,
		base: 'l',
		sales_unit: 'ST',
		sales_unit_label: PCS,
		price_cents: 3340,
		stock_verified: true,
		allergen_info: true
	}
};

interface FxRequest {
	asked: AskedLine;
	alternatives: string[];
	reason: Record<string, Text>;
	trace: Trace;
	/** Stock limit for the amount stepper; null when there is none. */
	max_quantity: number | null;
}

const NEEDED_BY = '2026-11-16';

const ARRIVE_LATE: Text = { en: 'arrive after Monday', fi: 'ehtii vasta maanantain jälkeen' };

const REQUESTS: Record<string, FxRequest> = {
	r1: {
		asked: { text: '5 kg ground beef by Monday', quantity: 5, unit: 'kg', package_word: null, needed_by: NEEDED_BY },
		alternatives: ['mince10', 'mince17', 'mince_org'],
		reason: {
			mince10: { en: 'Cheapest mince that arrives Monday', fi: 'Edullisin jauheliha, joka ehtii maanantaiksi' },
			mince17: { en: 'Finnish mince that arrives Monday', fi: 'Kotimainen jauheliha, joka ehtii maanantaiksi' },
			mince_org: { en: 'Organic mince, stock not confirmed', fi: 'Luomujauheliha, saatavuutta ei vahvistettu' }
		},
		trace: {
			found: 14,
			removed: [
				{ reason_code: 'DELIVERY_DATE_UNREACHABLE', count: 4, text: ARRIVE_LATE },
				{ reason_code: 'UNAVAILABLE', count: 3, text: { en: 'out of stock', fi: 'loppu varastosta' } },
				{ reason_code: 'ALLERGEN_CONFLICT', count: 2, text: { en: 'contain milk', fi: 'sisältää maitoa' } }
			],
			left: 5,
			ranking_rule: { en: 'lowest price per kilo', fi: 'halvin kilohinta' }
		},
		max_quantity: 40
	},
	r2: {
		asked: { text: 'my usual oat drink, 20 l', quantity: 20, unit: 'l', package_word: null, needed_by: NEEDED_BY },
		alternatives: ['oat1', 'oat25'],
		reason: {
			oat1: { en: 'The one you usually order', fi: 'Se, jonka yleensä tilaat' },
			oat25: { en: 'Exactly 20 l in 2,5 l cartons', fi: 'Tasan 20 l 2,5 l pakkauksissa' }
		},
		trace: {
			found: 6,
			removed: [{ reason_code: 'DELIVERY_DATE_UNREACHABLE', count: 1, text: ARRIVE_LATE }],
			left: 5,
			ranking_rule: { en: 'your usual product', fi: 'tavallinen tuotteesi' }
		},
		max_quantity: null
	},
	r3: {
		asked: { text: '10 l rapeseed oil', quantity: 10, unit: 'l', package_word: null, needed_by: NEEDED_BY },
		alternatives: ['oil5', 'oil10'],
		reason: {
			oil5: { en: 'Cheapest nut-free oil, Monday', fi: 'Edullisin pähkinätön öljy, maanantaiksi' },
			oil10: { en: 'Same oil in a 10 l can', fi: 'Sama öljy 10 l kanisterissa' }
		},
		trace: {
			found: 8,
			removed: [
				{ reason_code: 'ALLERGEN_CONFLICT', count: 3, text: { en: 'may contain nuts', fi: 'voi sisältää pähkinää' } },
				{ reason_code: 'DELIVERY_DATE_UNREACHABLE', count: 1, text: ARRIVE_LATE }
			],
			left: 4,
			ranking_rule: { en: 'lowest price per litre', fi: 'halvin litrahinta' }
		},
		max_quantity: null
	}
};

/** Flag codes that need a "Got it", from the `ack` setting in policy/messages.yaml. */
const ACK_CODES = new Set([
	'ALLERGEN_NO_LISTING',
	'AVAILABILITY_UNVERIFIED',
	'PACK_SIZE_FROM_NAME',
	'SUBSTITUTED_PACK_SIZE',
	'SUBSTITUTED_CURATED',
	'QUANTITY_UNUSUAL',
	'DUPLICATE_ORDER',
	'FIRST_TIME_PRODUCT'
]);

interface FxLine {
	line_id: string;
	request_id: string;
	product_id: string;
	quantity: number;
	/** The buyer set the amount by hand, so it is not a rounding. */
	manual: boolean;
}

interface FxState {
	token: string;
	scenario: string;
	state: PageState;
	lang: Lang;
	version: number;
	hash: string;
	lines: FxLine[];
	flags: ViewFlag[];
	change: QuoteChange | null;
	requoted: boolean;
	order: ConfirmationView['order'];
}

/** At most this many tokens are kept; the oldest is dropped first, so memory stays bounded. */
const MAX_TOKENS = 500;
const store = new Map<string, FxState>();
let nextOrderNumber = 1042;

const SCENARIOS = ['ready', 'fi', 'requote', 'confirmed', 'cancelled', 'expired', 'recipe'];

function scenarioOf(token: string): string | null {
	const match = /^fx-([a-z]+)(?:-[A-Za-z0-9_-]+)?$/.exec(token);
	return match && SCENARIOS.includes(match[1]) ? match[1] : null;
}

const newHash = () => randomBytes(16).toString('hex');
const now = () => new Date().toISOString();
const num = (value: number) => new Intl.NumberFormat('fi-FI', { maximumFractionDigits: 3 }).format(value);

function both(fn: (lang: Lang) => string): Text {
	return { en: fn('en'), fi: fn('fi') };
}

/** Sales units needed to cover the asked amount. */
function quantityFor(req: FxRequest, product: Product): number {
	return Math.ceil(req.asked.quantity / product.size - 1e-9);
}

const lineTotal = (line: FxLine) => PRODUCTS[line.product_id].price_cents * line.quantity;
const total = (s: FxState) => s.lines.reduce((sum, line) => sum + lineTotal(line), 0);

type NewFlag = Omit<ViewFlag, 'acknowledged_at' | 'is_new' | 'requires_ack'>;

/** The flags the current lines call for, with acknowledgements carried over by key and text. */
function deriveFlags(s: FxState, extra: NewFlag[] = []): ViewFlag[] {
	const wanted: NewFlag[] = [];
	for (const line of s.lines) {
		const product = PRODUCTS[line.product_id];
		const req = REQUESTS[line.request_id];
		const amount = line.quantity * product.size;
		if (!product.stock_verified) {
			wanted.push({
				flag_key: `AVAILABILITY_UNVERIFIED:${product.id}`,
				code: 'AVAILABILITY_UNVERIFIED',
				line_ids: [line.line_id],
				kind: 'acknowledge',
				text: {
					en: `Stock for ${product.name.en} could not be verified. It can be ordered, but delivery is not confirmed.`,
					fi: `Tuotteen ${product.name.fi} varastosaldoa ei voitu varmistaa. Tilaus on mahdollinen, mutta toimitusta ei ole vahvistettu.`
				},
				options: [],
				current_option_id: null
			});
		}
		if (amount > req.asked.quantity + 1e-9 && !line.manual) {
			const exact = product.exact_fit ? PRODUCTS[product.exact_fit] : null;
			const unit = (l: Lang) => product.sales_unit_label[l];
			wanted.push({
				flag_key: `ROUNDED_UP:${line.line_id}`,
				code: 'ROUNDED_UP',
				line_ids: [line.line_id],
				kind: exact ? 'choose' : 'acknowledge',
				text: {
					en: `I rounded ${product.name.en} up to ${line.quantity} ${unit('en')} to make whole sales units.`,
					fi: `Pyöristin tuotteen ${product.name.fi} määrän ylöspäin kokonaisiin myyntiyksiköihin: ${line.quantity} ${unit('fi')}.`
				},
				options: exact
					? [
							{
								option_id: 'keep',
								label: both((l) => `${l === 'en' ? 'Keep' : 'Pidä'} ${num(amount)} ${req.asked.unit}, ${line.quantity} ${unit(l)}`),
								line_total_cents: lineTotal(line)
							},
							{
								option_id: `exact:${exact.id}`,
								label: both((l) => `${l === 'en' ? 'Exactly' : 'Tasan'} ${num(req.asked.quantity)} ${req.asked.unit}, ${exact.name[l]}`),
								line_total_cents: exact.price_cents * quantityFor(req, exact)
							}
						]
					: [],
				current_option_id: exact ? 'keep' : null
			});
		}
	}
	const noInfo = s.lines.filter((line) => !PRODUCTS[line.product_id].allergen_info);
	if (noInfo.length > 0) {
		const names = (l: Lang) => noInfo.map((line) => PRODUCTS[line.product_id].name[l]).join(', ');
		wanted.push({
			flag_key: 'ALLERGEN_NO_LISTING',
			code: 'ALLERGEN_NO_LISTING',
			line_ids: noInfo.map((line) => line.line_id),
			kind: 'acknowledge',
			text: {
				en: `Note: these products have no allergen information: ${names('en')}. I can't confirm they are free from nuts.`,
				fi: `Huomio: seuraaville tuotteille ei ole ilmoitettu allergeenitietoja: ${names('fi')}. En voi vahvistaa, etteivät ne sisällä pähkinää.`
			},
			options: [],
			current_option_id: null
		});
	}

	const previous = new Map(s.flags.map((f) => [f.flag_key, f]));
	const isFirst = s.flags.length === 0 && s.version === 1;
	return [...wanted, ...extra].map((flag) => {
		const before = previous.get(flag.flag_key);
		const sameText = Boolean(before && before.text.en === flag.text.en);
		const carried = before && sameText ? before.acknowledged_at : null;
		// "New" marks a flag the buyer hasn't seen in this form, until they acknowledge it.
		const isNew = isFirst ? false : sameText ? Boolean(before?.is_new) : true;
		return {
			...flag,
			requires_ack: flag.kind === 'choose' || ACK_CODES.has(flag.code),
			acknowledged_at: carried,
			is_new: isNew && carried === null
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
			{ line_id: 'l1', request_id: 'r1', product_id: 'mince10', quantity: 2, manual: false },
			{ line_id: 'l2', request_id: 'r2', product_id: 'oat1', quantity: 2, manual: false },
			{ line_id: 'l3', request_id: 'r3', product_id: 'oil5', quantity: 2, manual: false }
		],
		flags: [],
		change: null,
		requoted: false,
		order: null
	};
	s.flags = deriveFlags(s);
	// As in screen 20: the stock flag was already checked.
	const stock = s.flags.find((f) => f.flag_key === 'AVAILABILITY_UNVERIFIED:oil5');
	if (stock) stock.acknowledged_at = now();
	if (scenario === 'confirmed') {
		for (const f of s.flags) f.acknowledged_at ??= now();
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
	if (store.size > MAX_TOKENS) store.delete(store.keys().next().value!);
	return s;
}

function placeOrder(s: FxState) {
	s.state = 'confirmed';
	s.order = {
		order_number: `D-${nextOrderNumber++}`,
		confirmed_at: now(),
		acknowledged: s.flags
			.filter((f) => f.acknowledged_at !== null)
			.map((f) => ({ flag_key: f.flag_key, code: f.code, at: f.acknowledged_at ?? now() }))
	};
	s.change = null;
}

function lineView(line: FxLine): QuoteLine {
	const product = PRODUCTS[line.product_id];
	const req = REQUESTS[line.request_id];
	return {
		line_id: line.line_id,
		group: null,
		asked: req.asked,
		product_id: product.id,
		name: product.name,
		image_url: null,
		sales_unit: product.sales_unit,
		sales_unit_label: product.sales_unit_label,
		quantity_sales_units: line.quantity,
		quantity_in_asked_unit: line.quantity * product.size,
		unit_price_gross: product.price_cents / 100,
		price_per_base_unit: Math.round(product.price_cents / product.size) / 100,
		base_unit: product.base,
		line_total_cents: lineTotal(line),
		delivery_date: NEEDED_BY,
		stock_status: product.stock_verified ? 'verified' : 'unverified',
		origin: null,
		reason_codes: [],
		reason_text: req.reason[product.id],
		trace: req.trace,
		alternatives: req.alternatives
			.filter((id) => id !== product.id)
			.map((id) => {
				const alt = PRODUCTS[id];
				const quantity = quantityFor(req, alt);
				return { product_id: id, label: alt.name, quantity_sales_units: quantity, line_total_cents: alt.price_cents * quantity };
			})
	};
}

/** The `recipe` scenario: the first two requests are for one of our recipes. */
const RECIPE_GROUP = {
	group: 'Lihapullat tomaattikastikkeessa',
	requests: ['r1', 'r2'],
	image_url: 'https://cdn-wp.valio.fi/valio-wp-network/sites/32/2024/11/37515-lihapullat-tomaattikastikkeessa-400x300.jpeg'
};

function groupOf(s: FxState, line: FxLine): string | null {
	return s.scenario === 'recipe' && RECIPE_GROUP.requests.includes(line.request_id) ? RECIPE_GROUP.group : null;
}

function groupsOf(s: FxState): ConfirmationView['groups'] {
	const lines = s.lines.filter((line) => groupOf(s, line) !== null);
	if (lines.length === 0) return [];
	return [
		{
			group: RECIPE_GROUP.group,
			line_ids: lines.map((l) => l.line_id),
			subtotal_cents: lines.reduce((sum, l) => sum + lineTotal(l), 0),
			image_url: RECIPE_GROUP.image_url
		}
	];
}

function toView(s: FxState): ConfirmationView {
	return {
		state: s.state,
		lang: s.lang,
		expires_at: s.state === 'expired' ? '2026-11-12T10:32:00+02:00' : null,
		company: { name: 'Hassu Hauki Oy' },
		session: { channel: 'phone', started_at: '2026-11-12T10:02:00+02:00' },
		exclusions: [
			{ key: 'milk_free', label: { en: 'Milk-free', fi: 'Maidoton' } },
			{ key: 'nut_free', label: { en: 'Nut-free', fi: 'Pähkinätön' } }
		],
		quote: {
			quote_id: `q-${s.token}-${s.version}`,
			version: s.version,
			quote_hash: s.hash,
			total_cents: total(s),
			delivery: s.lines.length > 0 ? { earliest: NEEDED_BY, latest: NEEDED_BY } : null
		},
		lines: s.lines.map((line) => ({ ...lineView(line), group: groupOf(s, line) })),
		groups: groupsOf(s),
		not_ordered: [],
		flags: s.flags,
		change: s.change,
		order: s.order
	};
}

function requireActive(s: FxState | null, quoteHash: string): FxState {
	if (!s) throw new ConfirmationError(404);
	if (s.state === 'expired') throw new ConfirmationError(410);
	if (s.state !== 'ready' && s.state !== 'requote_needed') {
		throw new ConfirmationError(409, { en: 'This order is already closed.', fi: 'Tämä tilaus on jo käsitelty.' });
	}
	if (quoteHash !== s.hash) {
		throw new ConfirmationError(409, {
			en: 'The order changed in another window. This is the latest version.',
			fi: 'Tilaus muuttui toisessa ikkunassa. Tämä on uusin versio.'
		});
	}
	return s;
}

function newVersion(s: FxState, change: QuoteChange, extraFlags: NewFlag[] = []) {
	s.version += 1;
	s.hash = newHash();
	s.change = change;
	s.flags = deriveFlags(s, extraFlags);
	if (s.state === 'requote_needed' && change.reason === 'edit') s.state = 'ready';
}

function switchProduct(s: FxState, line: FxLine, productId: string) {
	const req = REQUESTS[line.request_id];
	if (!req.alternatives.includes(productId)) throw new ConfirmationError(422);
	const previous = total(s);
	line.product_id = productId;
	line.quantity = quantityFor(req, PRODUCTS[productId]);
	line.manual = false;
	newVersion(s, { reason: 'edit', previous_total_cents: previous, line_ids: [line.line_id], text: null });
}

export const fixtureSource: ConfirmationSource = {
	async get(token) {
		const s = load(token);
		return s ? toView(s) : null;
	},

	async acknowledge(token, quoteHash, flagKey, optionId = null) {
		const s = requireActive(load(token), quoteHash);
		const flag = s.flags.find((f) => f.flag_key === flagKey);
		if (!flag) throw new ConfirmationError(422);
		if (flag.kind === 'choose') {
			const option = flag.options.find((o) => o.option_id === optionId);
			if (!option) throw new ConfirmationError(422);
			if (option.option_id.startsWith('exact:')) {
				const line = s.lines.find((l) => l.line_id === flag.line_ids[0]);
				if (!line) throw new ConfirmationError(422);
				// The exact fit replaces the rounded line, and its rounding flag goes away.
				switchProduct(s, line, option.option_id.slice('exact:'.length));
				return;
			}
		}
		flag.acknowledged_at ??= now();
		flag.is_new = false;
	},

	async edit(token, quoteHash, edit: EditOp) {
		const s = requireActive(load(token), quoteHash);
		const line = s.lines.find((l) => l.line_id === edit.line_id);
		if (!line) throw new ConfirmationError(422);
		const req = REQUESTS[line.request_id];

		if (edit.op === 'choose_alternative') {
			switchProduct(s, line, edit.alternative_id);
			return;
		}
		const previous = total(s);
		if (edit.op === 'set_quantity') {
			if (!Number.isInteger(edit.quantity) || edit.quantity < 1) {
				throw new ConfirmationError(422, { en: 'Choose at least 1.', fi: 'Valitse vähintään 1.' }, line.line_id);
			}
			if (req.max_quantity !== null && edit.quantity > req.max_quantity) {
				throw new ConfirmationError(
					422,
					{ en: `Only ${req.max_quantity} available.`, fi: `Saatavilla vain ${req.max_quantity}.` },
					line.line_id
				);
			}
			line.quantity = edit.quantity;
			line.manual = true;
		} else {
			s.lines = s.lines.filter((l) => l.line_id !== line.line_id);
		}
		newVersion(s, {
			reason: 'edit',
			previous_total_cents: previous,
			line_ids: edit.op === 'remove' ? [] : [line.line_id],
			text: null
		});
	},

	async confirm(token, quoteHash) {
		const s = requireActive(load(token), quoteHash);
		if (s.lines.length === 0) {
			throw new ConfirmationError(422, { en: 'There is nothing left to order.', fi: 'Tilauksessa ei ole enää mitään.' });
		}
		if (s.flags.some((f) => f.requires_ack && f.acknowledged_at === null)) {
			throw new ConfirmationError(422, { en: 'Check the flagged items first.', fi: 'Tarkista merkityt kohdat ensin.' });
		}
		const oil = s.lines.find((l) => l.product_id === 'oil5');
		if (s.scenario === 'requote' && !s.requoted && oil) {
			// Availability got worse since the quote: the 5 l oil ran out.
			const previous = total(s);
			oil.product_id = 'oil10';
			oil.quantity = 1;
			s.requoted = true;
			newVersion(
				s,
				{
					reason: 'requote',
					previous_total_cents: previous,
					line_ids: [oil.line_id],
					text: {
						en: 'Stock changed since the quote. Here is the updated order.',
						fi: 'Saatavuus muuttui tarjouksen jälkeen. Tässä päivitetty tilaus.'
					}
				},
				[
					{
						flag_key: `SUBSTITUTED_PACK_SIZE:${oil.line_id}`,
						code: 'SUBSTITUTED_PACK_SIZE',
						line_ids: [oil.line_id],
						kind: 'acknowledge',
						text: {
							en: 'Rapeseed oil 5 l was replaced by the same product in another pack size: Rapeseed oil 10 l.',
							fi: 'Tuote Rypsiöljy 5 l korvattiin samalla tuotteella toisessa pakkauskoossa: Rypsiöljy 10 l.'
						},
						options: [],
						current_option_id: null
					}
				]
			);
			s.state = 'requote_needed';
			throw new ConfirmationError(409, s.change?.text ?? null);
		}
		placeOrder(s);
	},

	async cancel(token, quoteHash) {
		const s = requireActive(load(token), quoteHash);
		s.state = 'cancelled';
		s.change = null;
	}
};
