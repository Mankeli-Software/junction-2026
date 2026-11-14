/** Turns a quote into what the QuoteCard shows (design UI-05). Every text and number is the engine's. */
import { askedText, askedUnit } from '#lib/confirmation/display.js';
import { number } from '#lib/confirmation/format.js';
import { str } from './resolve';
import type { SurfaceStore } from './surfaces.svelte';
import type { Lang, Quote, QuoteLine } from './types';

export interface QuoteSection {
	/** `photo`: a recipe photo group; `group`: any other named group (a recipe from our data); `other`: the rest. */
	kind: 'photo' | 'group' | 'other';
	group: string | null;
	draftId: string | null;
	/** The recipe's image for the group header, from the API; null draws no image. */
	imageUrl: string | null;
	subtotalCents: number;
	lines: QuoteLine[];
}

/** Lines per group in the quote's order, then the lines without a group as "Other lines". */
export function quoteSections(quote: Quote): QuoteSection[] {
	const byId = new Map(quote.lines.map((l) => [l.line_id, l]));
	const used = new Set<string>();
	const sections: QuoteSection[] = [];
	for (const g of quote.groups) {
		const lines = g.line_ids.map((id) => byId.get(id)).filter((l): l is QuoteLine => Boolean(l));
		lines.forEach((l) => used.add(l.line_id));
		sections.push({
			kind: g.source === 'photo' ? 'photo' : 'group',
			group: g.group,
			draftId: g.recipe_draft_id ?? null,
			imageUrl: g.image_url ?? null,
			subtotalCents: g.subtotal_cents,
			lines
		});
	}
	const rest = quote.lines.filter((l) => !used.has(l.line_id));
	if (rest.length) {
		sections.push({
			kind: 'other',
			group: null,
			draftId: null,
			imageUrl: null,
			subtotalCents: rest.reduce((sum, l) => sum + l.line_total_cents, 0),
			lines: rest
		});
	}
	return sections;
}

/** "maitoa 6 l" for a recipe line, the buyer's own words otherwise. */
export function askedLabel(line: QuoteLine, lang: Lang): string {
	if (line.asked.text && line.group) {
		return `${line.asked.text} ${number(line.asked.quantity, lang)} ${askedUnit(line, lang)}`.trim();
	}
	return askedText(line, lang);
}

/** "Valio kevytmaito 1 l, 6 cartons". */
export function productLabel(line: QuoteLine, lang: Lang): string {
	return `${line.name[lang]}, ${line.quantity_sales_units} ${line.sales_unit_label[lang]}`;
}

/** Flag codes that point at this line, once each. */
export function lineFlagCodes(quote: Quote, lineId: string): string[] {
	return [...new Set(quote.flags.filter((f) => f.line_ids.includes(lineId)).map((f) => f.code))];
}

/**
 * The surface of a later QuoteCard with another quote id that loaded, when this one
 * has been followed by a newer quote in the chat. Null while this card is the latest.
 * QuoteCard marks `${componentId}#loaded` with its quote id once its quote is in.
 */
export function newerQuoteSurface(
	store: SurfaceStore,
	surfaceId: string,
	componentId: string,
	quoteId: string,
	/** Surfaces left out, such as the panel's Current order drawer. */
	skip: (surfaceId: string) => boolean = () => false
): string | null {
	let seen = false;
	let newer: string | null = null;
	for (const sid of store.order) {
		const surface = store.surfaces[sid];
		if (!surface?.supported || (sid !== surfaceId && skip(sid))) continue;
		for (const [cid, c] of Object.entries(surface.components)) {
			if (c.component !== 'QuoteCard') continue;
			if (sid === surfaceId && cid === componentId) {
				seen = true;
				continue;
			}
			if (!seen) continue;
			const other = str(surface, c.quoteId, 80);
			// Only a card that loaded its quote counts, so a wrong id never hides a good card.
			if (!other || store.actedOn(sid, `${cid}#loaded`) !== other) continue;
			newer = other !== quoteId ? sid : null;
		}
	}
	return newer;
}
