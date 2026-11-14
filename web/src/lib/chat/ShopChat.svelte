<script lang="ts" module>
	import type { Exclusion } from '#lib/demo/types.js';

	export interface ChatAccount {
		company_name: string;
		phone_masked: string;
		exclusions: Exclusion[];
	}
</script>

<script lang="ts">
	/**
	 * S.I.MO's chat on the webshop (#57, docs/specs/webshop-chat.md §2 to §4, design
	 * 40 and UI-02): a launcher that opens a side panel on a computer and a full screen
	 * on a phone. The header names the kitchen's exclusions; before the first message
	 * the visitor enters their number (the phone page's number entry) and sees the
	 * dashboard notice. "Current order" is the latest quote, refreshed after each turn.
	 *
	 * The confirmation link never shows here (§4.4): after sending, only the notice card.
	 */
	import { onDestroy, tick } from 'svelte';
	import { apiData } from '#lib/a2ui/api.js';
	import { setChatContext } from '#lib/a2ui/context.js';
	import { SIMO_CATALOG_ID } from '#lib/a2ui/protocol.js';
	import Surface from '#lib/a2ui/Surface.svelte';
	import type { ChatData } from '#lib/a2ui/types.js';
	import NumberEntry from '#lib/demo/components/NumberEntry.svelte';
	import { exclusionLabel, joinList, money } from '#lib/demo/i18n.js';
	import type { Lang, SetupValues } from '#lib/demo/types.js';
	import ChatView from './ChatView.svelte';
	import { t } from './i18n';
	import { ChatSession } from './session.svelte';

	let {
		lang,
		ready,
		account,
		values,
		busy = false,
		entryError = null,
		onsubmit,
		open = $bindable(false),
		data = apiData
	}: {
		lang: Lang;
		/** The account check has finished. */
		ready: boolean;
		account: ChatAccount | null;
		values: SetupValues;
		busy?: boolean;
		entryError?: 'limit' | 'failed' | null;
		onsubmit: (values: SetupValues, e164: string) => void;
		open?: boolean;
		data?: ChatData;
	} = $props();

	const CURRENT_SURFACE = 'current-order';

	const session = new ChatSession({
		endpoint: '/api/v1/chat',
		photoEndpoint: '/api/v1/recipe-drafts/read',
		lang: () => lang,
		onDone: () => void refreshCurrent()
	});
	// The data source is fixed for the panel's life.
	// svelte-ignore state_referenced_locally
	setChatContext({ store: session.store, data, lang: () => lang, revision: () => session.revision });
	onDestroy(() => session.dispose());

	let current = $state<{ quote_id: string; total_cents: number } | null>(null);
	let orderOpen = $state(false);
	let panel = $state<HTMLElement | null>(null);
	let launcher = $state<HTMLButtonElement | null>(null);
	let input = $state<HTMLInputElement | null>(null);

	const subtitle = $derived(
		account
			? account.exclusions.length === 0
				? t(lang, 'noExclusions')
				: t(lang, 'avoids', {
						list: joinList(
							lang,
							account.exclusions.map((e) => exclusionLabel(lang, e).toLowerCase())
						)
					})
			: null
	);

	/** `GET /api/v1/quotes/current`: the newest quote, or nothing yet (404). */
	async function refreshCurrent() {
		if (!account) return;
		try {
			const response = await fetch('/api/v1/quotes/current', {
				credentials: 'same-origin',
				headers: { accept: 'application/json' }
			});
			if (!response.ok) return;
			const quote = (await response.json()) as { quote_id?: unknown; total_cents?: unknown };
			if (typeof quote.quote_id !== 'string' || typeof quote.total_cents !== 'number') return;
			current = { quote_id: quote.quote_id, total_cents: quote.total_cents };
			// The bar opens the latest QuoteCard, drawn by the same renderer as the chat.
			session.store.process([
				{ version: 'v0.9', createSurface: { surfaceId: CURRENT_SURFACE, catalogId: SIMO_CATALOG_ID } },
				{
					version: 'v0.9',
					updateComponents: {
						surfaceId: CURRENT_SURFACE,
						components: [{ id: 'root', component: 'QuoteCard', quoteId: quote.quote_id }]
					}
				}
			]);
		} catch {
			// Offline: keep what is shown.
		}
	}

	// A new account (or the first check) loads its current order; another number clears it.
	let loadedFor: string | null = null;
	$effect(() => {
		const key = account ? `${account.company_name} ${account.phone_masked}` : null;
		if (key === loadedFor) return;
		loadedFor = key;
		current = null;
		orderOpen = false;
		if (key) void refreshCurrent();
	});

	// After the number entry the chat replaces it: focus goes to the text field, not lost.
	$effect(() => {
		if (!open || !input || !panel) return;
		const active = document.activeElement;
		if (!active || active === document.body || !panel.contains(active)) input.focus();
	});

	async function show() {
		open = true;
		await tick();
		(input ?? panel?.querySelector<HTMLElement>('input, select, button'))?.focus();
	}

	async function hide() {
		open = false;
		await tick();
		launcher?.focus();
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.stopPropagation();
			void hide();
		}
	}
</script>

{#if !open}
	<button
		type="button"
		class="launcher"
		bind:this={launcher}
		aria-label={t(lang, 'openLabel')}
		aria-expanded="false"
		data-testid="chat-launcher"
		onclick={show}
	>
		<span class="avatar" aria-hidden="true">S</span>
		<span>{t(lang, 'open')}</span>
	</button>
{/if}

{#if open}
	<div
		class="panel"
		bind:this={panel}
		role="dialog"
		aria-label={t(lang, 'panelLabel')}
		data-testid="chat-panel"
		tabindex="-1"
		{onkeydown}
	>
		<header class="head">
			<span class="avatar big" aria-hidden="true">S</span>
			<div class="who">
				<b>S.I.MO</b>
				{#if subtitle}<span data-testid="chat-exclusions">{subtitle}</span>{/if}
			</div>
			<button type="button" class="close" aria-label={t(lang, 'close')} onclick={hide}>
				<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" aria-hidden="true">
					<path d="M6 6l12 12M18 6L6 18" />
				</svg>
			</button>
		</header>

		{#if account && current}
			<button
				type="button"
				class="order-bar"
				aria-expanded={orderOpen}
				aria-controls="chat-current-order"
				data-testid="current-order"
				onclick={() => (orderOpen = !orderOpen)}
			>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--petrol)" stroke-width="2.2" aria-hidden="true">
					<path d="M3 4h2l2.5 11h11L21 7H7" /><circle cx="9" cy="19" r="1.5" /><circle cx="18" cy="19" r="1.5" />
				</svg>
				<b class="grow">{t(lang, 'currentOrder')}</b>
				<b data-testid="current-order-total">{money(current.total_cents)}</b>
				<svg class="chev" class:up={orderOpen} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--petrol)" stroke-width="2.5" aria-hidden="true">
					<path d="M6 9l6 6 6-6" />
				</svg>
			</button>
			{#if orderOpen}
				<div class="order" id="chat-current-order">
					<Surface surfaceId={CURRENT_SURFACE} />
				</div>
			{/if}
		{/if}

		{#if !ready}
			<div class="grow"></div>
		{:else if !account}
			<div class="entry" data-testid="chat-number-entry">
				<h2 class="hd">{t(lang, 'whoTitle')}</h2>
				<p>{t(lang, 'whoText')}</p>
				<NumberEntry
					{lang}
					initial={values}
					{busy}
					error={entryError}
					{onsubmit}
					notices={[
						{ icon: 'monitor', text: t(lang, 'noticeDashboard') },
						{ icon: 'chat', text: t(lang, 'noticeInbox') }
					]}
					hint={t(lang, 'phoneHint')}
					submitLabel={t(lang, 'continue')}
					busyLabel={t(lang, 'continuing')}
				/>
			</div>
		{:else}
			<ChatView {session} {lang} photos inputId="shop-chat-input" bind:input>
				{#snippet empty(ask)}
					<p class="bot">{t(lang, 'greeting')}</p>
					<p class="notice" data-testid="chat-notice">{t(lang, 'noticeDashboard')}</p>
					<div class="examples" role="group" aria-label={t(lang, 'examples')}>
						{#each ['example1', 'example2', 'example3'] as const as key (key)}
							<button type="button" class="sugg" onclick={() => ask(t(lang, key))}>{t(lang, key)}</button>
						{/each}
					</div>
				{/snippet}
			</ChatView>
		{/if}
	</div>
{/if}

<style>
	.launcher {
		position: fixed;
		right: 20px;
		bottom: 20px;
		z-index: 40;
		height: 56px;
		padding: 0 22px 0 10px;
		display: flex;
		align-items: center;
		gap: 10px;
		border: 0;
		border-radius: 28px;
		background: var(--petrol);
		color: #fff;
		font: inherit;
		font-size: 16px;
		font-weight: 700;
		box-shadow: 0 6px 20px rgba(16, 48, 63, 0.25);
		cursor: pointer;
	}
	.launcher:hover {
		background: var(--petrol-dark);
	}
	.avatar {
		width: 36px;
		height: 36px;
		flex-shrink: 0;
		border-radius: 18px;
		background: #2a6582;
		color: #fff;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 20px;
	}

	.panel {
		position: fixed;
		inset: 0;
		z-index: 50;
		display: flex;
		flex-direction: column;
		background: var(--card);
		color: var(--ink);
		outline: none;
	}
	@media (min-width: 720px) {
		.panel {
			left: auto;
			width: 460px;
			border-left: 1px solid var(--border);
			box-shadow: -8px 0 24px rgba(16, 48, 63, 0.12);
		}
	}

	.head {
		height: 60px;
		flex-shrink: 0;
		background: var(--petrol);
		color: #fff;
		padding: 0 14px;
		display: flex;
		align-items: center;
		gap: 12px;
	}
	.who {
		display: flex;
		flex-direction: column;
		flex-grow: 1;
		min-width: 0;
	}
	.who b {
		font-size: 16px;
	}
	.who span {
		font-size: 13px;
		color: #cfe0e8;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.close {
		width: 40px;
		height: 40px;
		flex-shrink: 0;
		border-radius: 20px;
		border: 0;
		background: #2a6582;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}

	.order-bar {
		flex-shrink: 0;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 11px 14px;
		border: 0;
		border-bottom: 1px solid var(--border);
		background: var(--lavender);
		font: inherit;
		color: inherit;
		text-align: left;
		cursor: pointer;
	}
	.order-bar b {
		font-size: 15px;
	}
	.grow {
		flex-grow: 1;
	}
	.chev {
		transition: transform 0.15s;
	}
	.chev.up {
		transform: rotate(180deg);
	}
	.order {
		flex-shrink: 0;
		max-height: 50%;
		overflow-y: auto;
		padding: 14px;
		border-bottom: 1px solid var(--border);
		background: var(--page);
	}

	.entry {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 18px 14px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		background: var(--page);
	}
	.entry h2 {
		font-size: 24px;
		line-height: 1.1;
		color: var(--petrol);
	}
	.entry > p {
		margin: 0 0 8px;
		font-size: 15px;
		line-height: 1.4;
		color: var(--muted-2);
	}
	.entry :global(.body) {
		padding: 0;
	}

	.bot {
		align-self: flex-start;
		max-width: min(290px, 90%);
		margin: 0;
		background: var(--page);
		border-radius: 4px 14px 14px 14px;
		padding: 10px 13px;
		font-size: 15px;
		line-height: 1.4;
	}
	.notice {
		margin: 0;
		background: var(--yellow-note);
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 14px;
		line-height: 1.4;
	}
	.examples {
		display: flex;
		flex-direction: column;
		gap: 8px;
		align-items: flex-start;
	}
	.sugg {
		min-height: 38px;
		padding: 6px 14px;
		border-radius: 19px;
		border: 1px solid var(--border-strong);
		background: var(--card);
		color: var(--ink);
		font: inherit;
		font-size: 14px;
		text-align: left;
		cursor: pointer;
	}
	.sugg:hover {
		border-color: var(--petrol);
	}
</style>
