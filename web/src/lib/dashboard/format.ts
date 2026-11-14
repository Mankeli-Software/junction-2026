/** Money, time and quantity formatting (`docs/specs/dashboard.md` §6). Times in Europe/Helsinki. */
import type { Lang } from './types';

export const TIME_ZONE = 'Europe/Helsinki';

/** No-break space, so "1 150,00 €" never wraps inside a number. */
const NBSP = ' ';

function groupThousands(digits: string, separator: string): string {
	return digits.replace(/\B(?=(\d{3})+(?!\d))/g, separator);
}

/** Euros with two decimals: "1 150,00 €" in Finnish, "1,150.00 €" in English. */
export function formatMoney(cents: number, lang: Lang): string {
	const negative = cents < 0;
	const abs = Math.round(Math.abs(cents));
	const whole = Math.floor(abs / 100).toString();
	const fraction = (abs % 100).toString().padStart(2, '0');
	const number =
		lang === 'fi'
			? `${groupThousands(whole, NBSP)},${fraction}`
			: `${groupThousands(whole, ',')}.${fraction}`;
	return `${negative ? '-' : ''}${number}${NBSP}€`;
}

/** A plain decimal number in the language's style ("2,5" or "2.5"), for quantities and unit prices. */
export function formatNumber(value: number, lang: Lang, maxDecimals = 2): string {
	const rounded = Number(value.toFixed(maxDecimals));
	const [whole, fraction] = Math.abs(rounded).toString().split('.');
	const grouped = groupThousands(whole, lang === 'fi' ? NBSP : ',');
	const sign = rounded < 0 ? '-' : '';
	return fraction ? `${sign}${grouped}${lang === 'fi' ? ',' : '.'}${fraction}` : `${sign}${grouped}`;
}

/** A unit price, always with two decimals and no thousands grouping concerns ("8,38 €"). */
export function formatUnitPrice(euros: number, lang: Lang): string {
	return formatMoney(Math.round(euros * 100), lang);
}

/** Whole seconds from `since` to `now`, never negative. */
export function secondsSince(since: string, now: number): number {
	const start = Date.parse(since);
	if (Number.isNaN(start)) return 0;
	return Math.max(0, Math.floor((now - start) / 1000));
}

/** A call timer: "1:12", "12:05", "1:02:09". */
export function formatClock(totalSeconds: number): string {
	const s = Math.max(0, Math.floor(totalSeconds));
	const hours = Math.floor(s / 3600);
	const minutes = Math.floor((s % 3600) / 60);
	const seconds = (s % 60).toString().padStart(2, '0');
	return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}

/** Time in a state for a status pill: "<1 min", "2 min", "1 h 5 min". */
export function formatMinutes(totalSeconds: number, lang: Lang): string {
	const minutes = Math.floor(Math.max(0, totalSeconds) / 60);
	if (minutes < 1) return lang === 'fi' ? 'alle 1 min' : '<1 min';
	if (minutes < 60) return `${minutes} min`;
	const hours = Math.floor(minutes / 60);
	const rest = minutes % 60;
	return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

function partsOf(date: Date, lang: Lang, options: Intl.DateTimeFormatOptions): Record<string, string> {
	const parts = new Intl.DateTimeFormat(lang === 'fi' ? 'fi-FI' : 'en-GB', {
		timeZone: TIME_ZONE,
		...options
	}).formatToParts(date);
	return Object.fromEntries(parts.map((p) => [p.type, p.value]));
}

/** "10:04" in Helsinki time. */
export function formatTime(iso: string, lang: Lang): string {
	const p = partsOf(new Date(iso), lang, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
	return `${p.hour}:${p.minute}`;
}

/** "10:02:14" in Helsinki time. */
export function formatTimeSeconds(iso: string, lang: Lang): string {
	const p = partsOf(new Date(iso), lang, {
		hour: '2-digit',
		minute: '2-digit',
		second: '2-digit',
		hourCycle: 'h23'
	});
	return `${p.hour}:${p.minute}:${p.second}`;
}

/** A calendar date (YYYY-MM-DD, no time zone) as "Mon 16 Nov" or "ma 16.11.". */
export function formatDay(isoDate: string, lang: Lang): string {
	const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
	const date = new Date(Date.UTC(y, m - 1, d, 12));
	const weekday = new Intl.DateTimeFormat(lang === 'fi' ? 'fi-FI' : 'en-GB', {
		weekday: 'short',
		timeZone: 'UTC'
	}).format(date);
	if (lang === 'fi') return `${weekday} ${d}.${m}.`;
	const month = new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: 'UTC' }).format(date);
	return `${weekday} ${d} ${month}`;
}

/** The demo clock in the header: "Thu 12 Nov 09:00" (Helsinki time). */
export function formatDemoTime(iso: string, lang: Lang): string {
	const date = new Date(iso);
	if (Number.isNaN(date.getTime())) return '';
	const p = partsOf(date, 'en', { year: 'numeric', month: '2-digit', day: '2-digit' });
	return `${formatDay(`${p.year}-${p.month}-${p.day}`, lang)} ${formatTime(iso, lang)}`;
}

/** The first characters of a hash, for tables. */
export function shortHash(hash: string, length = 6): string {
	return hash.slice(0, length);
}

/** "browser agent" as a sentence start: "Browser agent". */
export function capitalize(text: string): string {
	return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A session's UUID as its first block ("d8144d23"), for a label; other ids as they are. */
export function shortSessionId(id: string): string {
	return /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(id) ? id.slice(0, 8) : id;
}
