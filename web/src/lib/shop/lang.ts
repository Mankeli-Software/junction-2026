/**
 * The webshop's language (#56). One setting, `SHOP_LANG` (src/env.ts), picks the rule:
 * - `auto` (the default): Finnish when the browser's most preferred language in
 *   `Accept-Language` is Finnish (`fi`, `fi-FI`, ...), English for anything else;
 * - `fi` or `en`: always that language.
 * The EN/FI toggle (`?lang=fi` or `?lang=en`) overrides the setting for that page.
 */
import type { Lang } from '#lib/demo/types.js';

export type ShopLangSetting = 'auto' | Lang;

export function shopLang(setting: ShopLangSetting, param: string | null, acceptLanguage: string | null): Lang {
	if (param === 'fi' || param === 'en') return param;
	if (setting !== 'auto') return setting;
	return preferredLanguage(acceptLanguage)?.startsWith('fi') ? 'fi' : 'en';
}

/** The language tag with the highest `q` (the first one on a tie), lower case. */
export function preferredLanguage(header: string | null): string | null {
	let best: { tag: string; q: number } | null = null;
	for (const part of (header ?? '').split(',')) {
		const [rawTag, ...params] = part.trim().split(';');
		const tag = rawTag.trim().toLowerCase();
		if (!tag || tag === '*') continue;
		const qParam = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
		const q = qParam ? Number(qParam.slice(2)) : 1;
		if (!Number.isFinite(q) || q <= 0) continue;
		if (!best || q > best.q) best = { tag, q };
	}
	return best?.tag ?? null;
}
