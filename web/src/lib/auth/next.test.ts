import { describe, expect, it } from 'vitest';
import { safeNext, withNext } from './next';

describe('safeNext', () => {
	it('keeps paths on this site', () => {
		expect(safeNext('/connect?request=abc')).toBe('/connect?request=abc');
		expect(safeNext('/phone?inbox=1#x')).toBe('/phone?inbox=1#x');
	});

	it('refuses other sites and odd forms', () => {
		for (const raw of [
			null,
			'',
			'https://evil.example/',
			'//evil.example/x',
			'/\\evil.example',
			'javascript:alert(1)',
			'connect',
			'/\tevil'
		]) {
			expect(safeNext(raw)).toBeNull();
		}
	});
});

describe('withNext', () => {
	it('carries next and the language', () => {
		expect(withNext('/signup', '/connect?request=a b')).toBe('/signup?next=%2Fconnect%3Frequest%3Da+b');
		expect(withNext('/login', null, 'fi')).toBe('/login?lang=fi');
		expect(withNext('/login', null)).toBe('/login');
	});
});
