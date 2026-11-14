import { describe, expect, it, vi } from 'vitest';
import { cardEnvelopes } from './fixtures';
import type { A2uiClientAction, A2uiServerEnvelope } from './protocol';
import { SIMO_CATALOG_ID } from './protocol';
import { getPath, setPath, SurfaceStore } from './surfaces.svelte';

function store() {
	const actions: A2uiClientAction[] = [];
	return { store: new SurfaceStore((a) => actions.push(a)), actions };
}

describe('getPath', () => {
	const data = { a: { b: [10, { c: 'x' }] }, 'we/ird': { '~k': 1 } };

	it('reads nested objects and arrays', () => {
		expect(getPath(data, '/a/b/0')).toBe(10);
		expect(getPath(data, '/a/b/1/c')).toBe('x');
	});

	it('returns the whole model for an empty pointer', () => {
		expect(getPath(data, '')).toBe(data);
		expect(getPath(data, '/')).toBe(data);
	});

	it('unescapes ~1 and ~0', () => {
		expect(getPath(data, '/we~1ird/~0k')).toBe(1);
	});

	it('is undefined for a missing step', () => {
		expect(getPath(data, '/a/x/y')).toBeUndefined();
		expect(getPath(null, '/a')).toBeUndefined();
		expect(getPath('text', '/length')).toBeUndefined();
	});

	it('never reads through the prototype', () => {
		expect(getPath({}, '/constructor')).toBeUndefined();
		expect(getPath({}, '/__proto__')).toBeUndefined();
		expect(getPath({}, '/toString')).toBeUndefined();
	});
});

describe('setPath', () => {
	it('replaces the whole model for an empty pointer', () => {
		expect(setPath({ a: 1 }, '', { b: 2 })).toEqual({ b: 2 });
	});

	it('makes objects along the way and leaves the input alone', () => {
		const input = { a: { keep: true } };
		const output = setPath(input, '/a/b/c', 5);
		expect(output).toEqual({ a: { keep: true, b: { c: 5 } } });
		expect(input).toEqual({ a: { keep: true } });
	});

	it('replaces a non-object step', () => {
		expect(setPath({ a: 3 }, '/a/b', 1)).toEqual({ a: { b: 1 } });
	});

	it('refuses prototype keys anywhere in the path', () => {
		const input = { a: 1 };
		expect(setPath(input, '/__proto__/polluted', true)).toBe(input);
		expect(setPath(input, '/a/constructor/prototype/polluted', true)).toBe(input);
		expect(setPath(input, '/prototype', true)).toBe(input);
		expect(({} as Record<string, unknown>).polluted).toBeUndefined();
	});
});

describe('SurfaceStore', () => {
	it('creates a surface on our catalog and keeps the order', () => {
		const { store: s } = store();
		s.process(cardEnvelopes('s1', 'QuoteCard', { quoteId: 'q_ready' }));
		s.process(cardEnvelopes('s2', 'SentNotice'));
		expect(s.order).toEqual(['s1', 's2']);
		expect(s.surfaces.s1.supported).toBe(true);
		expect(s.surfaces.s1.components.card).toMatchObject({ component: 'QuoteCard', quoteId: 'q_ready' });
		expect(s.surfaces.s1.components.root.children).toEqual(['card']);
	});

	it('marks a surface on another catalog as unsupported', () => {
		const { store: s } = store();
		s.process([{ version: 'v0.9', createSurface: { surfaceId: 'x', catalogId: 'https://a2ui.org/standard.json' } }]);
		expect(s.surfaces.x.supported).toBe(false);
	});

	it('creating a surface again resets it but keeps its place', () => {
		const { store: s } = store();
		s.process(cardEnvelopes('s1', 'QuoteCard', { quoteId: 'q1' }));
		s.process(cardEnvelopes('s2', 'SentNotice'));
		s.process([{ version: 'v0.9', createSurface: { surfaceId: 's1', catalogId: SIMO_CATALOG_ID } }]);
		expect(s.order).toEqual(['s1', 's2']);
		expect(s.surfaces.s1.components).toEqual({});
	});

	it('updates components by id and ignores unknown surfaces and bad entries', () => {
		const { store: s } = store();
		s.process(cardEnvelopes('s1', 'QuoteCard', { quoteId: 'q1' }));
		s.process([
			{
				version: 'v0.9',
				updateComponents: {
					surfaceId: 's1',
					components: [
						{ id: 'card', component: 'QuoteCard', quoteId: 'q2' },
						{ id: 7, component: 'Text' },
						null,
						{ id: '__proto__', component: 'Text' }
					]
				}
			},
			{ version: 'v0.9', updateComponents: { surfaceId: 'nope', components: [{ id: 'root', component: 'Text' }] } }
		] as unknown as A2uiServerEnvelope[]);
		expect(s.surfaces.s1.components.card.quoteId).toBe('q2');
		expect(Object.keys(s.surfaces.s1.components).sort()).toEqual(['card', 'root']);
		expect(s.surfaces.nope).toBeUndefined();
	});

	it('updates the data model at a path or as a whole', () => {
		const { store: s } = store();
		s.process(cardEnvelopes('s1', 'Text'));
		s.process([{ version: 'v0.9', updateDataModel: { surfaceId: 's1', value: { portions: 80 } } }]);
		s.process([{ version: 'v0.9', updateDataModel: { surfaceId: 's1', path: '/answer/text', value: 'yes' } }]);
		expect(s.surfaces.s1.data).toEqual({ portions: 80, answer: { text: 'yes' } });
		s.process([{ version: 'v0.9', updateDataModel: { surfaceId: 's1', path: '/__proto__/x', value: 1 } }]);
		expect(s.surfaces.s1.data).toEqual({ portions: 80, answer: { text: 'yes' } });
	});

	it('deletes a surface and drops it from the order', () => {
		const { store: s } = store();
		s.process(cardEnvelopes('s1', 'Text'));
		s.process(cardEnvelopes('s2', 'Text'));
		s.process([{ version: 'v0.9', deleteSurface: { surfaceId: 's1' } }]);
		expect(s.order).toEqual(['s2']);
		expect(s.surfaces.s1).toBeUndefined();
	});

	it('skips envelopes that are not objects or have no surface id', () => {
		const { store: s } = store();
		s.process([null, 'x', 3, { createSurface: {} }, { unknownKind: {} }] as unknown as A2uiServerEnvelope[]);
		s.process('not an array' as unknown as A2uiServerEnvelope[]);
		expect(s.order).toEqual([]);
	});

	it('emits actions with fixed context over bound context', () => {
		const { store: s, actions } = store();
		s.process(cardEnvelopes('s1', 'Button'));
		s.setData('s1', '/form', { portions: 120, note: 'bound' });
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2026-11-14T12:00:00Z'));
		s.emit('s1', 'card', 'portions_answered', { note: 'fixed' }, { portions: '/form/portions', note: '/form/note' });
		vi.useRealTimers();
		expect(actions).toEqual([
			{
				name: 'portions_answered',
				surfaceId: 's1',
				sourceComponentId: 'card',
				timestamp: '2026-11-14T12:00:00.000Z',
				context: { portions: 120, note: 'fixed' }
			}
		]);
	});

	it('remembers what the buyer did on a card', () => {
		const { store: s } = store();
		expect(s.actedOn('s1', 'card')).toBeUndefined();
		s.markActed('s1', 'card', 'selected');
		expect(s.actedOn('s1', 'card')).toBe('selected');
		expect(s.actedOn('s2', 'card')).toBeUndefined();
	});
});
