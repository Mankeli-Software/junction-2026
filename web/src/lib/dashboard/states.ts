/** Session states, channels and exclusions in words (`docs/specs/dashboard.md` §4). */
import { formatClock, formatMinutes, formatTime, secondsSince } from './format';
import { t } from './i18n';
import { CHANNELS, type Channel, type Exclusion, type Lang, type OrderCard, type OverviewFilter, type SessionState, type StateGroup } from './types';

const GROUPS: Record<SessionState, StateGroup | null> = {
	in_conversation: 'active',
	needs_clarification: 'active',
	quote_ready: 'active',
	awaiting_confirmation: 'waiting',
	link_opened: 'waiting',
	confirmed: 'confirmed',
	expired: 'attention',
	rejected: 'attention',
	sms_failed: 'attention',
	callback_requested: 'attention',
	requote_needed: 'attention',
	cancelled: null,
	abandoned: null
};

export function stateGroup(state: SessionState): StateGroup | null {
	return GROUPS[state] ?? null;
}

export type Tone = 'active' | 'waiting' | 'confirmed' | 'attention' | 'ended';

export function stateTone(state: SessionState): Tone {
	return stateGroup(state) ?? 'ended';
}

export function isAttention(state: SessionState): boolean {
	return stateGroup(state) === 'attention';
}

export function isActive(state: SessionState): boolean {
	return stateGroup(state) === 'active';
}

const LABELS: Record<SessionState, { en: string; fi: string }> = {
	in_conversation: { en: 'Building quote', fi: 'Tarjous tekeillä' },
	needs_clarification: { en: 'Asking the buyer', fi: 'Kysyy ostajalta' },
	quote_ready: { en: 'Quote ready', fi: 'Tarjous valmis' },
	awaiting_confirmation: { en: 'Waiting', fi: 'Odottaa' },
	link_opened: { en: 'Buyer looking', fi: 'Ostaja katsoo' },
	confirmed: { en: 'Confirmed', fi: 'Vahvistettu' },
	cancelled: { en: 'Cancelled', fi: 'Peruttu' },
	expired: { en: 'Expired', fi: 'Vanhentunut' },
	rejected: { en: 'Rejected', fi: 'Hylätty' },
	sms_failed: { en: 'SMS failed', fi: 'SMS epäonnistui' },
	callback_requested: { en: 'Callback requested', fi: 'Soittopyyntö' },
	requote_needed: { en: 'New quote needed', fi: 'Uusi tarjous tarvitaan' },
	abandoned: { en: 'Ended, no order', fi: 'Päättyi ilman tilausta' }
};

/**
 * The status pill text with time in state, as on screen 30:
 * "In call, 1:12" (phone, ticking), "Waiting, 2 min", "Confirmed 09:12", "SMS failed".
 */
export function statusText(
	card: Pick<OrderCard, 'state' | 'state_since' | 'channel'>,
	lang: Lang,
	now: number
): string {
	const elapsed = secondsSince(card.state_since, now);
	switch (card.state) {
		case 'in_conversation':
			if (card.channel === 'phone') return `${lang === 'fi' ? 'Puhelu' : 'In call'}, ${formatClock(elapsed)}`;
			return LABELS.in_conversation[lang];
		case 'awaiting_confirmation':
		case 'link_opened':
			return `${LABELS[card.state][lang]}, ${formatMinutes(elapsed, lang)}`;
		case 'confirmed':
		case 'cancelled':
			return `${LABELS[card.state][lang]} ${formatTime(card.state_since, lang)}`;
		default:
			return LABELS[card.state]?.[lang] ?? card.state;
	}
}

/** The plain state word, without time ("Confirmed"). */
export function stateLabel(state: SessionState, lang: Lang): string {
	return LABELS[state]?.[lang] ?? state;
}

export function channelName(channel: Channel, lang: Lang): string {
	return t(`ch_${channel}`, lang);
}

/** A connector's own name ("Claude", "MCP Inspector"), or null when it gave none. */
export function connectorName(client: string): string | null {
	// The API says "MCP client" when the connector gave no name.
	return client && client !== 'mcp' && client !== 'MCP client' ? client : null;
}

/** The badge on a card: "Phone", "Webshop chat", "WebMCP", "Claude connector". */
export function channelBadge(channel: Channel, client: string, lang: Lang): string {
	if (channel === 'mcp') {
		const name = connectorName(client) ?? 'MCP';
		return lang === 'fi' ? `${name}${t('connector', lang)}` : `${name} ${t('connector', lang)}`;
	}
	return channelName(channel, lang);
}

/** The card's note for a connector session, naming the connector when it gave a name. */
export function connectorNote(client: string, lang: Lang): string {
	const name = connectorName(client);
	return name ? t('connector_note_named', lang).replace('{client}', name) : t('connector_note', lang);
}

const EXCLUSION_WORDS: Record<Exclusion, { en: string; fi: string }> = {
	milk_free: { en: 'milk', fi: 'maito' },
	lactose_free: { en: 'lactose', fi: 'laktoosi' },
	gluten_free: { en: 'gluten', fi: 'gluteeni' },
	nut_free: { en: 'nuts', fi: 'pähkinät' },
	egg_free: { en: 'eggs', fi: 'kananmuna' },
	fish_free: { en: 'fish', fi: 'kala' },
	vegan: { en: 'animal products', fi: 'eläintuotteet' }
};

function joinWords(words: string[], lang: Lang): string {
	if (words.length <= 1) return words.join('');
	const and = lang === 'fi' ? 'ja' : 'and';
	return `${words.slice(0, -1).join(', ')} ${and} ${words[words.length - 1]}`;
}

/** "milk and nuts" / "maito ja pähkinät". */
export function exclusionWords(exclusions: readonly Exclusion[], lang: Lang): string {
	return joinWords(
		exclusions.map((e) => EXCLUSION_WORDS[e]?.[lang] ?? e),
		lang
	);
}

/** "Avoids milk and nuts", or "No restrictions". */
export function exclusionsSentence(exclusions: readonly Exclusion[], lang: Lang): string {
	if (exclusions.length === 0) return t('no_restrictions', lang);
	return `${t('avoids', lang)} ${exclusionWords(exclusions, lang)}`;
}

/** "Milk, nuts" for the summary tile. */
export function exclusionsShort(exclusions: readonly Exclusion[], lang: Lang): string {
	if (exclusions.length === 0) return t('nothing', lang);
	const words = exclusions.map((e) => EXCLUSION_WORDS[e]?.[lang] ?? e);
	const text = words.join(', ');
	return text.charAt(0).toUpperCase() + text.slice(1);
}

const STATE_GROUPS: readonly StateGroup[] = ['active', 'waiting', 'confirmed', 'attention'];

/** `?state=&channel=` from the page URL; unknown values are ignored. */
export function parseFilter(params: URLSearchParams): OverviewFilter {
	const state = params.get('state');
	const channel = params.get('channel');
	return {
		state: STATE_GROUPS.includes(state as StateGroup) ? (state as StateGroup) : null,
		channel: CHANNELS.includes(channel as Channel) ? (channel as Channel) : null
	};
}

export function matchesFilter(card: OrderCard, filter: OverviewFilter): boolean {
	if (filter.state && stateGroup(card.state) !== filter.state) return false;
	if (filter.channel && card.channel !== filter.channel) return false;
	return true;
}
