/** Language helpers: every server text is `{fi, en}`, picked in one place. */
import type { Lang, Localized } from './types';

export const LANG_STORAGE_KEY = 'simo.dashboard.lang';

export function isLang(value: unknown): value is Lang {
	return value === 'fi' || value === 'en';
}

/** `?lang=fi` wins, then the stored choice, then English. */
export function resolveLang(queryLang: string | null | undefined, storedLang: string | null | undefined): Lang {
	if (isLang(queryLang)) return queryLang;
	if (isLang(storedLang)) return storedLang;
	return 'en';
}

/** Pick one language from a server text. Falls back to the other language if one is empty. */
export function pick(text: Localized | null | undefined, lang: Lang): string {
	if (!text) return '';
	const other: Lang = lang === 'fi' ? 'en' : 'fi';
	return text[lang] || text[other] || '';
}

export function readStoredLang(): string | null {
	try {
		return localStorage.getItem(LANG_STORAGE_KEY);
	} catch {
		return null;
	}
}

export function storeLang(lang: Lang): void {
	try {
		localStorage.setItem(LANG_STORAGE_KEY, lang);
	} catch {
		// Private windows and blocked storage: the choice just isn't remembered.
	}
}

const STRINGS = {
	live_dashboard: { en: 'Live dashboard', fi: 'Live-näkymä' },
	live: { en: 'Live', fi: 'Live' },
	reconnecting: { en: 'Reconnecting', fi: 'Yhdistetään' },
	demo_time: { en: 'Demo time', fi: 'Demoaika' },
	overview_title: { en: 'Agent orders, live', fi: 'Agenttien tilaukset, live' },
	overview_lead: {
		en: 'Every order an AI agent prepares, from every channel. One engine decides, a person confirms.',
		fi: 'Jokainen tilaus, jonka tekoälyagentti valmistelee, jokaisesta kanavasta. Yksi moottori päättää, ihminen vahvistaa.'
	},
	active_now: { en: 'Active now', fi: 'Käynnissä nyt' },
	waiting_for_confirmation: { en: 'Waiting for confirmation', fi: 'Odottaa vahvistusta' },
	confirmed: { en: 'Confirmed', fi: 'Vahvistettu' },
	needs_attention: { en: 'Needs attention', fi: 'Vaatii huomiota' },
	confirmed_value: { en: 'Confirmed value, incl. VAT', fi: 'Vahvistettu arvo, sis. ALV' },
	ch_phone: { en: 'Phone', fi: 'Puhelin' },
	ch_phone_sub: { en: 'S.I.MO voice agent', fi: 'S.I.MO-puheagentti' },
	ch_web_chat: { en: 'Webshop chat', fi: 'Verkkokaupan chat' },
	ch_web_chat_sub: { en: 'S.I.MO in the webshop', fi: 'S.I.MO verkkokaupassa' },
	ch_webmcp: { en: 'WebMCP', fi: 'WebMCP' },
	ch_webmcp_sub: { en: 'Outside browser agents', fi: 'Ulkopuoliset selainagentit' },
	ch_mcp: { en: 'MCP connectors', fi: 'MCP-liittimet' },
	ch_mcp_sub: { en: 'Claude, OpenAI', fi: 'Claude, OpenAI' },
	connector: { en: 'connector', fi: '-liitin' },
	filter_all: { en: 'All', fi: 'Kaikki' },
	filter_active: { en: 'Active', fi: 'Käynnissä' },
	filter_waiting: { en: 'Waiting', fi: 'Odottaa' },
	filter_confirmed: { en: 'Confirmed', fi: 'Vahvistettu' },
	filter_attention: { en: 'Needs attention', fi: 'Vaatii huomiota' },
	no_orders: { en: 'No orders here yet.', fi: 'Ei vielä tilauksia.' },
	no_restrictions: { en: 'No restrictions', fi: 'Ei rajoituksia' },
	avoids: { en: 'Avoids', fi: 'Välttää' },
	webshop_session: { en: 'webshop session', fi: 'verkkokauppaistunto' },
	line: { en: 'line', fi: 'rivi' },
	lines: { en: 'lines', fi: 'riviä' },
	lines_so_far: { en: 'so far', fi: 'tähän mennessä' },
	recipes: { en: 'recipes', fi: 'reseptiä' },
	flag: { en: 'flag', fi: 'huomio' },
	flags: { en: 'flags', fi: 'huomiota' },
	connector_note: {
		en: "Conversation stays in the buyer's Claude. Tool calls shown.",
		fi: 'Keskustelu jää ostajan Claudeen. Työkalukutsut näytetään.'
	},
	all_orders: { en: 'All orders', fi: 'Kaikki tilaukset' },
	order: { en: 'Order', fi: 'Tilaus' },
	session: { en: 'Session', fi: 'Istunto' },
	tab_summary: { en: 'Summary', fi: 'Yhteenveto' },
	tab_flow: { en: 'Full flow', fi: 'Koko kulku' },
	tab_audit: { en: 'Audit log', fi: 'Lokikirja' },
	delivery: { en: 'Delivery', fi: 'Toimitus' },
	total_incl_vat: { en: 'Total incl. VAT', fi: 'Yhteensä sis. ALV' },
	channel: { en: 'Channel', fi: 'Kanava' },
	kitchen_avoids: { en: 'Kitchen avoids', fi: 'Keittiö välttää' },
	nothing: { en: 'Nothing', fi: 'Ei mitään' },
	ordered_and_why: { en: 'What was ordered, and why', fi: 'Mitä tilattiin ja miksi' },
	nothing_ordered_yet: { en: 'Nothing added to the order yet.', fi: 'Tilaukseen ei ole vielä lisätty mitään.' },
	asked: { en: 'Asked', fi: 'Pyydetty' },
	why: { en: 'Why', fi: 'Miksi' },
	found_left: { en: '{found} found, {left} left', fi: '{found} löytyi, {left} jäljellä' },
	safe_left: { en: 'safe, in stock, on time', fi: 'sopivia, varastossa, ajallaan' },
	rank: { en: '#', fi: '#' },
	product: { en: 'Product', fi: 'Tuote' },
	per: { en: 'Per', fi: 'Hinta /' },
	stock: { en: 'Stock', fi: 'Saldo' },
	chosen: { en: 'Chosen', fi: 'Valittu' },
	in_stock: { en: 'In stock', fi: 'Varastossa' },
	not_confirmed: { en: 'Not confirmed', fi: 'Ei vahvistettu' },
	unavailable: { en: 'Unavailable', fi: 'Ei saatavilla' },
	rounded_up_from: { en: 'rounded up from {asked}', fi: 'pyöristetty ylös määrästä {asked}' },
	not_ordered: { en: 'Not ordered', fi: 'Ei tilattu' },
	flags_checked: { en: 'Flags the buyer checked', fi: 'Ostajan tarkistamat huomiot' },
	no_flags: { en: 'No flags on this quote.', fi: 'Tarjouksessa ei ole huomioita.' },
	not_acknowledged: { en: 'Not yet', fi: 'Ei vielä' },
	can_we_trust: { en: 'Can we trust it?', fi: 'Voiko tähän luottaa?' },
	sig_valid: { en: 'Quote signed and verified', fi: 'Tarjous allekirjoitettu ja tarkistettu' },
	sig_invalid: { en: 'Quote signature does not match', fi: 'Tarjouksen allekirjoitus ei täsmää' },
	sig_unknown: { en: 'Quote signature not checked yet', fi: 'Tarjouksen allekirjoitusta ei ole vielä tarkistettu' },
	chain_intact_n: { en: 'Audit chain intact, {n} events', fi: 'Lokiketju eheä, {n} tapahtumaa' },
	chain_broken_at: { en: 'Audit chain broken at event #{n}', fi: 'Lokiketju katkeaa tapahtumassa #{n}' },
	chain_checking: { en: 'Checking the audit chain', fi: 'Tarkistetaan lokiketjua' },
	quote_no_edits: { en: 'Quote v{v}, no edits. See full flow', fi: 'Tarjous v{v}, ei muutoksia. Katso koko kulku' },
	quote_edited: { en: 'Quote v{v}, earlier versions voided. See full flow', fi: 'Tarjous v{v}, aiemmat versiot mitätöity. Katso koko kulku' },
	no_quote: { en: 'No quote yet. See full flow', fi: 'Ei vielä tarjousta. Katso koko kulku' },
	flow_title: { en: 'Everything that happened', fi: 'Kaikki mitä tapahtui' },
	prompt: { en: 'prompt', fi: 'kehote' },
	everything: { en: 'Everything', fi: 'Kaikki' },
	conversation: { en: 'Conversation', fi: 'Keskustelu' },
	agent_and_engine: { en: 'Agent and engine', fi: 'Agentti ja moottori' },
	legend_buyer: { en: 'Buyer', fi: 'Ostaja' },
	legend_agent: { en: 'Agent', fi: 'Agentti' },
	legend_tool: { en: 'Tool call', fi: 'Työkalukutsu' },
	legend_engine: { en: 'Engine', fi: 'Moottori' },
	legend_confirmation: { en: 'Confirmation', fi: 'Vahvistus' },
	buyer_transcript: { en: 'Buyer (transcript)', fi: 'Ostaja (litterointi)' },
	agent_transcript: { en: 'Agent (transcript)', fi: 'Agentti (litterointi)' },
	buyer_said: { en: 'Buyer', fi: 'Ostaja' },
	agent_said: { en: 'Agent', fi: 'Agentti' },
	engine_prefix: { en: 'Engine:', fi: 'Moottori:' },
	show_details: { en: 'Show details', fi: 'Näytä tiedot' },
	hide_details: { en: 'Hide details', fi: 'Piilota tiedot' },
	arguments: { en: 'Arguments', fi: 'Argumentit' },
	response_to_agent: { en: 'Response to agent', fi: 'Vastaus agentille' },
	no_response_yet: { en: 'No response yet', fi: 'Ei vielä vastausta' },
	tool_returned: { en: 'Returned', fi: 'Vastasi' },
	show_more_steps: { en: 'Show {n} more steps', fi: 'Näytä {n} vaihetta lisää' },
	connector_flow_note: {
		en: "Conversation happens in the buyer's own {client} client and is not visible to us. Tool calls shown below.",
		fi: 'Keskustelu käydään ostajan omassa {client}-sovelluksessa, eikä se näy meille. Työkalukutsut näkyvät alla.'
	},
	no_steps: { en: 'No steps yet.', fi: 'Ei vielä vaiheita.' },
	audit_title: { en: 'The raw record', fi: 'Raakaloki' },
	chain_intact: { en: 'Chain intact', fi: 'Ketju eheä' },
	chain_broken: { en: 'Chain broken at event #{n}', fi: 'Ketju katkeaa tapahtumassa #{n}' },
	recomputed: {
		en: '{n} events recomputed in your browser just now.',
		fi: '{n} tapahtumaa laskettiin juuri uudelleen selaimessasi.'
	},
	recomputed_broken: {
		en: 'Recomputed in your browser: event #{n} does not match ({reason}).',
		fi: 'Laskettu selaimessasi: tapahtuma #{n} ei täsmää ({reason}).'
	},
	reason_hash: { en: 'its hash differs', fi: 'tiiviste eroaa' },
	reason_payload_hash: { en: 'its content differs', fi: 'sisältö eroaa' },
	reason_seq_gap: { en: 'an event before it is missing', fi: 'sitä edeltävä tapahtuma puuttuu' },
	reason_prev_hash: { en: 'it does not link to the event before it', fi: 'se ei linkity edelliseen tapahtumaan' },
	reason_session_prev_hash: {
		en: 'it does not link to the previous event of this order',
		fi: 'se ei linkity tilauksen edelliseen tapahtumaan'
	},
	sig_valid_short: { en: 'Quote signature valid.', fi: 'Tarjouksen allekirjoitus kunnossa.' },
	sig_invalid_short: { en: 'Quote signature invalid.', fi: 'Tarjouksen allekirjoitus ei kelpaa.' },
	sig_unknown_short: { en: 'Quote signature not checked yet.', fi: 'Tarjouksen allekirjoitusta ei vielä tarkistettu.' },
	verify_again: { en: 'Verify again', fi: 'Tarkista uudelleen' },
	download_json: { en: 'Download JSON', fi: 'Lataa JSON' },
	col_time: { en: 'Time', fi: 'Aika' },
	col_type: { en: 'Type', fi: 'Tyyppi' },
	col_what: { en: 'What happened', fi: 'Mitä tapahtui' },
	col_hash: { en: 'Hash', fi: 'Tiiviste' },
	show_events: { en: 'Show events {from} to {to}', fi: 'Näytä tapahtumat {from}–{to}' },
	event_n: { en: 'Event {n}', fi: 'Tapahtuma {n}' },
	show_in_flow: { en: 'Show in full flow', fi: 'Näytä koko kulussa' },
	identity: { en: 'Identity', fi: 'Tunniste' },
	previous: { en: 'Previous', fi: 'Edellinen' },
	session_previous: { en: 'Previous in order', fi: 'Edellinen tilauksessa' },
	payload_hash: { en: 'Payload hash', fi: 'Sisällön tiiviste' },
	read_only: {
		en: 'Read-only. Nothing here can be changed from the dashboard.',
		fi: 'Vain luku. Tässä näkymässä mitään ei voi muuttaa.'
	},
	pick_event: { en: 'Pick an event to see its full record.', fi: 'Valitse tapahtuma nähdäksesi koko tietueen.' },
	record_not_loaded: { en: 'Full record not available.', fi: 'Koko tietuetta ei ole saatavilla.' },
	not_found_title: { en: 'Order not found', fi: 'Tilausta ei löytynyt' },
	not_found_text: {
		en: 'There is no order with this id. It may be from an earlier event.',
		fi: 'Tällä tunnisteella ei ole tilausta. Se voi olla aiemmasta tapahtumasta.'
	},
	back_to_all: { en: 'Back to all orders', fi: 'Takaisin kaikkiin tilauksiin' },
	error_title: { en: 'Something went wrong', fi: 'Jokin meni vikaan' },
	error_text: {
		en: 'The dashboard could not load this page. It retries when you reload.',
		fi: 'Näkymää ei voitu ladata. Lataa sivu uudelleen.'
	}
} as const satisfies Record<string, Localized>;

export type StringKey = keyof typeof STRINGS;

/** A UI string, with `{name}` placeholders filled from `vars`. */
export function t(key: StringKey, lang: Lang, vars?: Record<string, string | number>): string {
	let text: string = STRINGS[key][lang];
	if (vars) {
		for (const [name, value] of Object.entries(vars)) text = text.replaceAll(`{${name}}`, String(value));
	}
	return text;
}
