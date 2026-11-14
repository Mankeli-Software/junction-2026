/** Quantity text for a quote line: "2 pcs = 5 kg, 20,95 € / pcs". */
import { formatNumber, formatUnitPrice } from './format';
import { pick, t } from './i18n';
import type { AskedLine, Lang, SummaryLine } from './types';

export function askedUnitWord(asked: AskedLine, line: SummaryLine, lang: Lang): string {
	switch (asked.unit) {
		case 'l':
		case 'kg':
			return asked.unit;
		case 'piece':
			return lang === 'fi' ? 'kpl' : 'pcs';
		case 'package':
			return asked.package_word ?? pick(line.sales_unit_label, lang);
		default:
			return pick(line.sales_unit_label, lang);
	}
}

/**
 * Sales units, the same amount in the asked unit, then either the unit price or, when one
 * line had to round the asked amount up, "rounded up from 20 l".
 */
export function lineQuantityText(line: SummaryLine, asked: AskedLine, lang: Lang, onlyLine: boolean): string {
	const unit = askedUnitWord(asked, line, lang);
	const salesUnits = `${line.quantity_sales_units} ${pick(line.sales_unit_label, lang)}`;
	const head =
		asked.unit === 'sales_unit'
			? salesUnits
			: `${salesUnits} = ${formatNumber(line.quantity_in_asked_unit, lang)} ${unit}`;
	if (onlyLine && line.quantity_in_asked_unit > asked.quantity) {
		return `${head}, ${t('rounded_up_from', lang, { asked: `${formatNumber(asked.quantity, lang)} ${unit}` })}`;
	}
	return `${head}, ${formatUnitPrice(line.unit_price_gross, lang)} / ${pick(line.sales_unit_label, lang)}`;
}
