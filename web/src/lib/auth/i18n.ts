/**
 * Labels for the connector login pages (/login, /signup, /connect; #48), in English and
 * Finnish. Design rules: the agent is always written S.I.MO, no middle-dot character,
 * masked numbers with stars, no "DEMO" labels.
 */
import type { Lang, Text } from '../demo/types';

const strings = {
	loginTitle: { en: 'Log in', fi: 'Kirjaudu' },
	loginText: {
		en: 'Log in to let your own AI assistant order with S.I.MO for your kitchen.',
		fi: 'Kirjaudu, niin oma tekoälyavustajasi voi tilata S.I.MOn kautta keittiöllesi.'
	},
	signupTitle: { en: 'Create an account', fi: 'Luo tunnus' },
	signupText: {
		en: 'Connect Claude or ChatGPT to S.I.MO. Every order still waits for your yes by SMS.',
		fi: 'Yhdistä Claude tai ChatGPT S.I.MOon. Jokainen tilaus odottaa silti kyllääsi tekstiviestillä.'
	},
	email: { en: 'Email', fi: 'Sähköposti' },
	password: { en: 'Password', fi: 'Salasana' },
	passwordHint: { en: 'At least 10 characters.', fi: 'Vähintään 10 merkkiä.' },
	phoneLabel: { en: 'Your real phone number', fi: 'Oikea puhelinnumerosi' },
	phoneHint: {
		en: 'The order link comes here. Your company is picked by this number.',
		fi: 'Tilauslinkki tulee tähän. Yrityksesi valitaan tämän numeron mukaan.'
	},
	countryCode: { en: 'Country code', fi: 'Maatunnus' },
	phoneInvalid: {
		en: 'Check the number. Type it with the area code, for example 40 123 4512.',
		fi: 'Tarkista numero. Kirjoita se suuntanumeron kanssa, esimerkiksi 40 123 4512.'
	},
	emailInvalid: { en: 'Check the email address.', fi: 'Tarkista sähköpostiosoite.' },
	passwordShort: { en: 'Use at least 10 characters.', fi: 'Käytä vähintään 10 merkkiä.' },
	logIn: { en: 'Log in', fi: 'Kirjaudu' },
	loggingIn: { en: 'Logging in', fi: 'Kirjaudutaan' },
	createAccount: { en: 'Create account', fi: 'Luo tunnus' },
	creating: { en: 'Creating', fi: 'Luodaan' },
	noAccount: { en: 'No account yet?', fi: 'Eikö sinulla ole tunnusta?' },
	signUpLink: { en: 'Create one', fi: 'Luo tunnus' },
	haveAccount: { en: 'Have an account already?', fi: 'Onko sinulla jo tunnus?' },
	logInLink: { en: 'Log in', fi: 'Kirjaudu' },
	wrongLogin: { en: 'Wrong email or password.', fi: 'Väärä sähköposti tai salasana.' },
	tooMany: {
		en: 'Too many tries. Wait a few minutes and try again.',
		fi: 'Liian monta yritystä. Odota muutama minuutti ja yritä uudelleen.'
	},
	emailTaken: {
		en: "This email can't be used to sign up. Try logging in instead.",
		fi: 'Tällä sähköpostilla ei voi luoda tunnusta. Kokeile kirjautua.'
	},
	failed: { en: 'Something went wrong. Try again.', fi: 'Jokin meni vikaan. Yritä uudelleen.' },

	phoneStepTitle: { en: 'One more thing', fi: 'Vielä yksi asia' },
	phoneStepText: {
		en: 'Your account has no phone number yet. S.I.MO sends the order link to it, so you can say yes.',
		fi: 'Tunnuksellasi ei ole vielä puhelinnumeroa. S.I.MO lähettää tilauslinkin siihen, jotta voit hyväksyä tilauksen.'
	},
	phoneStepSave: { en: 'Save and continue', fi: 'Tallenna ja jatka' },
	saving: { en: 'Saving', fi: 'Tallennetaan' },

	connectTitle: { en: 'Connect your assistant', fi: 'Yhdistä avustajasi' },
	connectQuestion: {
		en: 'Allow {client} to order for {company}?',
		fi: 'Saako {client} tilata yritykselle {company}?'
	},
	connectText: {
		en: '{client} can search products, build quotes and ask for your confirmation. Nothing is ordered until you confirm the SMS link sent to {phone}.',
		fi: '{client} voi hakea tuotteita, koota tarjouksia ja pyytää vahvistustasi. Mitään ei tilata ennen kuin vahvistat numeroon {phone} lähetetyn linkin.'
	},
	connectRedirect: { en: 'You go back to {host} after this.', fi: 'Palaat tämän jälkeen osoitteeseen {host}.' },
	allow: { en: 'Allow', fi: 'Salli' },
	cancel: { en: 'Cancel', fi: 'Peruuta' },
	connectLoading: { en: 'Checking the request', fi: 'Tarkistetaan pyyntöä' },
	connectGone: {
		en: 'This sign-in request has expired. Start again from your assistant.',
		fi: 'Tämä kirjautumispyyntö on vanhentunut. Aloita alusta avustajassasi.'
	},
	noRealOrder: {
		en: 'Junction 2026 demo: no real order is placed.',
		fi: 'Junction 2026 -demo: oikeaa tilausta ei tehdä.'
	}
} satisfies Record<string, Text>;

export type AuthStringKey = keyof typeof strings;

export function at(lang: Lang, key: AuthStringKey, vars: Record<string, string | number> = {}): string {
	return strings[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ''));
}
