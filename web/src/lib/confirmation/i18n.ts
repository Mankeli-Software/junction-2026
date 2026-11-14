/**
 * The confirmation page's own labels in both languages. Texts about the order
 * itself (flags, reasons, product names) come from the engine as `Text`.
 * Design rules: the agent is always written S.I.MO, no middle-dot character.
 */
import type { Channel, Lang, Text } from './types';

const strings = {
	yourOrder: { en: 'Your order', fi: 'Tilauksesi' },
	language: { en: 'Language', fi: 'Kieli' },
	delivery: { en: 'Delivery', fi: 'Toimitus' },
	totalInclVat: { en: 'Total incl. VAT', fi: 'Yhteensä sis. alv' },
	validUntil: { en: 'Valid until {time}', fi: 'Voimassa klo {time} asti' },
	exclusions: { en: 'Your kitchen', fi: 'Keittiösi' },
	checkFirst: { en: 'Check these first', fi: 'Tarkista ensin' },
	doneCount: { en: '{done} of {total} done', fi: '{done}/{total} tarkistettu' },
	gotIt: { en: 'Got it', fi: 'Selvä' },
	checked: { en: 'Checked', fi: 'Tarkistettu' },
	newFlag: { en: 'New', fi: 'Uusi' },
	askedAdded: { en: 'You asked, we added', fi: 'Pyysit, lisäsimme' },
	youAsked: { en: 'You asked: {asked}', fi: 'Pyysit: {asked}' },
	askedFallback: { en: '{amount} {product} by {date}', fi: '{amount} {product}, {date} mennessä' },
	checkThis: { en: 'Check this', fi: 'Tarkista tämä' },
	groupLabel: { en: 'For {group}', fi: 'Reseptiin {group}' },
	traceFound: { en: 'products found', fi: 'tuotetta löytyi' },
	traceLeft: { en: 'left after these checks', fi: 'jäi jäljelle' },
	tracePicked: { en: 'We picked by: {rule}', fi: 'Valintaperuste: {rule}' },
	inYourOrder: { en: 'In your order', fi: 'Tilauksessasi' },
	altText: { en: '{quantity} for {total}', fi: '{quantity} hintaan {total}' },
	why: { en: 'Why', fi: 'Miksi' },
	whyLabel: { en: 'Why this product', fi: 'Miksi tämä tuote' },
	changeLine: { en: 'Change this line', fi: 'Muuta riviä' },
	flagsCount: { en: '{n} flags', fi: '{n} huomiota' },
	notOrdered: { en: 'Not ordered: {items}', fi: 'Ei tilattu: {items}' },
	changed: { en: 'Changed', fi: 'Muuttui' },
	totalChanged: { en: 'Total {from} → {to}', fi: 'Yhteensä {from} → {to}' },
	checksLeftOne: { en: '1 check left before you can confirm', fi: '1 tarkistus jäljellä ennen vahvistusta' },
	checksLeft: { en: '{n} checks left before you can confirm', fi: '{n} tarkistusta jäljellä ennen vahvistusta' },
	nothingUntilConfirm: { en: 'Nothing is ordered until you confirm.', fi: 'Mitään ei tilata ennen kuin vahvistat.' },
	inclVat: { en: 'incl. VAT', fi: 'sis. alv' },
	confirm: { en: 'Confirm {total}', fi: 'Vahvista {total}' },
	cancelOrder: { en: 'Cancel order', fi: 'Peru tilaus' },
	cancelCheck: { en: 'Cancel this order? Nothing will be ordered.', fi: 'Perutaanko tilaus? Mitään ei tilata.' },
	cancelYes: { en: 'Yes, cancel', fi: 'Kyllä, peru' },
	cancelNo: { en: 'Keep the order', fi: 'Pidä tilaus' },
	updating: { en: 'Checking your change...', fi: 'Tarkistetaan muutosta...' },
	nothingLeft: { en: 'There is nothing left in this order.', fi: 'Tilauksessa ei ole enää mitään.' },
	whyThisOne: { en: 'Why this one', fi: 'Miksi tämä' },
	otherOptions: { en: 'Other options', fi: 'Muut vaihtoehdot' },
	changeAmount: { en: 'Change amount', fi: 'Muuta määrää' },
	anyChange: {
		en: 'Any change makes a new quote. The total updates on the page.',
		fi: 'Jokainen muutos tekee uuden tarjouksen. Summa päivittyy sivulle.'
	},
	less: { en: 'Less', fi: 'Vähemmän' },
	more: { en: 'More', fi: 'Enemmän' },
	removeLine: { en: 'Remove from order', fi: 'Poista tilauksesta' },
	close: { en: 'Close', fi: 'Sulje' },
	orderReceived: { en: 'Order received', fi: 'Tilaus vastaanotettu' },
	orderConfirmedAt: { en: 'Order {number}, confirmed {time}', fi: 'Tilaus {number}, vahvistettu klo {time}' },
	youCheckedOne: { en: 'You checked 1 flagged item before confirming.', fi: 'Tarkistit 1 merkityn kohdan ennen vahvistusta.' },
	youChecked: { en: 'You checked {n} flagged items before confirming.', fi: 'Tarkistit {n} merkittyä kohtaa ennen vahvistusta.' },
	demoNoteLead: { en: 'This is a demo.', fi: 'Tämä on demo.' },
	demoNote: {
		en: 'No real order was sent. You can reopen this link until the end of the event.',
		fi: 'Oikeaa tilausta ei lähetetty. Voit avata linkin uudelleen tapahtuman loppuun asti.'
	},
	cancelledTitle: { en: 'Order cancelled', fi: 'Tilaus peruttu' },
	cancelledText: {
		en: 'Nothing was ordered. You can start a new order with S.I.MO.',
		fi: 'Mitään ei tilattu. Voit aloittaa uuden tilauksen S.I.MOn kanssa.'
	},
	expiredTitle: { en: 'Quote expired', fi: 'Tarjous vanheni' },
	expiredText: {
		en: 'This quote expired at {time}. Nothing was ordered. Ask S.I.MO for a new quote.',
		fi: 'Tarjous vanheni klo {time}. Mitään ei tilattu. Pyydä S.I.MOlta uusi tarjous.'
	},
	invalidTitle: { en: 'This link is not valid.', fi: 'Tämä linkki ei ole voimassa.' },
	errorGeneric: { en: 'Something went wrong. Try again.', fi: 'Jotain meni pieleen. Yritä uudelleen.' },
	errorStale: {
		en: 'The order changed. This is the latest version.',
		fi: 'Tilaus muuttui. Tämä on uusin versio.'
	},
	channel_phone: { en: 'call at {time}', fi: 'puhelu klo {time}' },
	channel_web_chat: { en: 'chat at {time}', fi: 'chat klo {time}' },
	channel_webmcp: { en: 'webshop at {time}', fi: 'verkkokauppa klo {time}' },
	channel_mcp: { en: 'your agent at {time}', fi: 'agentti klo {time}' }
} satisfies Record<string, Text>;

export type StringKey = keyof typeof strings;

export function t(lang: Lang, key: StringKey, vars: Record<string, string | number> = {}): string {
	return strings[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ''));
}

export function channelText(lang: Lang, channel: Channel, time: string): string {
	return t(lang, `channel_${channel}`, { time });
}
