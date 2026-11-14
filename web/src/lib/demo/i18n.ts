/**
 * Labels for the demo start page and the phone page, in English and Finnish
 * (docs/specs/call-screen.md §5). Design rules: the agent is always written S.I.MO,
 * no middle-dot character, masked numbers with stars, no "DEMO" labels.
 */
import type { Exclusion, Lang, Text } from './types';

const strings = {
	language: { en: 'Language', fi: 'Kieli' },
	brand: { en: 'S.I.MO', fi: 'S.I.MO' },

	// Start page (00, 01)
	heroTitle: {
		en: 'Give S.I.MO a ring. Your kitchen order sorts itself out.',
		fi: 'Soita S.I.MOlle. Keittiösi tilaus hoituu itsestään.'
	},
	heroText: {
		en: 'S.I.MO listens, picks safe products that arrive on time, and sends the order to your phone. Nothing is ordered until you say yes.',
		fi: 'S.I.MO kuuntelee, valitsee turvalliset tuotteet, jotka ehtivät ajoissa, ja lähettää tilauksen puhelimeesi. Mitään ei tilata ennen kuin sanot kyllä.'
	},
	heroTitlePhone: { en: 'Give S.I.MO a ring', fi: 'Soita S.I.MOlle' },
	heroTextPhone: { en: 'Say what you need. Confirm on your phone.', fi: 'Kerro mitä tarvitset. Vahvista puhelimellasi.' },
	tryIt: { en: 'Try it', fi: 'Kokeile' },
	callSimo: { en: 'Call S.I.MO', fi: 'Soita S.I.MOlle' },
	callSimoText: { en: 'Order by voice and confirm on your own phone.', fi: 'Tilaa puhumalla ja vahvista omalla puhelimellasi.' },
	callSimoShort: { en: 'Order by voice, about 3 minutes', fi: 'Tilaa puhumalla, noin 3 minuuttia' },
	start: { en: 'Start', fi: 'Aloita' },
	scanQr: { en: 'Scan with your phone. It works best there.', fi: 'Skannaa puhelimellasi. Siellä se toimii parhaiten.' },
	qrAlt: { en: 'QR code for the phone page', fi: 'QR-koodi puhelinsivulle' },
	callFromComputer: { en: 'Call from this computer', fi: 'Soita tältä tietokoneelta' },
	dashboardTitle: { en: 'Watch the dashboard', fi: 'Seuraa näkymää' },
	dashboardText: {
		en: 'Every agent order, live. See why each product was chosen, the whole conversation and the audit log.',
		fi: 'Jokainen agentin tilaus livenä. Näet miksi kukin tuote valittiin, koko keskustelun ja lokin.'
	},
	openDashboard: { en: 'Open dashboard', fi: 'Avaa näkymä' },
	dashboardShort: { en: 'Live dashboard', fi: 'Live-näkymä' },
	dashboardShortText: { en: 'Best on a computer. Open it anyway', fi: 'Paras tietokoneella. Avaa silti' },
	webshopTitle: { en: 'Chat in the webshop', fi: 'Chattaa verkkokaupassa' },
	webshopText: {
		en: 'Plan a weekly menu with S.I.MO and turn it into one order.',
		fi: 'Suunnittele viikon ruokalista S.I.MOn kanssa ja tee siitä yksi tilaus.'
	},
	openWebshop: { en: 'Open webshop', fi: 'Avaa verkkokauppa' },
	webshopShort: { en: 'Webshop chat', fi: 'Verkkokaupan chat' },
	webshopShortText: { en: 'Plan a weekly menu', fi: 'Suunnittele viikon ruokalista' },
	ownAgentTitle: { en: 'Bring your own agent', fi: 'Tuo oma agenttisi' },
	ownAgentText: {
		en: 'Our ordering engine is an open MCP server. Connect your own AI and order with the same rules, the same flags and the same confirmation link.',
		fi: 'Tilausmoottorimme on avoin MCP-palvelin. Yhdistä oma tekoälysi ja tilaa samoilla säännöillä, samoilla huomioilla ja samalla vahvistuslinkillä.'
	},
	ownAgentShort: { en: 'Use your own agent', fi: 'Käytä omaa agenttia' },
	ownAgentShortText: { en: 'Claude, ChatGPT, any MCP client', fi: 'Claude, ChatGPT, mikä tahansa MCP-asiakas' },
	mcpAddress: { en: 'MCP server address', fi: 'MCP-palvelimen osoite' },
	copyAddress: { en: 'Copy address', fi: 'Kopioi osoite' },
	copied: { en: 'Copied', fi: 'Kopioitu' },
	wayClaude: {
		en: 'Add the address as a custom connector, then sign in with your demo email.',
		fi: 'Lisää osoite omaksi yhdistimeksi ja kirjaudu demosähköpostillasi.'
	},
	wayOpenAi: {
		en: 'Open the webshop page in an agent browser. The tools are there through WebMCP.',
		fi: 'Avaa verkkokaupan sivu agenttiselaimessa. Työkalut löytyvät sieltä WebMCP:n kautta.'
	},
	wayAny: { en: 'Streamable HTTP at the address above.', fi: 'Streamable HTTP yllä olevassa osoitteessa.' },
	wayDevelopers: { en: 'Developers', fi: 'Kehittäjät' },
	wayDocs: { en: 'Tool list and OpenAPI docs', fi: 'Työkalulista ja OpenAPI-dokumentaatio' },
	wayAnyLabel: { en: 'Any MCP client', fi: 'Mikä tahansa MCP-asiakas' },
	wayOpenAiLabel: { en: 'ChatGPT and OpenAI', fi: 'ChatGPT ja OpenAI' },
	howItWorks: { en: 'How it works', fi: 'Näin se toimii' },
	step1: { en: '<b>You ask</b> by phone, chat or your own agent', fi: '<b>Kysyt</b> puhelimella, chatissa tai omalla agentillasi' },
	step2: { en: '<b>The agent prepares</b> the order lines', fi: '<b>Agentti valmistelee</b> tilausrivit' },
	step3: { en: '<b>The engine decides</b> products, safety, price', fi: '<b>Moottori päättää</b> tuotteet, turvallisuuden ja hinnan' },
	step4: { en: '<b>You confirm</b> with the link on your phone', fi: '<b>Vahvistat</b> puhelimeesi tulevalla linkillä' },
	footLead: { en: 'A demo for Junction 2026.', fi: 'Demo Junction 2026 -tapahtumaan.' },
	footText: {
		en: 'Products and prices come from the challenge data. No real orders are placed.',
		fi: 'Tuotteet ja hinnat tulevat haasteen datasta. Oikeita tilauksia ei tehdä.'
	},
	footLeadPhone: { en: 'Junction 2026 demo.', fi: 'Junction 2026 -demo.' },
	footTextPhone: { en: 'No real orders are placed.', fi: 'Oikeita tilauksia ei tehdä.' },

	// Phone on a computer (14)
	backToStart: { en: 'Back to the demo start', fi: 'Takaisin demon alkuun' },
	bestOnPhone: { en: 'This works best on your phone', fi: 'Tämä toimii parhaiten puhelimella' },
	bestOnPhoneText: {
		en: "Scan the code to call S.I.MO from your own phone, or use the phone here with your computer's microphone.",
		fi: 'Skannaa koodi ja soita S.I.MOlle omalla puhelimellasi, tai käytä tätä puhelinta tietokoneen mikrofonilla.'
	},
	onComputer: { en: 'On a computer', fi: 'Tietokoneella' },
	onComputerText1: {
		en: 'The phone keeps its phone size, so every screen looks the same as on a real phone.',
		fi: 'Puhelin pysyy puhelimen kokoisena, joten jokainen näkymä näyttää samalta kuin oikeassa puhelimessa.'
	},
	onComputerText2: {
		en: "The confirmation link arrives in this phone's messages.",
		fi: 'Vahvistuslinkki tulee tämän puhelimen viesteihin.'
	},

	// Set up (10)
	setupTitle: { en: 'Your demo phone', fi: 'Demopuhelimesi' },
	setupText: {
		en: 'This page becomes a phone. Give S.I.MO a ring and order what your kitchen needs.',
		fi: 'Tästä sivusta tulee puhelin. Soita S.I.MOlle ja tilaa mitä keittiösi tarvitsee.'
	},
	phoneLabel: { en: 'Your real phone number', fi: 'Oikea puhelinnumerosi' },
	countryCode: { en: 'Country code', fi: 'Maatunnus' },
	phoneHint: { en: 'The order link comes to this demo phone.', fi: 'Tilauslinkki tulee tähän demopuhelimeen.' },
	phoneInvalid: {
		en: 'Check the number. Type it with the area code, for example 40 123 4512.',
		fi: 'Tarkista numero. Kirjoita se suuntanumeron kanssa, esimerkiksi 40 123 4512.'
	},
	kitchenAvoids: { en: 'Your kitchen avoids', fi: 'Keittiösi välttää' },
	nothing: { en: 'Nothing', fi: 'Ei mitään' },
	noticeDashboard: {
		en: 'Your order and what you say show on our public demo dashboard under a made-up company name. Your number is never shown in full.',
		fi: 'Tilauksesi ja se mitä sanot näkyvät julkisessa demonäkymässämme keksityllä yritysnimellä. Numeroasi ei koskaan näytetä kokonaan.'
	},
	noticeInbox: {
		en: 'The link to confirm your order arrives in the demo phone on this page. This is a demo; no real order is placed.',
		fi: 'Linkki tilauksen vahvistamiseen tulee tämän sivun demopuhelimeen. Tämä on demo; oikeaa tilausta ei tehdä.'
	},
	openDemoPhone: { en: 'Open demo phone', fi: 'Avaa demopuhelin' },
	opening: { en: 'Opening...', fi: 'Avataan...' },
	limitReached: {
		en: 'This number has reached the demo limit. Ask us at the booth.',
		fi: 'Tämä numero on saavuttanut demon rajan. Kysy meiltä osastolla.'
	},
	setupFailed: { en: 'Could not open the demo phone. Try again.', fi: 'Demopuhelimen avaus ei onnistunut. Yritä uudelleen.' },

	// Contacts (11)
	contacts: { en: 'Contacts', fi: 'Yhteystiedot' },
	search: { en: 'Search', fi: 'Hae' },
	simoTagline: { en: 'Tell me what your kitchen needs. I will sort it out.', fi: 'Kerro mitä keittiösi tarvitsee. Minä hoidan sen.' },
	call: { en: 'Call', fi: 'Soita' },
	callAria: { en: 'Call S.I.MO', fi: 'Soita S.I.MOlle' },
	trySaying: { en: 'Try saying', fi: 'Kokeile sanoa' },
	try1: { en: '"I need 1,000 litres of lactose-free milk by Monday."', fi: '"Tarvitsen 1 000 litraa laktoositonta maitoa maanantaiksi."' },
	try2: { en: '"We ran out of ground beef, 5 kilos for tomorrow."', fi: '"Jauheliha loppui, 5 kiloa huomiseksi."' },
	try3: { en: '"My usual butter, 20 kilos."', fi: '"Tavallinen voi, 20 kiloa."' },
	try4: { en: '"A recipe for 200 people, milk-free."', fi: '"Resepti 200 hengelle, maidoton."' },
	kitchen: { en: 'Kitchen', fi: 'Keittiö' },
	avoids: { en: 'Avoids {list}', fi: 'Välttää: {list}' },
	avoidsNothing: { en: 'No restrictions', fi: 'Ei rajoituksia' },
	change: { en: 'Change', fi: 'Muuta' },
	changeKitchen: { en: 'Change kitchen', fi: 'Muuta keittiötä' },
	usualOrder: { en: 'Usual order', fi: 'Tavallinen tilaus' },
	noUsual: { en: 'Nothing yet', fi: 'Ei vielä mitään' },
	tabMessages: { en: 'Messages', fi: 'Viestit' },
	tabRecents: { en: 'Recents', fi: 'Viimeisimmät' },
	tabContacts: { en: 'Contacts', fi: 'Yhteystiedot' },
	tabKeypad: { en: 'Keypad', fi: 'Näppäimistö' },
	unread: { en: '{n} new', fi: '{n} uutta' },
	and: { en: 'and', fi: 'ja' },

	// In call (12)
	onSpeaker: { en: 'On speaker', fi: 'Kaiutin päällä' },
	speakerOff: { en: 'Speaker off', fi: 'Kaiutin pois' },
	connecting: { en: 'Connecting...', fi: 'Yhdistetään...' },
	speaking: { en: 'Speaking', fi: 'Puhuu' },
	listening: { en: 'Listening', fi: 'Kuuntelee' },
	liveCaptions: { en: 'Live captions, automatic', fi: 'Livetekstitys, automaattinen' },
	captionsHint: {
		en: 'Captions are made automatically and can be wrong. If S.I.MO heard you wrong, just say it again.',
		fi: 'Tekstitys tehdään automaattisesti ja voi olla väärin. Jos S.I.MO kuuli väärin, sano se uudelleen.'
	},
	captionsOff: { en: 'Captions are off.', fi: 'Tekstitys on pois päältä.' },
	you: { en: 'You', fi: 'Sinä' },
	youListening: { en: 'Listening...', fi: 'Kuunnellaan...' },
	mute: { en: 'Mute', fi: 'Mykistä' },
	muted: { en: 'Muted', fi: 'Mykistetty' },
	speaker: { en: 'Speaker', fi: 'Kaiutin' },
	captions: { en: 'Captions', fi: 'Tekstitys' },
	hangUp: { en: 'Hang up', fi: 'Lopeta puhelu' },

	// Call ended (13)
	callEnded: { en: 'Call ended, {time}', fi: 'Puhelu päättyi, {time}' },
	callDropped: { en: 'The call dropped, {time}', fi: 'Puhelu katkesi, {time}' },
	notifTitle: { en: 'Confirm your order, {total}', fi: 'Vahvista tilauksesi, {total}' },
	notifTitlePlain: { en: 'Confirm your order', fi: 'Vahvista tilauksesi' },
	notifTap: { en: 'Tap to check it', fi: 'Napauta ja tarkista' },
	now: { en: 'now', fi: 'nyt' },
	nothingOrderedYet: { en: 'Nothing is ordered yet', fi: 'Mitään ei ole vielä tilattu' },
	endStep1: { en: 'Tap the notification', fi: 'Napauta ilmoitusta' },
	endStep2: { en: 'Check what S.I.MO flagged', fi: 'Tarkista mitä S.I.MO merkitsi' },
	endStep3: { en: 'Confirm', fi: 'Vahvista' },
	waitingForLink: { en: 'The link is on its way to your messages.', fi: 'Linkki on tulossa viesteihisi.' },
	smsSent: { en: 'Also sent by SMS to {number}', fi: 'Lähetetty myös tekstiviestinä numeroon {number}' },
	smsFailed: { en: 'The SMS did not arrive, use the message above.', fi: 'Tekstiviesti ei mennyt perille, käytä yllä olevaa viestiä.' },
	noOrder: { en: 'No order was made on this call.', fi: 'Tässä puhelussa ei tehty tilausta.' },
	callAgain: { en: 'Call again', fi: 'Soita uudelleen' },
	callAgainAria: { en: 'Call S.I.MO again', fi: 'Soita S.I.MOlle uudelleen' },
	openMessages: { en: 'Open messages', fi: 'Avaa viestit' },

	// Messages (inbox)
	messages: { en: 'Messages', fi: 'Viestit' },
	back: { en: 'Back', fi: 'Takaisin' },
	noMessages: {
		en: 'No messages yet. The link to confirm your order comes here after the call.',
		fi: 'Ei vielä viestejä. Linkki tilauksen vahvistamiseen tulee tänne puhelun jälkeen.'
	},
	messagesNote: {
		en: 'Only this browser sees these messages.',
		fi: 'Vain tämä selain näkee nämä viestit.'
	},

	// Errors (spec §3)
	micDenied: { en: 'We need the microphone for the call.', fi: 'Tarvitsemme mikrofonin puhelua varten.' },
	micDeniedHelp: {
		en: 'Allow the microphone for this page: tap the lock or the settings icon next to the address, then allow Microphone, and try again.',
		fi: 'Salli mikrofoni tälle sivulle: napauta osoitteen vieressä olevaa lukkoa tai asetuksia, salli mikrofoni ja yritä uudelleen.'
	},
	unsupported: {
		en: 'This browser cannot make the call. Try Chrome or Safari on your phone.',
		fi: 'Tällä selaimella ei voi soittaa. Kokeile Chromea tai Safaria puhelimellasi.'
	},
	cannotConnect: { en: 'Could not connect. Try again.', fi: 'Yhteyttä ei saatu. Yritä uudelleen.' },
	sessionLost: {
		en: 'Your demo phone was reset. Type your number again.',
		fi: 'Demopuhelimesi nollautui. Kirjoita numerosi uudelleen.'
	},
	tryAgain: { en: 'Try again', fi: 'Yritä uudelleen' },
	setUpAgain: { en: 'Set up again', fi: 'Aloita alusta' }
} satisfies Record<string, Text>;

export type StringKey = keyof typeof strings;

export function t(lang: Lang, key: StringKey, vars: Record<string, string | number> = {}): string {
	return strings[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ''));
}

/** Short chip names for "Your kitchen avoids" (design 10). `vegan` has no single food to name. */
const exclusionShort: Record<Exclusion, Text> = {
	milk_free: { en: 'Milk', fi: 'Maito' },
	lactose_free: { en: 'Lactose', fi: 'Laktoosi' },
	gluten_free: { en: 'Gluten', fi: 'Gluteeni' },
	nut_free: { en: 'Nuts', fi: 'Pähkinät' },
	egg_free: { en: 'Egg', fi: 'Kananmuna' },
	fish_free: { en: 'Fish', fi: 'Kala' },
	vegan: { en: 'Animal products', fi: 'Eläintuotteet' }
};

export function exclusionLabel(lang: Lang, exclusion: Exclusion): string {
	return exclusionShort[exclusion][lang];
}

/** "Avoids milk and nuts" for the Kitchen row on Contacts (design 11). */
export function avoidsText(lang: Lang, exclusions: readonly Exclusion[]): string {
	if (exclusions.length === 0) return t(lang, 'avoidsNothing');
	const names = exclusions.map((e) => exclusionLabel(lang, e).toLowerCase());
	return t(lang, 'avoids', { list: joinList(lang, names) });
}

export function joinList(lang: Lang, items: string[]): string {
	if (items.length <= 1) return items.join('');
	return `${items.slice(0, -1).join(', ')} ${t(lang, 'and')} ${items[items.length - 1]}`;
}

/** "2:14": minutes and seconds, for the call timer and "Call ended, 2:14". */
export function duration(seconds: number): string {
	const s = Math.max(0, Math.floor(seconds));
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** "128,40 €" in both languages, like the confirmation page. */
const moneyFormat = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' });
export function money(cents: number): string {
	return moneyFormat.format(cents / 100);
}

export function langParam(value: string | null): Lang {
	return value === 'fi' ? 'fi' : 'en';
}
