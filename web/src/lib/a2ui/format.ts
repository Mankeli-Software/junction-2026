/** Numbers for the chat cards: decimal comma in both languages, like the prices. */
export { date, money } from '#lib/confirmation/format.js';

export function amount(value: number | string | null | undefined): string {
	if (value === null || value === undefined || value === '') return '';
	const n = typeof value === 'string' ? Number(value) : value;
	return Number.isFinite(n) ? new Intl.NumberFormat('fi-FI', { maximumFractionDigits: 2 }).format(n) : '';
}

/** "1,5" or "1.5" to 1.5; empty to null; anything else to undefined (invalid). */
export function parseAmount(text: string): number | null | undefined {
	const clean = text.trim().replace(/\s/g, '').replace(',', '.');
	if (clean === '') return null;
	if (!/^\d*\.?\d+$/.test(clean)) return undefined;
	const n = Number(clean);
	return Number.isFinite(n) && n > 0 && n <= 100000 ? n : undefined;
}

/** Amount as written, scaled from the recipe's servings to the buyer's portions. */
export function scaled(value: number | null, servings: number | null, portions: number): number | null {
	if (value === null || !servings) return value;
	return Math.round(((value * portions) / servings) * 100) / 100;
}

/** "600 g", "2,5 dl", or just the unit or amount when the other is missing. */
export function measure(value: number | null | undefined, unit: string | null | undefined): string {
	return `${amount(value)} ${unit ?? ''}`.trim();
}

/** Only http(s) and same-origin image paths go into `src`. */
export function safeImage(url: string | null | undefined): string | null {
	if (!url) return null;
	if (url.startsWith('/') && !url.startsWith('//')) return url;
	try {
		const parsed = new URL(url);
		return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.href : null;
	} catch {
		return null;
	}
}
