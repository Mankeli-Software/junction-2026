/** The cards' pure helpers, the fixture ChatData and the catalog. */
import { describe, expect, it } from 'vitest';
import catalog from './catalog.json';
import { fixtureData, fixtureQuestionQuote, fixtureReadyQuote } from './fixtures';
import { amount, measure, parseAmount, safeImage, scaled } from './format';
import { t } from './i18n';
import { isNotFound } from './api';
import { SIMO_CATALOG_ID, SIMO_COMPONENTS } from './protocol';
import { askedLabel, lineFlagCodes, newerQuoteSurface, productLabel, quoteSections } from './quote';
import { SurfaceStore } from './surfaces.svelte';
import { cardEnvelopes } from './fixtures';

describe('format', () => {
	it('parses amounts with a comma or a point', () => {
		expect(parseAmount('2,5')).toBe(2.5);
		expect(parseAmount(' 2.5 ')).toBe(2.5);
		expect(parseAmount('')).toBeNull();
		expect(parseAmount('ripaus')).toBeUndefined();
		expect(parseAmount('0')).toBeUndefined();
		expect(parseAmount('1e3')).toBeUndefined();
		expect(parseAmount('-1')).toBeUndefined();
		expect(parseAmount('100001')).toBeUndefined();
	});

	it('scales from the servings to the portions', () => {
		expect(scaled(100, 20, 120)).toBe(600);
		expect(scaled(2.5, 20, 120)).toBe(15);
		expect(scaled(1, null, 120)).toBe(1);
		expect(scaled(null, 20, 120)).toBeNull();
	});

	it('writes numbers with a decimal comma', () => {
		expect(amount(2.5)).toBe('2,5');
		expect(amount(null)).toBe('');
		expect(measure(1.6, 'kg')).toBe('1,6 kg');
		expect(measure(null, 'kpl')).toBe('kpl');
	});

	it('lets only http(s) and same-origin images through', () => {
		expect(safeImage('https://cdn.example/x.jpg')).toBe('https://cdn.example/x.jpg');
		expect(safeImage('/images/x.jpg')).toBe('/images/x.jpg');
		expect(safeImage('//evil.example/x.jpg')).toBeNull();
		expect(safeImage('javascript:alert(1)')).toBeNull();
		expect(safeImage('data:image/png;base64,AAAA')).toBeNull();
		expect(safeImage(null)).toBeNull();
	});
});

describe('i18n', () => {
	it('fills the placeholders', () => {
		expect(t('en', 'sourceMakes', { n: 20, portions: 120 })).toBe('The recipe makes 20. Amounts are scaled to 120.');
		expect(t('fi', 'alsoSms', { number: '+358 40 *** **12' })).toBe('Lähetetty myös tekstiviestinä numeroon +358 40 *** **12');
	});
});

describe('quote helpers', () => {
	it('groups the lines per group, then the rest as other lines', () => {
		const sections = quoteSections(fixtureQuestionQuote);
		expect(sections.map((s) => [s.kind, s.group, s.subtotalCents, s.lines.map((l) => l.line_id)])).toEqual([
			['photo', 'Karjalanpiirakat', 1872, ['p5', 'p6']],
			['other', null, 12480, ['l1']]
		]);
		expect(sections[0].draftId).toBe('rd_notebook');
	});

	it('writes what was asked and what was added', () => {
		const [milk, , lactoseFree] = fixtureQuestionQuote.lines;
		expect(askedLabel(milk, 'en')).toBe('maitoa 6 l');
		expect(askedLabel(lactoseFree, 'en')).toBe('60 l lactose-free milk');
		expect(productLabel(milk, 'en')).toBe('Valio light milk 1 l, 6 cartons');
		expect(productLabel(milk, 'fi')).toBe('Valio kevytmaito 1 l, 6 tölkkiä');
	});

	it('finds the flags of a line', () => {
		expect(lineFlagCodes(fixtureQuestionQuote, 'p6')).toEqual(['ROUNDED_UP']);
		expect(lineFlagCodes(fixtureQuestionQuote, 'p5')).toEqual([]);
	});

	it('knows when a later QuoteCard shows a newer quote', () => {
		const store = new SurfaceStore(() => {});
		store.process(cardEnvelopes('s1', 'QuoteCard', { quoteId: 'q_question' }));
		expect(newerQuoteSurface(store, 's1', 'card', 'q_question')).toBeNull();
		store.process(cardEnvelopes('s2', 'Text', { text: 'One question first.' }));
		store.process(cardEnvelopes('s3', 'QuoteCard', { quoteId: 'q_ready' }));
		expect(newerQuoteSurface(store, 's1', 'card', 'q_question')).toBeNull();
		store.markActed('s3', 'card#loaded', 'q_ready');
		expect(newerQuoteSurface(store, 's1', 'card', 'q_question')).toBe('s3');
		expect(newerQuoteSurface(store, 's3', 'card', 'q_ready')).toBeNull();
	});

	it('leaves out the surfaces the host skips, such as the Current order drawer', () => {
		const store = new SurfaceStore(() => {});
		store.process(cardEnvelopes('s1', 'QuoteCard', { quoteId: 'q_question' }));
		store.process(cardEnvelopes('current-order', 'QuoteCard', { quoteId: 'q_ready' }));
		store.markActed('current-order', 'card#loaded', 'q_ready');
		expect(newerQuoteSurface(store, 's1', 'card', 'q_question')).toBe('current-order');
		expect(newerQuoteSurface(store, 's1', 'card', 'q_question', (sid) => sid === 'current-order')).toBeNull();
	});
});

describe('fixtureData', () => {
	it('answers 404 for an unknown id', async () => {
		const data = fixtureData();
		await expect(data.getQuote('q_nope')).rejects.toSatisfy(isNotFound);
		await expect(data.getDraft('rd_nope')).rejects.toSatisfy(isNotFound);
	});

	it('confirms a draft with the edits and scales it', async () => {
		const data = fixtureData();
		const draft = await data.getDraft('rd_notebook');
		const edited = draft.ingredients.map((i) => (i.index === 5 ? { ...i, amount: 7, confidence: 'high' as const, note: null } : i));
		const confirmed = await data.confirmDraft('rd_notebook', { portions: 40, ingredients: edited, use_ai_reading: false });
		expect(confirmed.status).toBe('confirmed');
		expect(confirmed.scaled.find((i) => i.index === 5)?.amount).toBe(14);
		expect(data.calls.map((c) => c.method)).toEqual(['getDraft', 'confirmDraft']);
		await expect(data.discardDraft('rd_notebook')).rejects.toThrow();
	});

	it('uses what the AI saw for a dish photo', async () => {
		const data = fixtureData();
		const confirmed = await data.confirmDraft('rd_dish', { use_ai_reading: true });
		expect(confirmed.ingredients.map((i) => i.text)).toEqual(['lohta', 'perunaa', 'kermaa', 'tilliä']);
		expect(confirmed.matched_recipe).toBeNull();
	});

	it('copies a confirmed draft into a new one', async () => {
		const data = fixtureData();
		await data.confirmDraft('rd_notebook', { use_ai_reading: false });
		const copy = await data.copyDraft('rd_notebook');
		expect(copy.status).toBe('draft');
		expect(copy.draft_id).not.toBe('rd_notebook');
		expect((await data.getDraft(copy.draft_id)).status).toBe('draft');
	});

	it('keeps each instance separate', async () => {
		await fixtureData().discardDraft('rd_notebook');
		expect((await fixtureData().getDraft('rd_notebook')).status).toBe('draft');
	});

	it('scales a recipe to the portions', async () => {
		const recipe = await fixtureData().getRecipe('r_1188', 80);
		expect(recipe.portions).toBe(80);
		expect(recipe.ingredients[0].quantity).toBe(4);
	});

	it('fails on demand and reports what was sent', async () => {
		const data = fixtureData({ failing: ['q_ready'], sent: null });
		await expect(data.getQuote('q_ready')).rejects.toThrow('500');
		expect(await data.getSentLatest()).toBeNull();
		expect(fixtureReadyQuote.status).toBe('ready');
	});
});

describe('catalog', () => {
	it('lists exactly the components the renderer draws', () => {
		expect(catalog.id).toBe(SIMO_CATALOG_ID);
		expect(catalog.components.map((c) => c.name).sort()).toEqual([...SIMO_COMPONENTS].sort());
	});

	it('names the actions of plan section 3', () => {
		const text = JSON.stringify(catalog);
		for (const action of [
			'recipe_confirmed',
			'recipe_discarded',
			'clarification_answered',
			'send_for_confirmation',
			'recipe_selected',
			'recipe_swap',
			'menu_swap_day',
			'menu_build'
		]) {
			expect(text).toContain(action);
		}
	});

	it('has no middle dot in any text', () => {
		expect(JSON.stringify(catalog)).not.toContain('\u00b7');
	});
});
