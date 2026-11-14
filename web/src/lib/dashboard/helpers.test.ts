import { describe, expect, it } from 'vitest';
import {
	formatClock,
	formatDay,
	formatDemoTime,
	formatMinutes,
	formatMoney,
	formatTime,
	secondsSince
} from './format';
import { pick, resolveLang, t } from './i18n';
import { channelBadge, exclusionsSentence, parseFilter, stateGroup, statusText } from './states';

const NBSP = ' ';

describe('formatMoney', () => {
	it('uses a comma and spaces in Finnish', () => {
		expect(formatMoney(115000, 'fi')).toBe(`1${NBSP}150,00${NBSP}€`);
		expect(formatMoney(12840, 'fi')).toBe(`128,40${NBSP}€`);
		expect(formatMoney(421000, 'fi')).toBe(`4${NBSP}210,00${NBSP}€`);
	});

	it('uses a point and commas in English', () => {
		expect(formatMoney(115000, 'en')).toBe(`1,150.00${NBSP}€`);
		expect(formatMoney(5, 'en')).toBe(`0.05${NBSP}€`);
		expect(formatMoney(123456789, 'en')).toBe(`1,234,567.89${NBSP}€`);
	});

	it('keeps the sign', () => {
		expect(formatMoney(-2580, 'en')).toBe(`-25.80${NBSP}€`);
	});
});

describe('time in state', () => {
	const now = Date.parse('2026-11-12T10:10:00+02:00');

	it('counts whole seconds and never goes negative', () => {
		expect(secondsSince('2026-11-12T10:08:48+02:00', now)).toBe(72);
		expect(secondsSince('2026-11-12T10:11:00+02:00', now)).toBe(0);
		expect(secondsSince('not a date', now)).toBe(0);
	});

	it('formats a call timer', () => {
		expect(formatClock(72)).toBe('1:12');
		expect(formatClock(5)).toBe('0:05');
		expect(formatClock(3729)).toBe('1:02:09');
	});

	it('formats minutes', () => {
		expect(formatMinutes(30, 'en')).toBe('<1 min');
		expect(formatMinutes(125, 'en')).toBe('2 min');
		expect(formatMinutes(3900, 'fi')).toBe('1 h 5 min');
		expect(formatMinutes(7200, 'en')).toBe('2 h');
	});

	it('builds the status pill text', () => {
		const card = { channel: 'phone' as const, state_since: '2026-11-12T10:08:48+02:00' };
		expect(statusText({ ...card, state: 'in_conversation' }, 'en', now)).toBe('In call, 1:12');
		expect(statusText({ ...card, state: 'awaiting_confirmation' }, 'en', now)).toBe('Waiting, 1 min');
		expect(statusText({ ...card, state: 'confirmed' }, 'en', now)).toBe('Confirmed 10:08');
		expect(statusText({ ...card, state: 'sms_failed' }, 'fi', now)).toBe('SMS epäonnistui');
		expect(statusText({ ...card, channel: 'webmcp', state: 'in_conversation' }, 'en', now)).toBe(
			'Building quote'
		);
	});
});

describe('dates in Europe/Helsinki', () => {
	it('shows times in Helsinki whatever the offset', () => {
		expect(formatTime('2026-11-12T08:04:12Z', 'en')).toBe('10:04');
		expect(formatTime('2026-11-12T10:04:12+02:00', 'fi')).toBe('10:04');
	});

	it('formats a delivery day', () => {
		expect(formatDay('2026-11-16', 'en')).toBe('Mon 16 Nov');
		expect(formatDay('2026-11-16', 'fi')).toBe('ma 16.11.');
	});

	it('formats the demo clock', () => {
		expect(formatDemoTime('2026-11-12T09:00:00+02:00', 'en')).toBe('Thu 12 Nov 09:00');
	});
});

describe('language', () => {
	it('lets ?lang= win, then storage, then English', () => {
		expect(resolveLang('fi', 'en')).toBe('fi');
		expect(resolveLang(null, 'fi')).toBe('fi');
		expect(resolveLang('de', 'xx')).toBe('en');
		expect(resolveLang(undefined, null)).toBe('en');
	});

	it('picks one language and falls back when it is empty', () => {
		expect(pick({ en: 'Milk', fi: 'Maito' }, 'fi')).toBe('Maito');
		expect(pick({ en: 'Milk', fi: '' }, 'fi')).toBe('Milk');
		expect(pick(null, 'en')).toBe('');
	});

	it('fills placeholders in UI strings', () => {
		expect(t('found_left', 'en', { found: 14, left: 5 })).toBe('14 found, 5 left');
		expect(t('found_left', 'fi', { found: 14, left: 5 })).toBe('14 löytyi, 5 jäljellä');
	});
});

describe('states and words', () => {
	it('groups states for the counters', () => {
		expect(stateGroup('quote_ready')).toBe('active');
		expect(stateGroup('link_opened')).toBe('waiting');
		expect(stateGroup('requote_needed')).toBe('attention');
		expect(stateGroup('abandoned')).toBeNull();
	});

	it('says the exclusions in words', () => {
		expect(exclusionsSentence(['milk_free', 'nut_free'], 'en')).toBe('Avoids milk and nuts');
		expect(exclusionsSentence([], 'en')).toBe('No restrictions');
		expect(exclusionsSentence(['milk_free', 'gluten_free', 'nut_free'], 'fi')).toBe(
			'Välttää maito, gluteeni ja pähkinät'
		);
	});

	it('names the connector by its client', () => {
		expect(channelBadge('mcp', 'Claude', 'en')).toBe('Claude connector');
		expect(channelBadge('web_chat', 'web chat', 'en')).toBe('Webshop chat');
	});

	it('reads only known filters from the URL', () => {
		expect(parseFilter(new URLSearchParams('state=waiting&channel=phone'))).toEqual({
			state: 'waiting',
			channel: 'phone'
		});
		expect(parseFilter(new URLSearchParams('state=bogus&channel=fax'))).toEqual({ state: null, channel: null });
	});
});

describe('UI text rules', () => {
	it('never uses the middle-dot character', async () => {
		const sources = import.meta.glob(['./**/*.{ts,svelte,json}', '../../routes/dashboard/**/*.svelte'], {
			query: '?raw',
			import: 'default',
			eager: true
		});
		expect(Object.keys(sources).length).toBeGreaterThan(20);
		for (const [file, text] of Object.entries(sources)) {
			expect(String(text).includes('\u00b7'), file).toBe(false);
		}
	});
});
