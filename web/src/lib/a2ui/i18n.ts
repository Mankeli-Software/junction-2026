/**
 * The chat cards' own labels. Texts about the order come from the engine.
 * Design rules: the agent is always written S.I.MO, no middle-dot character,
 * masked numbers with stars.
 */
import type { Lang, Weekday } from './types';

const strings = {
	// Card states (UI-02)
	loading: { en: 'Loading', fi: 'Ladataan' },
	loadFailed: { en: 'This could not be loaded.', fi: 'Tätä ei voitu ladata.' },
	notFound: { en: 'S.I.MO could not find this. Ask again in the chat.', fi: 'S.I.MO ei löytänyt tätä. Kysy uudelleen keskustelussa.' },
	tryAgain: { en: 'Try again', fi: 'Yritä uudelleen' },
	actionFailed: { en: 'That did not go through. Try again.', fi: 'Se ei onnistunut. Yritä uudelleen.' },
	unsupported: { en: 'S.I.MO sent something this page cannot show.', fi: 'S.I.MO lähetti jotain, mitä tämä sivu ei osaa näyttää.' },

	// RecipeDraftCard (UI-03, Chat-A2, Chat-A3)
	recipeIRead: { en: 'Recipe I read', fi: 'Lukemani resepti' },
	fromNotebook: { en: 'From your recipe photo', fi: 'Reseptikuvastasi' },
	fromDish: { en: 'From your dish photo', fi: 'Ruokakuvastasi' },
	guessBanner: {
		en: 'This is a guess from the picture. Check it before ordering.',
		fi: 'Tämä on arvaus kuvan perusteella. Tarkista se ennen tilaamista.'
	},
	whichRecipe: { en: 'Which recipe', fi: 'Mikä resepti' },
	ourRecipe: { en: 'Our recipe', fi: 'Reseptimme' },
	aiSaw: { en: 'What the AI saw', fi: 'Mitä tekoäly näki' },
	dish: { en: 'Dish', fi: 'Ruoka' },
	portions: { en: 'Portions', fi: 'Annokset' },
	fewerPortions: { en: 'Fewer portions', fi: 'Vähemmän annoksia' },
	morePortions: { en: 'More portions', fi: 'Enemmän annoksia' },
	sourceMakes: {
		en: 'The recipe makes {n}. Amounts are scaled to {portions}.',
		fi: 'Resepti on {n} annokselle. Määrät on skaalattu {portions} annokselle.'
	},
	sourceUnknown: {
		en: 'The photo does not say how many it makes, so amounts are taken as written.',
		fi: 'Kuvassa ei kerrota annosmäärää, joten määrät otetaan sellaisinaan.'
	},
	ingredients: { en: 'Ingredients', fi: 'Ainekset' },
	ingredientsFor: { en: 'Ingredients for {n}', fi: 'Ainekset {n} annokselle' },
	linkedOf: { en: '{n} of {total} we can order', fi: '{n}/{total} tilattavissa' },
	ingredient: { en: 'Ingredient', fi: 'Aines' },
	amount: { en: 'Amount', fi: 'Määrä' },
	unit: { en: 'Unit', fi: 'Yksikkö' },
	orderRow: { en: 'Order {name}', fi: 'Tilaa {name}' },
	weOrder: { en: 'We order', fi: 'Tilataan' },
	weSearch: { en: 'We search', fi: 'Haetaan' },
	notOrderedTag: { en: 'Not ordered', fi: 'Ei tilata' },
	forPortions: { en: '{amount} for {n}', fi: '{amount} / {n} annosta' },
	checkThis: { en: 'Check this', fi: 'Tarkista' },
	toCheck: { en: '{n} to check', fi: '{n} tarkistettavaa' },
	removeRow: { en: 'Remove {name}', fi: 'Poista {name}' },
	addRow: { en: 'Add ingredient', fi: 'Lisää aines' },
	newIngredient: { en: 'New ingredient', fi: 'Uusi aines' },
	amountInvalid: { en: 'Write a number, or leave it empty', fi: 'Kirjoita numero tai jätä tyhjäksi' },
	ourRecipeNote: {
		en: 'Products linked to the recipe are ordered as they are. We search for the rest when we build the order.',
		fi: 'Reseptiin linkitetyt tuotteet tilataan sellaisinaan. Muille haetaan tuote, kun tilaus tehdään.'
	},
	nothingYet: {
		en: 'Nothing is ordered yet. After you confirm, S.I.MO makes a quote and checks every product against your kitchen.',
		fi: 'Mitään ei ole vielä tilattu. Kun vahvistat, S.I.MO tekee tarjouksen ja tarkistaa jokaisen tuotteen keittiösi tietoja vasten.'
	},
	nothingToOrder: { en: 'Tick at least one ingredient to order.', fi: 'Valitse ainakin yksi tilattava aines.' },
	fixAmounts: { en: 'Fix the amounts marked in red first.', fi: 'Korjaa ensin punaisella merkityt määrät.' },
	confirmRecipe: { en: 'Confirm recipe', fi: 'Vahvista resepti' },
	useThisRecipe: { en: 'Use this recipe', fi: 'Käytä tätä reseptiä' },
	startOver: { en: 'Start over', fi: 'Aloita alusta' },
	confirmedAs: { en: 'Confirmed: {dish}, {n} portions', fi: 'Vahvistettu: {dish}, {n} annosta' },
	discarded: {
		en: 'Recipe discarded. Send a new photo or type what you need.',
		fi: 'Resepti hylätty. Lähetä uusi kuva tai kirjoita, mitä tarvitset.'
	},
	editAsNew: { en: 'Edit as new draft', fi: 'Muokkaa uutena luonnoksena' },
	saveToAimo: { en: 'Save to My Aimo', fi: 'Tallenna Minun Aimoon' },
	savedToAimo: { en: 'Saved to My Aimo', fi: 'Tallennettu Minun Aimoon' },
	dietHintLong: {
		en: 'Diet tags are only a hint. Safety is checked on the actual products when we build the order.',
		fi: 'Ruokavaliomerkinnät ovat vain vihje. Turvallisuus tarkistetaan valituista tuotteista, kun tilaus tehdään.'
	},

	// RecipeCard (UI-04)
	recipeImage: { en: 'Recipe image', fi: 'Reseptin kuva' },
	noImage: { en: 'No recipe image', fi: 'Ei reseptin kuvaa' },
	portionsCount: { en: '{n} portions', fi: '{n} annosta' },
	portionsLinked: {
		en: '{n} portions, {linked} of {total} ingredients we can order',
		fi: '{n} annosta, {linked}/{total} aineksesta tilattavissa'
	},
	andMore: { en: '{names} and {n} more', fi: '{names} ja {n} muuta' },
	useThis: { en: 'Use this', fi: 'Käytä tätä' },
	swap: { en: 'Swap for another', fi: 'Vaihda toiseen' },
	showIngredients: { en: 'Show ingredients', fi: 'Näytä ainekset' },
	hideIngredients: { en: 'Hide ingredients', fi: 'Piilota ainekset' },
	usingThis: { en: 'Using this, {n} portions', fi: 'Käytössä, {n} annosta' },
	swapAsked: { en: 'You asked S.I.MO for another recipe.', fi: 'Pyysit S.I.MO:lta toista reseptiä.' },
	dietHint: {
		en: 'Safety is checked on the actual products when we build the order.',
		fi: 'Turvallisuus tarkistetaan valituista tuotteista, kun tilaus tehdään.'
	},

	// MenuWeek (UI-06)
	weeklyMenu: { en: 'Weekly menu', fi: 'Viikon ruokalista' },
	menuTitle: { en: 'Your week', fi: 'Viikkosi' },
	portionsEach: { en: '{n} portions each', fi: '{n} annosta kukin' },
	linkedShort: { en: '{linked} of {total} we can order', fi: '{linked}/{total} tilattavissa' },
	swapping: { en: 'Asked for another', fi: 'Pyydetty toista' },
	swapDay: { en: 'Swap {day}', fi: 'Vaihda {day}' },
	buildMenu: { en: 'Build order from this menu', fi: 'Tee tilaus tästä listasta' },
	menuBuilt: { en: 'S.I.MO is building the order from this menu.', fi: 'S.I.MO tekee tilauksen tästä listasta.' },
	noDays: { en: 'This menu has no days yet.', fi: 'Tällä listalla ei ole vielä päiviä.' },

	// QuoteCard (UI-05, Chat-A4)
	quoteTitle: { en: 'Your order so far', fi: 'Tilauksesi tähän asti' },
	deliveryVat: { en: 'Delivery {date}, incl. VAT', fi: 'Toimitus {date}, sis. alv' },
	deliveryRangeVat: { en: 'Delivery {from} to {to}, incl. VAT', fi: 'Toimitus {from} – {to}, sis. alv' },
	inclVat: { en: 'Incl. VAT', fi: 'Sis. alv' },
	fromPhotoGroup: { en: 'From your recipe photo: {group}', fi: 'Reseptikuvastasi: {group}' },
	fromPhotoGroupPortions: { en: 'From your recipe photo: {group}, {n} portions', fi: 'Reseptikuvastasi: {group}, {n} annosta' },
	forRecipe: { en: 'For {group}', fi: 'Reseptiin {group}' },
	otherLines: { en: 'Other lines', fi: 'Muut rivit' },
	youAsked: { en: 'You asked: {asked}', fi: 'Pyysit: {asked}' },
	notOrdered: { en: 'Not ordered: {items}', fi: 'Ei tilata: {items}' },
	oneThing: { en: '1 thing to check on your phone', fi: '1 asia tarkistettavana puhelimessa' },
	nThings: { en: '{n} things to check on your phone', fi: '{n} asiaa tarkistettavana puhelimessa' },
	checkOnPhone: {
		en: 'You tick these on the confirmation page before you confirm.',
		fi: 'Kuittaat nämä vahvistussivulla ennen vahvistamista.'
	},
	sendToPhone: { en: 'Send to my phone', fi: 'Lähetä puhelimeeni' },
	question: { en: 'Question', fi: 'Kysymys' },
	cantAdd: { en: 'Can’t add this', fi: 'Tätä ei voi lisätä' },
	nextStep: { en: 'Do this instead', fi: 'Tee näin' },
	replaced: { en: 'This quote was replaced by a newer one below.', fi: 'Uudempi tarjous alempana korvasi tämän.' },
	goLatest: { en: 'Go to the latest', fi: 'Siirry uusimpaan' },
	pendingConfirmation: { en: 'Sent to your phone', fi: 'Lähetetty puhelimeesi' },
	oneLine: { en: '1 line.', fi: '1 rivi.' },
	nLines: { en: '{n} lines.', fi: '{n} riviä.' },
	seeWholeOrder: { en: 'See the whole order', fi: 'Näytä koko tilaus' },
	quoteConfirmed: { en: 'Confirmed on your phone', fi: 'Vahvistettu puhelimessa' },
	quoteCancelled: { en: 'This quote was cancelled.', fi: 'Tämä tarjous peruttiin.' },
	quoteExpired: { en: 'This quote expired. Ask S.I.MO for a new one.', fi: 'Tämä tarjous vanheni. Pyydä S.I.MO:lta uusi.' },
	noLines: { en: 'Nothing could be added yet.', fi: 'Mitään ei voitu vielä lisätä.' },

	// SentNotice (UI-05)
	sentTitle: { en: 'Sent to your demo phone', fi: 'Lähetetty demopuhelimeesi' },
	sentText: {
		en: 'Open it in this browser to confirm. Nothing is ordered yet.',
		fi: 'Avaa se tässä selaimessa ja vahvista. Mitään ei ole vielä tilattu.'
	},
	openPhone: { en: 'Open the demo phone', fi: 'Avaa demopuhelin' },
	alsoSms: { en: 'Also sent by SMS to {number}', fi: 'Lähetetty myös tekstiviestinä numeroon {number}' }
} satisfies Record<string, Record<Lang, string>>;

export type Key = keyof typeof strings;

export function t(lang: Lang, key: Key, vars: Record<string, string | number> = {}): string {
	return strings[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`));
}

const DAYS: Record<Weekday, { short: Record<Lang, string>; long: Record<Lang, string> }> = {
	mon: { short: { en: 'Mon', fi: 'ma' }, long: { en: 'Monday', fi: 'maanantai' } },
	tue: { short: { en: 'Tue', fi: 'ti' }, long: { en: 'Tuesday', fi: 'tiistai' } },
	wed: { short: { en: 'Wed', fi: 'ke' }, long: { en: 'Wednesday', fi: 'keskiviikko' } },
	thu: { short: { en: 'Thu', fi: 'to' }, long: { en: 'Thursday', fi: 'torstai' } },
	fri: { short: { en: 'Fri', fi: 'pe' }, long: { en: 'Friday', fi: 'perjantai' } }
};

export function dayName(day: Weekday, lang: Lang, form: 'short' | 'long' = 'short'): string {
	return DAYS[day]?.[form][lang] ?? day;
}
