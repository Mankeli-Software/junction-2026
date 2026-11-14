/**
 * Turns the contract's structured fields into the short texts the page shows:
 * what the buyer asked, "2 cases = 24 l", unit prices and flag titles.
 */
import { date, money, number } from './format';
import { t } from './i18n';
import type { Lang, QuoteLine, Text, ViewFlag } from './types';

const UNIT_LABELS: Record<string, Text> = {
	l: { en: 'l', fi: 'l' },
	kg: { en: 'kg', fi: 'kg' },
	piece: { en: 'pcs', fi: 'kpl' }
};

/** The unit the buyer asked in, as a word. */
export function askedUnit(line: QuoteLine, lang: Lang): string {
	const { unit, package_word } = line.asked;
	if (unit === 'sales_unit') return line.sales_unit_label[lang];
	if (unit === 'package') return package_word ?? line.sales_unit_label[lang];
	return UNIT_LABELS[unit][lang];
}

/** "5 kg ground beef by Monday", or built from the amount when the buyer's words are missing. */
export function askedText(line: QuoteLine, lang: Lang): string {
	if (line.asked.text) return line.asked.text;
	return t(lang, 'askedFallback', {
		amount: `${number(line.asked.quantity, lang)} ${askedUnit(line, lang)}`,
		product: line.name[lang],
		date: date(line.asked.needed_by, lang)
	});
}

/** "2 cases = 24 l", or "3 pcs" when the buyer asked in sales units. */
export function quantityText(line: QuoteLine, lang: Lang): string {
	const sales = `${line.quantity_sales_units} ${line.sales_unit_label[lang]}`;
	if (line.asked.unit === 'sales_unit') return sales;
	return `${sales} = ${number(line.quantity_in_asked_unit, lang)} ${askedUnit(line, lang)}`;
}

/** "20,95 € / pcs, 8,38 € / kg incl. VAT" */
export function unitPriceText(line: QuoteLine, lang: Lang): string {
	const parts = [`${money(Math.round(line.unit_price_gross * 100))} / ${line.sales_unit_label[lang]}`];
	if (line.price_per_base_unit !== null && line.base_unit) {
		parts.push(`${money(Math.round(line.price_per_base_unit * 100))} / ${line.base_unit}`);
	}
	return `${parts.join(', ')} ${t(lang, 'inclVat')}`;
}

const FLAG_TITLES: Record<string, Text> = {
	ALLERGEN_NO_LISTING: { en: 'No allergen info listed', fi: 'Allergiatietoja ei ole' },
	AVAILABILITY_UNVERIFIED: { en: 'Stock not confirmed', fi: 'Saatavuutta ei vahvistettu' },
	STOCK_UNVERIFIED: { en: 'Stock not confirmed', fi: 'Saatavuutta ei vahvistettu' },
	PACK_SIZE_FROM_NAME: { en: 'Pack size read from the name', fi: 'Pakkauskoko luettu nimestä' },
	ROUNDED_UP: { en: 'Rounded up', fi: 'Pyöristetty ylöspäin' },
	SUBSTITUTED_PACK_SIZE: { en: 'Other pack size', fi: 'Toinen pakkauskoko' },
	SUBSTITUTED_CURATED: { en: 'Substitute', fi: 'Korvaava tuote' },
	QUANTITY_UNUSUAL: { en: 'Unusual amount', fi: 'Poikkeava määrä' },
	DUPLICATE_ORDER: { en: 'Possible duplicate', fi: 'Mahdollinen tuplatilaus' },
	FIRST_TIME_PRODUCT: { en: 'New product for you', fi: 'Uusi tuote teille' }
};

/** Short title for a flag code; the engine's sentence goes under it. */
export function codeTitle(code: string, lang: Lang): string {
	return FLAG_TITLES[code]?.[lang] ?? t(lang, 'checkThis');
}

/** "Rounded up 20 l → 24 l" when the flag is about one line, else the code's title. */
export function flagTitle(flag: ViewFlag, lines: QuoteLine[], lang: Lang): string {
	const title = codeTitle(flag.code, lang);
	if (flag.code !== 'ROUNDED_UP' || flag.line_ids.length !== 1) return title;
	const line = lines.find((l) => l.line_id === flag.line_ids[0]);
	if (!line || line.asked.unit === 'sales_unit') return title;
	const unit = askedUnit(line, lang);
	return `${title} ${number(line.asked.quantity, lang)} ${unit} → ${number(line.quantity_in_asked_unit, lang)} ${unit}`;
}
