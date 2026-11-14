<script lang="ts">
	/**
	 * The demo phone (issue #54; docs/design screens 10 to 14; docs/specs/call-screen.md).
	 * Set up → Contacts with S.I.MO → call → call ended → the notification opens the
	 * message in this phone's inbox, whose link opens the confirmation page.
	 * On a computer the same screens show at phone size inside a phone frame (14).
	 */
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { ApiError, createAccount, getInbox, getMe, watchInbox } from '#lib/demo/api.js';
	import CallFailed from '#lib/demo/components/phone/CallFailed.svelte';
	import ContactsScreen from '#lib/demo/components/phone/ContactsScreen.svelte';
	import EndedScreen from '#lib/demo/components/phone/EndedScreen.svelte';
	import InCallScreen from '#lib/demo/components/phone/InCallScreen.svelte';
	import MessagesScreen from '#lib/demo/components/phone/MessagesScreen.svelte';
	import SetupScreen from '#lib/demo/components/phone/SetupScreen.svelte';
	import { t } from '#lib/demo/i18n.js';
	import { readPhone, writePhone } from '#lib/demo/session.js';
	import type { DemoAccount, InboxMessage, Lang, SetupValues } from '#lib/demo/types.js';
	import { VoiceCall } from '#lib/voice/call.svelte.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const lang = $derived(data.lang);

	type Screen = 'setup' | 'contacts' | 'call' | 'messages';

	let screen = $state<Screen>('setup');
	let ready = $state(false);
	let values = $state<SetupValues>({ countryCode: '+358', number: '', exclusions: [] });
	let account = $state<DemoAccount | null>(null);
	let busy = $state(false);
	let setupError = $state<'limit' | 'failed' | null>(null);

	let call = $state<VoiceCall | null>(null);
	let now = $state(Date.now());

	let messages = $state<InboxMessage[]>([]);
	let seen = $state<string[]>([]);
	let callMessage = $state<InboxMessage | null>(null);
	let highlight = $state<string | null>(null);
	let knownAtCall = new Set<string>();
	let stopInbox: (() => void) | null = null;

	const unread = $derived(messages.filter((m) => !seen.includes(m.id)).length);

	function langHref(option: Lang): string {
		const target = new URL(page.url.href);
		if (option === 'fi') target.searchParams.set('lang', 'fi');
		else target.searchParams.delete('lang');
		return target.pathname + target.search;
	}

	function save() {
		writePhone({ values, account, seen });
	}

	onMount(() => {
		void restore();
		const tick = setInterval(() => (now = Date.now()), 500);
		const leave = () => call?.dispose();
		window.addEventListener('pagehide', leave);
		return () => {
			clearInterval(tick);
			window.removeEventListener('pagehide', leave);
			call?.dispose();
			stopInbox?.();
		};
	});

	/** Back from the confirmation page or a reload: open the phone where it was. */
	async function restore() {
		try {
			const stored = readPhone();
			if (stored.values) values = stored.values;
			if (Array.isArray(stored.seen)) seen = stored.seen;
			if (stored.account) {
				const me = await getMe();
				account = {
					...stored.account,
					user_id: me.user_id,
					company_id: me.company_id,
					company_name: me.company_name,
					phone_masked: me.phone_masked,
					exclusions: me.exclusions
				};
				screen = 'contacts';
				openInbox();
			} else if (page.url.searchParams.has('inbox')) {
				// From the connector login (#48): already signed in, so open the inbox.
				const me = await getMe();
				account = { ...me, usual_items: [], new_company: false, new_user: false };
				screen = 'messages';
				save();
				openInbox();
			}
		} catch {
			account = null; // No session any more: set up again.
		}
		ready = true;
	}

	async function submitSetup(next: SetupValues, e164: string) {
		values = next;
		busy = true;
		setupError = null;
		try {
			account = await createAccount({ phone_e164: e164, exclusions: next.exclusions, lang });
			screen = 'contacts';
			save();
			openInbox();
		} catch (error) {
			setupError = error instanceof ApiError && error.status === 429 ? 'limit' : 'failed';
		} finally {
			busy = false;
		}
	}

	function openInbox() {
		stopInbox?.();
		const add = (message: InboxMessage) => {
			if (messages.some((m) => m.id === message.id)) return;
			messages = [...messages, message];
			if (call && !knownAtCall.has(message.id)) announce(message);
		};
		// Listen first, then read what is already there, so nothing falls in between.
		stopInbox = watchInbox(add, async () => {
			try {
				for (const message of await getInbox()) add(message);
			} catch (error) {
				if (error instanceof ApiError && error.status === 401) sessionLost();
			}
		});
	}

	/** The confirmation message for this call: the banner, and a browser notification if allowed. */
	function announce(message: InboxMessage) {
		callMessage = message;
		if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && document.hidden) {
			const notification = new Notification('S.I.MO', { body: t(lang, 'notifTitlePlain'), tag: message.id });
			notification.onclick = () => {
				window.focus();
				openMessage();
			};
		}
	}

	function sessionLost() {
		stopInbox?.();
		stopInbox = null;
		call?.dispose();
		call = null;
		account = null;
		messages = [];
		screen = 'setup';
		save();
	}

	function startCall() {
		if (call && (call.phase === 'connecting' || call.phase === 'live')) return;
		knownAtCall = new Set(messages.map((m) => m.id));
		callMessage = null;
		call = new VoiceCall();
		screen = 'call';
		void call.start();
	}

	function openMessages() {
		screen = 'messages';
		seen = messages.map((m) => m.id);
		save();
	}

	function openMessage() {
		highlight = callMessage?.id ?? null;
		openMessages();
	}

	function toContacts() {
		highlight = null;
		screen = 'contacts';
	}
</script>

<svelte:head>
	<title>{t(lang, 'setupTitle')}, S.I.MO</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="stage">
	<header class="computer-bar">
		<span class="hd brand">{t(lang, 'brand')}</span>
		<a href="/{lang === 'fi' ? '?lang=fi' : ''}">{t(lang, 'backToStart')}</a>
	</header>

	<div class="layout">
		<aside class="side left">
			<h2 class="hd">{t(lang, 'bestOnPhone')}</h2>
			<p>{t(lang, 'bestOnPhoneText')}</p>
			<div class="qr" role="img" aria-label={t(lang, 'qrAlt')}>{@html data.qr}</div>
		</aside>

		<div class="device">
			<div class="screen">
				{#if !ready}
					<div class="blank"></div>
				{:else if screen === 'setup' || !account}
					<SetupScreen {lang} {langHref} initial={values} {busy} error={setupError} onsubmit={submitSetup} />
				{:else if screen === 'messages'}
					<MessagesScreen {lang} origin={page.url.origin} {messages} {highlight} oncontacts={toContacts} />
				{:else if screen === 'call' && call}
					{#if call.phase === 'connecting' || call.phase === 'live'}
						<InCallScreen {lang} {call} {now} />
					{:else if call.phase === 'failed' && call.error}
						<CallFailed
							{lang}
							error={call.error}
							onretry={startCall}
							onsetup={sessionLost}
							oncontacts={toContacts}
						/>
					{:else}
						<EndedScreen
							{lang}
							{call}
							companyName={account.company_name}
							phoneMasked={account.phone_masked}
							message={callMessage}
							onopen={openMessage}
							oncallagain={startCall}
							oncontacts={toContacts}
						/>
					{/if}
				{:else}
					<ContactsScreen
						{lang}
						{account}
						{unread}
						oncall={startCall}
						onchange={() => (screen = 'setup')}
						onmessages={openMessages}
					/>
				{/if}
			</div>
			<span class="home-bar" aria-hidden="true"></span>
		</div>

		<aside class="side right">
			<b>{t(lang, 'onComputer')}</b>
			<span>{t(lang, 'onComputerText1')}</span>
			<span>{t(lang, 'onComputerText2')}</span>
		</aside>
	</div>
</div>

<style>
	/* On a phone, the page is the phone: full screen, no frame. */
	.stage {
		min-height: 100dvh;
		background: var(--page);
	}
	.computer-bar,
	.side,
	.home-bar {
		display: none;
	}
	.device {
		height: 100dvh;
	}
	.screen {
		height: 100%;
		overflow-y: auto;
		overflow-x: hidden;
		background: #fff;
	}
	.blank {
		height: 100%;
		background: var(--page);
	}

	/* On a computer (14): the same screens at phone size inside a frame. */
	@media (min-width: 960px) {
		.stage {
			height: 100dvh;
			display: flex;
			flex-direction: column;
			background: var(--lavender);
		}
		.computer-bar {
			background: var(--petrol);
			color: #fff;
			height: 56px;
			flex-shrink: 0;
			padding: 0 40px;
			display: flex;
			align-items: center;
			justify-content: space-between;
		}
		.brand {
			font-size: 24px;
			color: #fff;
		}
		.computer-bar a {
			font-size: 15px;
			color: #cfe0e8;
		}
		.layout {
			flex-grow: 1;
			min-height: 0;
			display: flex;
			align-items: center;
			justify-content: center;
			gap: 64px;
			padding: 20px 40px;
		}
		.side {
			display: flex;
			flex-direction: column;
		}
		.left {
			width: 320px;
			gap: 18px;
		}
		.left h2 {
			font-size: 48px;
			line-height: 1;
			color: var(--petrol);
		}
		.left p {
			margin: 0;
			font-size: 17px;
			line-height: 1.4;
			color: var(--muted-2);
		}
		.qr {
			width: 150px;
			height: 150px;
			border: 2px solid var(--ink);
			border-radius: 10px;
			background: #fff;
			padding: 6px;
		}
		.qr :global(svg) {
			display: block;
			width: 100%;
			height: 100%;
		}
		.right {
			width: 280px;
			gap: 12px;
			font-size: 15px;
			line-height: 1.4;
			color: var(--muted-2);
		}
		.right b {
			font-size: 17px;
			color: var(--ink);
		}
		.device {
			position: relative;
			width: 414px;
			height: min(868px, 100%);
			flex-shrink: 0;
			border-radius: 52px;
			background: var(--ink);
			padding: 12px;
			box-shadow: 0 30px 60px rgba(16, 48, 63, 0.25);
		}
		.screen {
			border-radius: 42px;
			/* Keep fixed and sticky children inside the frame. */
			transform: translateZ(0);
		}
		.home-bar {
			display: block;
			position: absolute;
			left: 50%;
			bottom: 22px;
			width: 120px;
			height: 5px;
			margin-left: -60px;
			border-radius: 3px;
			background: #c7d2d8;
			pointer-events: none;
		}
	}
	@media (min-width: 960px) and (max-width: 1180px) {
		.right {
			display: none;
		}
	}
</style>
