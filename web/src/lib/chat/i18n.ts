/**
 * The chat panel's own labels (#57, docs/specs/webshop-chat.md). The cards inside
 * the chat have theirs in #lib/a2ui/i18n. Design rules: the agent is always written
 * S.I.MO, no middle-dot character, masked numbers with stars, no "DEMO" labels.
 */
import type { Lang } from '#lib/demo/types.js';

const strings = {
	open: { en: 'Ask S.I.MO', fi: 'Kysy S.I.MOlta' },
	openLabel: { en: 'Open the S.I.MO chat', fi: 'Avaa S.I.MO-chat' },
	panelLabel: { en: 'S.I.MO chat', fi: 'S.I.MO-chat' },
	close: { en: 'Close chat', fi: 'Sulje chat' },
	noExclusions: { en: 'No exclusions', fi: 'Ei rajoituksia' },
	avoids: { en: 'Avoids {list}', fi: 'Välttää: {list}' },

	whoTitle: { en: 'Who is ordering?', fi: 'Kuka tilaa?' },
	whoText: {
		en: 'Type your phone number, as on the demo phone. The same number gets the same kitchen.',
		fi: 'Kirjoita puhelinnumerosi kuten demopuhelimessa. Sama numero saa saman keittiön.'
	},
	noticeDashboard: {
		en: 'Your order and what you write show on our public demo dashboard under a made-up company name.',
		fi: 'Tilauksesi ja kirjoittamasi näkyvät julkisessa demonäkymässämme keksityllä yritysnimellä.'
	},
	phoneHint: {
		en: 'The order link goes to the demo phone in this browser.',
		fi: 'Tilauslinkki tulee tämän selaimen demopuhelimeen.'
	},
	continue: { en: 'Start chatting', fi: 'Aloita chat' },
	continuing: { en: 'Just a moment...', fi: 'Hetki...' },
	noticeInbox: {
		en: 'The link to confirm your order arrives in the demo phone in this browser, never in this chat. No real order is placed.',
		fi: 'Linkki tilauksen vahvistamiseen tulee tämän selaimen demopuhelimeen, ei koskaan tähän chattiin. Oikeaa tilausta ei tehdä.'
	},

	greeting: {
		en: 'Hi, I am S.I.MO, an AI helper. Tell me what your kitchen needs, or send me a photo of a recipe.',
		fi: 'Hei, olen S.I.MO, tekoälyavustaja. Kerro mitä keittiösi tarvitsee, tai lähetä minulle kuva reseptistä.'
	},
	examples: { en: 'Try one of these', fi: 'Kokeile näitä' },
	examplePhoto: { en: 'Order from a recipe photo', fi: 'Tilaa reseptikuvasta' },
	example1: { en: '1 000 l lactose-free milk by Monday', fi: '1 000 l laktoositonta maitoa maanantaiksi' },
	example2: {
		en: 'Plan a lunch menu for next week, 80 people',
		fi: 'Suunnittele lounaslista ensi viikolle, 80 henkeä'
	},
	example3: { en: 'My usual order', fi: 'Tavallinen tilaukseni' },

	currentOrder: { en: 'Current order', fi: 'Nykyinen tilaus' },
	showOrder: { en: 'Show the current order', fi: 'Näytä nykyinen tilaus' },

	messageLabel: { en: 'Message S.I.MO', fi: 'Viesti S.I.MOlle' },
	placeholder: { en: 'Write to S.I.MO', fi: 'Kirjoita S.I.MOlle' },
	send: { en: 'Send', fi: 'Lähetä' },
	addPhoto: { en: 'Add a recipe photo', fi: 'Lisää reseptikuva' },
	photoHint: {
		en: 'Photos are read once and not kept. Leave names and numbers out of the picture.',
		fi: 'Kuvat luetaan kerran eikä niitä säilytetä. Jätä nimet ja numerot pois kuvasta.'
	},
	photoAlt: { en: 'Your recipe photo', fi: 'Reseptikuvasi' },
	photoMessage: { en: 'Here is my recipe photo.', fi: 'Tässä on reseptikuvani.' },
	you: { en: 'You', fi: 'Sinä' },

	thinking: { en: 'One moment', fi: 'Hetki' },
	reading: { en: 'Reading your recipe', fi: 'Luen reseptiäsi' },
	building: { en: 'Building your order', fi: 'Teen tilaustasi' },
	recipes: { en: 'Looking for recipes', fi: 'Etsin reseptejä' },
	products: { en: 'Checking products', fi: 'Tarkistan tuotteita' },
	sending: { en: 'Sending it to your phone', fi: 'Lähetän sen puhelimeesi' },
	kitchen: { en: 'Looking up your kitchen', fi: 'Haen keittiösi tiedot' },
	status: { en: 'Checking the order', fi: 'Tarkistan tilausta' },
	working: { en: 'Working on it', fi: 'Työstän' },

	errorNotConfigured: {
		en: 'The chat is not set up right now. You can still order by phone on the demo phone.',
		fi: 'Chattia ei ole juuri nyt otettu käyttöön. Voit silti tilata soittamalla demopuhelimella.'
	},
	errorBusy: {
		en: 'S.I.MO is still answering your last message. Wait a moment and try again.',
		fi: 'S.I.MO vastaa vielä edelliseen viestiisi. Odota hetki ja yritä uudelleen.'
	},
	errorFailed: { en: 'Something went wrong. Try again.', fi: 'Jokin meni vikaan. Yritä uudelleen.' },
	errorNetwork: { en: 'The connection dropped. Try again.', fi: 'Yhteys katkesi. Yritä uudelleen.' },
	errorSignedOut: {
		en: 'Type your phone number first, then write again.',
		fi: 'Kirjoita ensin puhelinnumerosi ja kirjoita sitten uudelleen.'
	},
	read413: {
		en: 'This photo is too large. Try a smaller one, up to 10 MB.',
		fi: 'Kuva on liian suuri. Kokeile pienempää, enintään 10 Mt.'
	},
	read415: {
		en: 'I can only read photos: JPEG, PNG, WebP or HEIC.',
		fi: 'Osaan lukea vain kuvia: JPEG, PNG, WebP tai HEIC.'
	},
	read422: {
		en: 'I could not read this photo. Try a sharper one, in good light, or type the ingredients.',
		fi: 'En saanut kuvasta selvää. Kokeile tarkempaa kuvaa hyvässä valossa tai kirjoita ainekset.'
	},
	read502: {
		en: 'Reading the photo failed. Try again in a moment.',
		fi: 'Kuvan lukeminen epäonnistui. Yritä hetken päästä uudelleen.'
	},
	read503: {
		en: 'Reading photos is not set up right now. Type the ingredients instead.',
		fi: 'Kuvien lukemista ei ole juuri nyt otettu käyttöön. Kirjoita ainekset.'
	},
	read504: {
		en: 'Reading the photo took too long. Try again, or type the ingredients.',
		fi: 'Kuvan lukeminen kesti liian kauan. Yritä uudelleen tai kirjoita ainekset.'
	},
	linkHidden: { en: '(the link is in your demo phone)', fi: '(linkki on demopuhelimessasi)' },

	actionSend: { en: 'Send it to my phone', fi: 'Lähetä se puhelimeeni' },
	actionRecipeConfirmed: { en: 'Recipe confirmed', fi: 'Resepti vahvistettu' },
	actionRecipeDiscarded: { en: 'Start over', fi: 'Aloitetaan alusta' },
	actionRecipeEditAsNew: { en: 'Edit it as a new draft', fi: 'Muokataan uutena luonnoksena' },
	actionRecipeSelected: { en: 'Use this recipe for {n}', fi: 'Käytä tätä reseptiä {n} annokselle' },
	actionRecipeSelectedPlain: { en: 'Use this recipe', fi: 'Käytä tätä reseptiä' },
	actionRecipeSwap: { en: 'Swap this recipe for another', fi: 'Vaihda tämä resepti toiseen' },
	actionClarification: { en: 'This one', fi: 'Tämä' },
	actionMenuSwap: { en: 'Swap {day}', fi: 'Vaihda {day}' },
	actionMenuSwapPlain: { en: 'Swap this day', fi: 'Vaihda tämä päivä' },
	actionMenuBuild: { en: 'Build the order from this menu', fi: 'Tee tilaus tästä listasta' },

	askChanges: { en: 'Ask for changes', fi: 'Pyydä muutoksia' },
	askChangesHint: {
		en: 'Write what to change, for example "Make it 150 portions". You still confirm with the button on this page.',
		fi: 'Kirjoita mitä muutetaan, esimerkiksi "Tee siitä 150 annosta". Vahvistat silti tämän sivun painikkeella.'
	}
} satisfies Record<string, Record<Lang, string>>;

export type ChatKey = keyof typeof strings;

export function t(lang: Lang, key: ChatKey, vars: Record<string, string | number> = {}): string {
	return strings[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ''));
}

const DAYS: Record<string, { en: string; fi: string }> = {
	mon: { en: 'Monday', fi: 'maanantai' },
	tue: { en: 'Tuesday', fi: 'tiistai' },
	wed: { en: 'Wednesday', fi: 'keskiviikko' },
	thu: { en: 'Thursday', fi: 'torstai' },
	fri: { en: 'Friday', fi: 'perjantai' },
	sat: { en: 'Saturday', fi: 'lauantai' },
	sun: { en: 'Sunday', fi: 'sunnuntai' }
};
const DAY_KEYS = Object.keys(DAYS);

/**
 * A menu day as a word: "mon", "Monday", 0 to 6 (Monday first) or an ISO date.
 * Null when it is none of these.
 */
export function dayName(lang: Lang, day: unknown): string | null {
	if (typeof day === 'number' && Number.isInteger(day) && day >= 0 && day < 7) return DAYS[DAY_KEYS[day]][lang];
	if (typeof day !== 'string') return null;
	const key = day.trim().slice(0, 3).toLowerCase();
	if (DAYS[key]) return DAYS[key][lang];
	const date = /^\d{4}-\d{2}-\d{2}$/.test(day) ? new Date(`${day}T12:00:00Z`) : null;
	if (date && !Number.isNaN(date.getTime())) return DAYS[DAY_KEYS[(date.getUTCDay() + 6) % 7]][lang];
	return null;
}
