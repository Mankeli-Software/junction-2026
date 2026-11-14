import { describe, expect, it } from 'vitest';
import type { A2uiClientAction } from '#lib/a2ui/protocol.js';
import { dayName } from './i18n';
import { actionEcho, applyEvent, portionsFrom, readingErrorKey, withoutLinks, workingKey, type ChatState } from './messages';
import type { ChatEvent } from './stream';

function run(events: ChatEvent[], state: ChatState = { messages: [], working: { kind: 'thinking' }, conversationId: null }) {
	let n = 0;
	const effects = events.map((event) => applyEvent(state, event, () => `m${++n}`));
	return { state, effects };
}

const create = (surfaceId: string) => ({ version: 'v0.9' as const, createSurface: { surfaceId, catalogId: 'cat' } });

describe('applyEvent', () => {
	it('builds agent text from deltas and places surfaces between texts, in order', () => {
		const { state, effects } = run([
			{ type: 'start', conversation_id: 'c1' },
			{ type: 'text', delta: 'Here is ' },
			{ type: 'text', delta: 'your quote.' },
			{ type: 'a2ui', envelopes: [create('s1')] },
			{
				type: 'a2ui',
				envelopes: [
					{ version: 'v0.9', updateComponents: { surfaceId: 's1', components: [] } },
					create('s1')
				]
			},
			{ type: 'text', delta: 'Anything else?' },
			{ type: 'done', quote_id: 'q1' }
		]);
		expect(state.conversationId).toBe('c1');
		expect(state.messages).toEqual([
			{ kind: 'agent', id: 'm1', text: 'Here is your quote.' },
			{ kind: 'surface', id: 'm2', surfaceId: 's1' },
			{ kind: 'agent', id: 'm3', text: 'Anything else?' }
		]);
		expect(effects[3].envelopes).toHaveLength(1);
		expect(effects[6].done).toEqual({ quoteId: 'q1' });
		expect(state.working).toBeNull();
	});

	it('removes a deleted surface', () => {
		const { state } = run([
			{ type: 'a2ui', envelopes: [create('s1'), create('s2')] },
			{ type: 'a2ui', envelopes: [{ version: 'v0.9', deleteSurface: { surfaceId: 's1' } }] }
		]);
		expect(state.messages).toEqual([{ kind: 'surface', id: 'm2', surfaceId: 's2' }]);
	});

	it('shows a working line while a tool runs, and drops it when text comes', () => {
		const { state } = run([{ type: 'tool', name: 'build_quote', status: 'started' }]);
		expect(state.working).toEqual({ kind: 'tool', name: 'build_quote' });
		applyEvent(state, { type: 'tool', name: 'build_quote', status: 'done' }, () => 'x');
		expect(state.working).toEqual({ kind: 'thinking' });
		applyEvent(state, { type: 'text', delta: 'Done.' }, () => 'y');
		expect(state.working).toBeNull();
	});

	it('turns an error into a calm message', () => {
		const { state, effects } = run([{ type: 'error', code: 'not_configured', message: 'CHAT_MODEL is empty' }]);
		expect(state.messages).toEqual([{ kind: 'error', id: 'm1', key: 'errorNotConfigured' }]);
		expect(effects[0].error).toBe('not_configured');
		expect(run([{ type: 'error', code: 'whatever', message: '' }]).state.messages[0]).toMatchObject({ key: 'errorFailed' });
	});
});

describe('actionEcho', () => {
	const action = (name: string, context: Record<string, unknown> = {}): A2uiClientAction => ({
		name,
		surfaceId: 's1',
		sourceComponentId: 'c1',
		timestamp: '2026-11-14T12:00:00Z',
		context
	});

	it('says the known actions in plain words, in both languages', () => {
		expect(actionEcho('en', action('send_for_confirmation', { quoteId: 'q1' }), undefined)).toBe('Send it to my phone');
		expect(actionEcho('fi', action('send_for_confirmation'), undefined)).toBe('Lähetä se puhelimeeni');
		expect(actionEcho('en', action('recipe_selected', { recipeId: 'r1', portions: 80 }), undefined)).toBe('Use this recipe for 80');
		expect(actionEcho('en', action('recipe_confirmed', { draftId: 'd1' }), undefined)).toBe('Recipe confirmed');
		expect(actionEcho('en', action('menu_swap_day', { menuId: 'm', day: 'wed' }), undefined)).toBe('Swap Wednesday');
		expect(actionEcho('fi', action('menu_swap_day', { day: 2 }), undefined)).toBe('Vaihda keskiviikko');
		expect(actionEcho('en', action('menu_build', { menuId: 'm' }), undefined)).toBe('Build the order from this menu');
	});

	it('uses a button label for other actions, else the name in words', () => {
		const button = { id: 'c1', component: 'Button', label: 'Yes, 120' };
		expect(actionEcho('en', action('portions_answer'), button)).toBe('Yes, 120');
		expect(actionEcho('en', action('clarification_answered', { label: 'Six 1 l cartons' }), undefined)).toBe('Six 1 l cartons');
		expect(actionEcho('en', action('clarification_answered'), undefined)).toBe('This one');
		expect(actionEcho('en', action('make_it_bigger'), undefined)).toBe('Make it bigger');
	});
});

describe('helpers', () => {
	it('names menu days from keys, numbers and dates', () => {
		expect(dayName('en', 'Monday')).toBe('Monday');
		expect(dayName('en', '2026-11-18')).toBe('Wednesday');
		expect(dayName('en', 'someday')).toBeNull();
	});

	it('finds the portions next to a photo', () => {
		expect(portionsFrom('Karelian pies from my notebook, for 120 please.')).toBe(120);
		expect(portionsFrom('80 annosta')).toBe(80);
		expect(portionsFrom('lasagne 200 people')).toBe(200);
		expect(portionsFrom('my grandmother’s recipe')).toBeNull();
		expect(portionsFrom('for 5000 people')).toBeNull();
	});

	it('maps reading errors to short sentences', () => {
		expect([413, 415, 422, 502, 503, 504, 0, 500].map(readingErrorKey)).toEqual([
			'read413',
			'read415',
			'read422',
			'read502',
			'read503',
			'read504',
			'errorNetwork',
			'errorFailed'
		]);
	});

	it('labels the working line by tool', () => {
		expect(workingKey({ kind: 'tool', name: 'build_quote' })).toBe('building');
		expect(workingKey({ kind: 'reading' })).toBe('reading');
		expect(workingKey({ kind: 'tool', name: 'new_tool' })).toBe('working');
	});

	it('takes confirmation links out of agent text', () => {
		expect(withoutLinks('en', 'Open https://simo.mankeli.co/c/abc123 now')).toBe('Open (the link is in your demo phone) now');
		expect(withoutLinks('en', 'see /c/tok.')).toBe('see (the link is in your demo phone)');
		expect(withoutLinks('en', 'Your order is ready.')).toBe('Your order is ready.');
	});
});
