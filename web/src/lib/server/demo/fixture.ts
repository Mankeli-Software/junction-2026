/**
 * In-memory stand-in for the demo accounts and the simulated phone inbox
 * (technical-plan.md §9.2), used with DEMO_SOURCE=fixture until #44 and #46 exist,
 * and by the Playwright tests.
 *
 * - Same number, same company: a number gets one generated Oy name and keeps it.
 * - Each browser is its own user (a session cookie), and the inbox belongs to the
 *   user, so typing someone else's number never shows their links.
 *
 * The state lives on `globalThis`, because two copies of this module run in one
 * process: SvelteKit's own (for the HTTP routes) and the mock relay's (for
 * /voice/ws, loaded by vite.config.ts or mock/serve.ts). Both share one store.
 *
 * Imports use `.ts` so Node can load this file directly (mock/serve.ts).
 *
 * Test numbers (national part):
 * - ends in 0429: the number has reached the demo limit (429);
 * - ends in 7001: the SMS goes out (`delivery_status: sent`);
 * - ends in 7002: the SMS fails (`delivery_status: failed`);
 * - ends in 0005: a vegan catering company, which starts with Vegan when nothing is
 *   chosen (#81); any other number is a lunch restaurant.
 */
import { randomBytes, randomUUID } from 'node:crypto';
import { maskPhone } from '../../demo/phone.ts';
import type {
	DemoAccount,
	DemoAccountRequest,
	Exclusion,
	InboxMessage,
	KitchenType,
	Lang,
	Me,
	DeliveryStatus,
	UsualItem
} from '../../demo/types.ts';

export const SESSION_COOKIE = 'simo_session';

interface Company {
	id: string;
	phone: string;
	name: string;
	kitchenType: KitchenType;
	exclusions: Exclusion[];
	lang: Lang;
}

interface User {
	/** The session token: the `simo_session` cookie. */
	id: string;
	userId: string;
	phone: string;
	inbox: InboxMessage[];
}

type Listener = (message: InboxMessage) => void;

interface Store {
	companies: Map<string, Company>;
	users: Map<string, User>;
	listeners: Map<string, Set<Listener>>;
	nextMessage: number;
}

const KEY = Symbol.for('simo.demo.fixture');

function store(): Store {
	const holder = globalThis as unknown as Record<symbol, Store | undefined>;
	holder[KEY] ??= { companies: new Map(), users: new Map(), listeners: new Map(), nextMessage: 1 };
	return holder[KEY];
}

export class FixtureLimitError extends Error {
	constructor() {
		super('This number has reached the demo limit');
	}
}

/**
 * `POST /api/v1/demo/accounts`. Reuses the browser's user when it typed the same
 * number before; otherwise makes a new user (and so a new, empty inbox).
 */
export function createAccount(
	sessionId: string | null,
	request: DemoAccountRequest
): { sessionId: string; account: DemoAccount } {
	const { companies, users } = store();
	if (request.phone_e164.endsWith('0429')) throw new FixtureLimitError();

	let company = companies.get(request.phone_e164);
	const newCompany = !company;
	if (!company) {
		company = {
			id: randomUUID(),
			phone: request.phone_e164,
			name: uniqueName(request.phone_e164),
			kitchenType: request.phone_e164.endsWith('0005') ? 'vegan_catering' : 'lunch_restaurant',
			exclusions: [],
			lang: request.lang
		};
		companies.set(company.phone, company);
	}
	// A change to the kitchen applies from the next call (spec §2.2).
	// A new company with nothing chosen starts from its type's defaults (#81).
	const defaults: Exclusion[] = company.kitchenType === 'vegan_catering' ? ['vegan'] : [];
	company.exclusions = newCompany && request.exclusions.length === 0 ? defaults : [...request.exclusions];
	company.lang = request.lang;

	let user = sessionId ? users.get(sessionId) : undefined;
	const newUser = !user || user.phone !== request.phone_e164;
	if (!user || newUser) {
		user = { id: randomBytes(18).toString('base64url'), userId: randomUUID(), phone: request.phone_e164, inbox: [] };
		users.set(user.id, user);
	}
	return { sessionId: user.id, account: accountView(company, user, newCompany, newUser) };
}

/** What the mock relay needs about the caller. */
export function accountFor(
	sessionId: string | null | undefined
): { company_name: string; lang: Lang; phone: string } | null {
	const company = companyFor(sessionId);
	return company ? { company_name: company.name, lang: company.lang, phone: company.phone } : null;
}

/** `GET /api/v1/me`. */
export function me(sessionId: string | null | undefined): Me | null {
	const user = sessionId ? store().users.get(sessionId) : undefined;
	const company = companyFor(sessionId);
	if (!user || !company) return null;
	return {
		user_id: user.userId,
		company_id: company.id,
		company_name: company.name,
		phone_masked: maskPhone(company.phone),
		exclusions: [...company.exclusions],
		lang: company.lang,
		kitchen_type: company.kitchenType
	};
}

/** `GET /api/v1/private/inbox`, newest last. Null without a session. */
export function inbox(sessionId: string | null | undefined): InboxMessage[] | null {
	const user = sessionId ? store().users.get(sessionId) : undefined;
	return user ? [...user.inbox] : null;
}

/** Live inbox messages for one user (the SSE stream). Returns the unsubscribe function. */
export function subscribe(sessionId: string, listener: Listener): () => void {
	const { listeners } = store();
	let set = listeners.get(sessionId);
	if (!set) listeners.set(sessionId, (set = new Set()));
	set.add(listener);
	return () => set.delete(listener);
}

/**
 * What the real service does when a call ends after `request_confirmation`: the
 * held message goes to the user's inbox (and by SMS for allowlisted numbers).
 * The link opens the confirmation page's fixture (`fx-ready-<id>`, 128,40 €).
 */
export function deliverConfirmation(sessionId: string): { quoteId: string; totalCents: number; deliveryStatus: DeliveryStatus } {
	const s = store();
	const user = s.users.get(sessionId);
	if (!user) throw new Error('No such demo user');
	const company = s.companies.get(user.phone);
	const id = `${Date.now().toString(36)}${(s.nextMessage++).toString(36)}`;
	const totalCents = 12840;
	const fi = company?.lang === 'fi';
	const message: InboxMessage = {
		id,
		at: new Date().toISOString(),
		text: fi
			? `S.I.MO: vahvista tilauksesi, 128,40 €. Mitään ei tilata ennen kuin vahvistat. Junction 2026 -demo, oikeaa tilausta ei tehdä.`
			: `S.I.MO: confirm your order, 128,40 €. Nothing is ordered until you confirm. Junction 2026 demo, no real order is placed.`,
		link: `/c/fx-ready-${id}${fi ? '?lang=fi' : ''}`
	};
	user.inbox.push(message);
	for (const listener of s.listeners.get(sessionId) ?? []) listener(message);

	const deliveryStatus: DeliveryStatus = user.phone.endsWith('7001') ? 'sent' : user.phone.endsWith('7002') ? 'failed' : 'off';
	return { quoteId: `q-${id}`, totalCents, deliveryStatus };
}

function companyFor(sessionId: string | null | undefined): Company | null {
	const s = store();
	const user = sessionId ? s.users.get(sessionId) : undefined;
	return user ? (s.companies.get(user.phone) ?? null) : null;
}

function accountView(company: Company, user: User, newCompany: boolean, newUser: boolean): DemoAccount {
	return {
		user_id: user.userId,
		company_id: company.id,
		company_name: company.name,
		phone_masked: maskPhone(company.phone),
		exclusions: [...company.exclusions],
		usual_items: usualItems(company.exclusions),
		new_company: newCompany,
		new_user: newUser,
		kitchen_type: company.kitchenType
	};
}

// --- Generated company names: funny, alliterating Finnish Oy names ---

const ADJECTIVES = [
	'Hassu', 'Iloinen', 'Pörröinen', 'Reipas', 'Sävyisä', 'Kiltti', 'Uninen', 'Nälkäinen', 'Hurja', 'Pirteä',
	'Mahtava', 'Lempeä', 'Vikkelä', 'Topakka', 'Kekseliäs', 'Tuhti', 'Utelias', 'Jäyhä', 'Ketterä', 'Leppoisa'
];
const ANIMALS = [
	'Hauki', 'Ilves', 'Peura', 'Rusakko', 'Siili', 'Kurki', 'Ukkometso', 'Näätä', 'Hirvi', 'Pöllö',
	'Majava', 'Lohi', 'Varis', 'Tikka', 'Kettu', 'Tiainen', 'Ahven', 'Joutsen', 'Karhu', 'Lumikko'
];

/** Same letter first: "Hassu Hauki Oy". Deterministic per number, unique per run. */
function uniqueName(phone: string): string {
	const taken = new Set([...store().companies.values()].map((c) => c.name));
	const all = ADJECTIVES.flatMap((adjective) => ANIMALS.map((animal) => `${adjective} ${animal} Oy`));
	const alliterating = all.filter((name) => name[0] === name.split(' ')[1][0]);
	const start = hash(phone);
	for (const list of [alliterating, all]) {
		for (let i = 0; i < list.length; i++) {
			const name = list[(start + i) % list.length];
			if (!taken.has(name)) return name;
		}
	}
	return `Keittiö ${phone.slice(-4)} Oy`;
}

function hash(value: string): number {
	let h = 2166136261;
	for (const char of value) h = Math.imul(h ^ char.charCodeAt(0), 16777619);
	return h >>> 0;
}

// --- Usual items: seeded order history, kept safe for the kitchen ---

interface SeedItem extends UsualItem {
	contains: Exclusion[];
}

const SEED_ITEMS: SeedItem[] = [
	{ product_id: '6408430000203', name: { en: 'Valio butter 500 g', fi: 'Valio voi 500 g' }, quantity: 20, unit: 'kg', contains: ['milk_free', 'vegan'] },
	{ product_id: '6408430000043', name: { en: 'Oat drink 1 l', fi: 'Kaurajuoma 1 l' }, quantity: 24, unit: 'l', contains: [] },
	{ product_id: '6408430000111', name: { en: 'Lactose-free milk 1 l', fi: 'Laktoositon maito 1 l' }, quantity: 40, unit: 'l', contains: ['milk_free', 'vegan'] },
	{ product_id: '6408430000301', name: { en: 'Ground beef 10 % 2,5 kg', fi: 'Naudan jauheliha 10 % 2,5 kg' }, quantity: 5, unit: 'kg', contains: ['vegan'] },
	{ product_id: '6408430000402', name: { en: 'Rapeseed oil 5 l', fi: 'Rypsiöljy 5 l' }, quantity: 10, unit: 'l', contains: [] },
	{ product_id: '6408430000505', name: { en: 'Edam cheese 3 kg', fi: 'Edam-juusto 3 kg' }, quantity: 6, unit: 'kg', contains: ['milk_free', 'vegan'] },
	{ product_id: '6408430000606', name: { en: 'Wheat tortillas 18 pcs', fi: 'Vehnätortillat 18 kpl' }, quantity: 4, unit: 'package', contains: ['gluten_free'] }
];

function usualItems(exclusions: Exclusion[]): UsualItem[] {
	return SEED_ITEMS.filter((item) => !item.contains.some((e) => exclusions.includes(e)))
		.slice(0, 3)
		.map(({ contains: _contains, ...item }) => item);
}
