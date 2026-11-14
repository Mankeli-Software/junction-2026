/**
 * Money, dates and times for the confirmation page (docs/specs/confirmation-page.md §6):
 * euros with two decimals and a decimal comma in both languages, dates in words,
 * times in Europe/Helsinki.
 */
import type { Lang } from './types';

const TIME_ZONE = 'Europe/Helsinki';

const moneyFormat = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' });

export function money(cents: number): string {
	return moneyFormat.format(cents / 100);
}

/** "Mon 16 Nov" or "ma 16.11." */
export function date(iso: string, lang: Lang): string {
	const value = new Date(iso.length === 10 ? `${iso}T12:00:00Z` : iso);
	return lang === 'fi'
		? new Intl.DateTimeFormat('fi-FI', { weekday: 'short', day: 'numeric', month: 'numeric', timeZone: TIME_ZONE }).format(value)
		: new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TIME_ZONE })
				.format(value)
				.replace(',', '');
}

/** "10:02" or "10.02" */
export function time(iso: string, lang: Lang): string {
	return new Intl.DateTimeFormat(lang === 'fi' ? 'fi-FI' : 'en-GB', {
		hour: '2-digit',
		minute: '2-digit',
		timeZone: TIME_ZONE
	}).format(new Date(iso));
}
