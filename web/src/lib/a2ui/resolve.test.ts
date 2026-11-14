import { describe, expect, it } from 'vitest';
import { buttonAction } from './actions';
import { ids, int, record, str } from './resolve';
import type { Surface } from './surfaces.svelte';

const surface: Surface = {
	id: 's1',
	catalogId: 'x',
	components: {},
	supported: true,
	data: { name: 'Lasagne', portions: 80, text: '120', empty: '  ', nested: { id: 'q_1' } }
};

describe('str', () => {
	it('reads a literal or a binding', () => {
		expect(str(surface, 'hello')).toBe('hello');
		expect(str(surface, { path: '/name' })).toBe('Lasagne');
		expect(str(surface, { path: '/nested/id' })).toBe('q_1');
	});

	it('turns numbers into text and cuts long text', () => {
		expect(str(surface, 42)).toBe('42');
		expect(str(surface, 'abcdef', 3)).toBe('abc');
	});

	it('drops empty, missing and wrong types', () => {
		expect(str(surface, '')).toBeUndefined();
		expect(str(surface, { path: '/empty' })).toBeUndefined();
		expect(str(surface, { path: '/missing' })).toBeUndefined();
		expect(str(surface, { path: 3 })).toBeUndefined();
		expect(str(surface, { other: 'x' })).toBeUndefined();
		expect(str(surface, ['a'])).toBeUndefined();
		expect(str(surface, null)).toBeUndefined();
		expect(str(surface, true)).toBeUndefined();
	});
});

describe('int', () => {
	it('reads integers within the range, also from text', () => {
		expect(int(surface, 5, 1, 10)).toBe(5);
		expect(int(surface, { path: '/portions' }, 1, 1000)).toBe(80);
		expect(int(surface, { path: '/text' }, 1, 1000)).toBe(120);
	});

	it('drops fractions, out of range and wrong types', () => {
		expect(int(surface, 2.5, 1, 10)).toBeUndefined();
		expect(int(surface, 0, 1, 10)).toBeUndefined();
		expect(int(surface, 11, 1, 10)).toBeUndefined();
		expect(int(surface, 'many', 1, 10)).toBeUndefined();
		expect(int(surface, null, 1, 10)).toBeUndefined();
	});
});

describe('ids and record', () => {
	it('keeps only string ids, at most 30', () => {
		expect(ids(['a', 1, null, 'b'])).toEqual(['a', 'b']);
		expect(ids('a')).toEqual([]);
		expect(ids(Array.from({ length: 40 }, (_, i) => `c${i}`))).toHaveLength(30);
	});

	it('returns plain objects only', () => {
		expect(record({ a: 1 })).toEqual({ a: 1 });
		expect(record([1])).toEqual({});
		expect(record(null)).toEqual({});
		expect(record('x')).toEqual({});
	});
});

describe('buttonAction', () => {
	it('reads the A2UI v0.9 event shape', () => {
		expect(buttonAction({ event: { name: 'portions_answered', context: { portions: 120 } } })).toEqual({
			name: 'portions_answered',
			context: { portions: 120 },
			paths: {}
		});
	});

	it('reads the short shape', () => {
		expect(buttonAction({ name: 'yes', context: { ok: true, word: 'kyllä' } })).toEqual({
			name: 'yes',
			context: { ok: true, word: 'kyllä' },
			paths: {}
		});
	});

	it('works without a context', () => {
		expect(buttonAction({ event: { name: 'start_over' } })).toEqual({ name: 'start_over', context: {}, paths: {} });
	});

	it('splits literals from data bindings and drops other values', () => {
		expect(
			buttonAction({
				event: {
					name: 'answer',
					context: { a: 'x', b: 2, c: { path: '/form/c' }, d: { nested: 1 }, e: null, f: [1], g: Number.NaN }
				}
			})
		).toEqual({ name: 'answer', context: { a: 'x', b: 2 }, paths: { c: '/form/c' } });
	});

	it('rejects a missing, empty or odd name', () => {
		expect(buttonAction(undefined)).toBeNull();
		expect(buttonAction({})).toBeNull();
		expect(buttonAction({ event: {} })).toBeNull();
		expect(buttonAction({ name: '' })).toBeNull();
		expect(buttonAction({ name: { path: '/x' } })).toBeNull();
		expect(buttonAction({ name: 'has spaces' })).toBeNull();
		expect(buttonAction({ name: 'x'.repeat(61) })).toBeNull();
	});

	it('prefers event over a top-level name', () => {
		expect(buttonAction({ name: 'outer', event: { name: 'inner' } })?.name).toBe('inner');
	});

	it('never copies prototype keys and cuts long text', () => {
		const context = JSON.parse('{"__proto__": {"polluted": true}, "long": "' + 'a'.repeat(500) + '"}');
		const action = buttonAction({ name: 'x', context });
		expect(Object.keys(action?.context ?? {})).toEqual(['long']);
		expect((action?.context.long as string).length).toBe(400);
		expect(({} as Record<string, unknown>).polluted).toBeUndefined();
	});
});
