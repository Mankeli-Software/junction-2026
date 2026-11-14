import { describe, expect, test } from 'vitest';
import { preferredLanguage, shopLang } from './lang';

describe('shopLang', () => {
	test.each([
		['fi', 'fi'],
		['fi-FI,fi;q=0.9,en;q=0.8', 'fi'],
		['FI-fi', 'fi'],
		['en-US,en;q=0.9,fi;q=0.8', 'en'],
		['sv-FI,fi;q=0.9', 'en'],
		['en;q=0.5,fi;q=0.8', 'fi'],
		['de', 'en'],
		['*', 'en'],
		['', 'en']
	])('auto with Accept-Language %j is %s', (header, lang) => {
		expect(shopLang('auto', null, header)).toBe(lang);
	});

	test('no header is English', () => {
		expect(shopLang('auto', null, null)).toBe('en');
	});

	test('a fixed setting ignores the browser', () => {
		expect(shopLang('fi', null, 'en-US')).toBe('fi');
		expect(shopLang('en', null, 'fi-FI')).toBe('en');
	});

	test('the toggle wins over the setting and the browser', () => {
		expect(shopLang('auto', 'en', 'fi-FI')).toBe('en');
		expect(shopLang('fi', 'en', 'fi')).toBe('en');
		expect(shopLang('en', 'fi', 'en')).toBe('fi');
		expect(shopLang('auto', 'sv', 'fi')).toBe('fi');
	});
});

test('preferredLanguage skips q=0', () => {
	expect(preferredLanguage('fi;q=0, en;q=0.1')).toBe('en');
});
