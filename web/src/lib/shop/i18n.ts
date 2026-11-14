/**
 * The webshop's labels in English and Finnish (#56). The number entry's own labels
 * come from the phone page (#lib/demo/i18n). Design rules: the agent is always
 * written S.I.MO, no middle-dot character, masked numbers with stars, no "DEMO"
 * labels (the notice that no real order is placed stays).
 */
import type { Lang, Text } from '#lib/demo/types.js';

const strings = {
	shopName: { en: 'Foodservice webshop', fi: 'Ammattikeittiön verkkokauppa' },
	language: { en: 'Language', fi: 'Kieli' },
	categories: { en: 'Categories', fi: 'Tuoteryhmät' },
	all: { en: 'All products', fi: 'Kaikki tuotteet' },
	heroTitle: { en: 'Valio products for professional kitchens', fi: 'Valion tuotteet ammattikeittiöille' },
	heroText: {
		en: 'Order through the AI agent in your browser. This page gives it S.I.MO, our ordering tools: it finds safe products that arrive on time, and the order waits for your yes.',
		fi: 'Tilaa selaimesi tekoälyagentilla. Tämä sivu antaa sille S.I.MOn tilaustyökalut: ne löytävät turvalliset tuotteet, jotka ehtivät ajoissa, ja tilaus odottaa sinun hyväksyntääsi.'
	},
	productsTitle: { en: 'Products', fi: 'Tuotteet' },
	productsNote: {
		en: 'Prices, stock and delivery dates come through the agent.',
		fi: 'Hinnat, saatavuus ja toimituspäivät tulevat agentin kautta.'
	},
	productCount: { en: '{n} products', fi: '{n} tuotetta' },
	byPiece: { en: 'Sold by the piece', fi: 'Myydään kappaleittain' },
	byCase: { en: 'Sold by the case of {n}', fi: 'Myydään {n} kpl laatikoissa' },
	noImage: { en: 'No picture yet', fi: 'Ei vielä kuvaa' },

	whoTitle: { en: 'Who is ordering?', fi: 'Kuka tilaa?' },
	whoText: {
		en: 'Type your phone number, as on the demo phone. The same number gets the same kitchen.',
		fi: 'Kirjoita puhelinnumerosi kuten demopuhelimessa. Sama numero saa saman keittiön.'
	},
	noticeDashboard: {
		en: 'Your order and what your agent does show on our public demo dashboard under a made-up company name. Your number is never shown in full.',
		fi: 'Tilauksesi ja agenttisi toimet näkyvät julkisessa demonäkymässämme keksityllä yritysnimellä. Numeroasi ei koskaan näytetä kokonaan.'
	},
	noticeInbox: {
		en: 'The link to confirm your order arrives in the demo phone in this browser, never on this page. No real order is placed.',
		fi: 'Linkki tilauksen vahvistamiseen tulee tämän selaimen demopuhelimeen, ei koskaan tälle sivulle. Oikeaa tilausta ei tehdä.'
	},
	phoneHint: {
		en: 'The order link goes to the demo phone in this browser.',
		fi: 'Tilauslinkki tulee tämän selaimen demopuhelimeen.'
	},
	continue: { en: 'Continue', fi: 'Jatka' },
	continuing: { en: 'Just a moment...', fi: 'Hetki...' },
	orderingAs: { en: 'Ordering as', fi: 'Tilaaja' },
	changeNumber: { en: 'Change number', fi: 'Vaihda numero' },

	toolsTitle: { en: 'S.I.MO for your browser agent', fi: 'S.I.MO selaimesi agentille' },
	toolsReady: {
		en: '{n} ordering tools are ready for the agent in this browser (WebMCP).',
		fi: '{n} tilaustyökalua on valmiina tämän selaimen agentille (WebMCP).'
	},
	toolsMissing: {
		en: 'This browser has no WebMCP agent. Open the page in Chrome with the MCP-B extension.',
		fi: 'Tässä selaimessa ei ole WebMCP-agenttia. Avaa sivu Chromessa, jossa on MCP-B-laajennus.'
	},
	toolsTry: {
		en: 'Try asking: "Order 20 litres of lactose-free milk for Monday."',
		fi: 'Kokeile pyytää: "Tilaa 20 litraa laktoositonta maitoa maanantaiksi."'
	},
	latestQuote: { en: 'Latest quote from your agent', fi: 'Agenttisi viimeisin tarjous' },
	quoteSummaryOne: { en: '1 line, {total} incl. VAT', fi: '1 rivi, {total} sis. alv' },
	quoteSummary: { en: '{lines} lines, {total} incl. VAT', fi: '{lines} riviä, {total} sis. alv' },
	quoteReady: { en: 'Ready to send for confirmation', fi: 'Valmis lähetettäväksi vahvistettavaksi' },
	quoteQuestion: { en: 'S.I.MO has a question for your agent', fi: 'S.I.MOlla on kysymys agentillesi' },
	quoteRejected: { en: 'Not possible as asked', fi: 'Ei onnistu pyydetyllä tavalla' },
	linkInPhone: { en: 'Your confirmation link is in your demo phone', fi: 'Vahvistuslinkkisi on demopuhelimessasi' },
	linkInPhoneText: {
		en: 'Open the demo phone in this browser, check what S.I.MO flagged and confirm. Nothing is ordered until you do.',
		fi: 'Avaa demopuhelin tässä selaimessa, tarkista mitä S.I.MO merkitsi ja vahvista. Mitään ei tilata ennen sitä.'
	},
	smsAlso: { en: 'Also sent by SMS to {number}.', fi: 'Lähetetty myös tekstiviestinä numeroon {number}.' },
	openPhone: { en: 'Open the demo phone', fi: 'Avaa demopuhelin' },

	footLead: { en: 'A demo for Junction 2026.', fi: 'Demo Junction 2026 -tapahtumaan.' },
	footText: {
		en: 'Products come from the challenge data. Our own page in a webshop style, with no logos. No real orders are placed.',
		fi: 'Tuotteet tulevat haasteen datasta. Oma sivumme verkkokaupan tyyliin, ilman logoja. Oikeita tilauksia ei tehdä.'
	}
} satisfies Record<string, Text>;

export type ShopKey = keyof typeof strings;

export function t(lang: Lang, key: ShopKey, vars: Record<string, string | number> = {}): string {
	return strings[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ''));
}
