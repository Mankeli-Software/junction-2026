<script lang="ts">
	/**
	 * The webshop (#56, technical-plan.md §7.2): our own static page in the Aimo
	 * webshop's style (docs/design 40, without the chat panel, which is #57), with no
	 * logos. A browser agent orders through the WebMCP tools the page registers, which
	 * are exactly the MCP tools. Visitors identify with the same number entry and demo
	 * account as the phone page. The confirmation link never shows here: after
	 * `request_confirmation` the page only points to the demo phone (vision §8).
	 */
	import { onMount } from 'svelte';
	import { ApiError, createAccount, getMe } from '#lib/demo/api.js';
	import Icon from '#lib/demo/components/Icon.svelte';
	import NumberEntry from '#lib/demo/components/NumberEntry.svelte';
	import { money } from '#lib/demo/i18n.js';
	import { readPhone, writePhone } from '#lib/demo/session.js';
	import type { Lang, SetupValues } from '#lib/demo/types.js';
	import type { components } from '#lib/generated/openapi.js';
	import ProductCard from '#lib/shop/components/ProductCard.svelte';
	import { t } from '#lib/shop/i18n.js';
	import { PRODUCTS, SHELVES } from '#lib/shop/products.js';
	import { AGENT_TOOLS, findModelContext, registerAgentTools } from '#lib/shop/webmcp.js';
	import type { PageProps } from './$types';

	type Quote = components['schemas']['QuoteResponse'];
	type Confirmation = components['schemas']['ConfirmationRequestResponse'];

	let { data }: PageProps = $props();
	const lang = $derived(data.lang);

	let shelf = $state<string | null>(null);
	const shown = $derived(shelf ? PRODUCTS.filter((p) => p.shelf === shelf) : PRODUCTS);

	// Identity: the same demo account and session cookie as /phone.
	let ready = $state(false);
	let account = $state<{ company_name: string; phone_masked: string } | null>(null);
	let editing = $state(false);
	let values = $state<SetupValues>({ countryCode: '+358', number: '', exclusions: [] });
	let busy = $state(false);
	let entryError = $state<'limit' | 'failed' | null>(null);

	// WebMCP: whether the browser has a model context to register the tools with.
	let tools = $state<'looking' | 'ready' | 'missing'>('looking');
	let quote = $state<Quote | null>(null);
	let confirmation = $state<Confirmation | null>(null);

	const phoneHref = $derived(`/phone${lang === 'fi' ? '?lang=fi' : ''}`);

	onMount(() => {
		void identify();
		let unregister: (() => void) | null = null;
		// A polyfill or extension may add the model context a moment after the page loads.
		let tries = 0;
		const look = () => {
			const context = findModelContext();
			if (context) {
				unregister = registerAgentTools(context, onToolResult);
				tools = 'ready';
			} else if (++tries < 20) {
				timer = setTimeout(look, 500);
			} else {
				tools = 'missing';
			}
		};
		let timer = setTimeout(look, 0);
		return () => {
			clearTimeout(timer);
			unregister?.();
		};
	});

	async function identify() {
		const stored = readPhone();
		if (stored.values) values = stored.values;
		try {
			const me = await getMe();
			account = { company_name: me.company_name, phone_masked: me.phone_masked };
		} catch {
			account = null;
		}
		ready = true;
	}

	async function submit(next: SetupValues, e164: string) {
		values = next;
		busy = true;
		entryError = null;
		try {
			const created = await createAccount({ phone_e164: e164, exclusions: next.exclusions, lang });
			account = created;
			editing = false;
			quote = null;
			confirmation = null;
			// So /phone in this tab opens on Contacts with the same account and inbox.
			const stored = readPhone();
			writePhone({ values: next, account: created, seen: created.new_user ? [] : (stored.seen ?? []) });
		} catch (error) {
			entryError = error instanceof ApiError && error.status === 429 ? 'limit' : 'failed';
		} finally {
			busy = false;
		}
	}

	function onToolResult(name: string, result: unknown) {
		if (name === 'build_quote' || name === 'update_quote') {
			quote = result as Quote;
			confirmation = null;
		} else if (name === 'request_confirmation') {
			confirmation = result as Confirmation;
		}
	}

	function langHref(option: Lang): string {
		return `?lang=${option}`;
	}
</script>

<svelte:head>
	<title>{t(lang, 'shopName')}</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="page" {lang}>
	<header class="top">
		<div class="inner">
			<span class="hd shop-name">{t(lang, 'shopName')}</span>
			<nav class="langs" aria-label={t(lang, 'language')}>
				{#each ['en', 'fi'] as const as option (option)}
					<a
						href={langHref(option)}
						class:active={lang === option}
						aria-current={lang === option ? 'true' : undefined}
						hreflang={option}
						data-sveltekit-reset="false"
						data-sveltekit-replacestate
						data-sveltekit-noscroll>{option.toUpperCase()}</a
					>
				{/each}
			</nav>
		</div>
	</header>

	<section class="band">
		<div class="inner">
			<h1 class="hd">{t(lang, 'heroTitle')}</h1>
			<p>{t(lang, 'heroText')}</p>
			<nav class="tiles" aria-label={t(lang, 'categories')}>
				<button type="button" class="tile" aria-pressed={shelf === null} onclick={() => (shelf = null)}>
					{t(lang, 'all')}
				</button>
				{#each SHELVES as option (option.key)}
					<button
						type="button"
						class="tile"
						aria-pressed={shelf === option.key}
						onclick={() => (shelf = shelf === option.key ? null : option.key)}
					>
						{option.name[lang]}
					</button>
				{/each}
			</nav>
		</div>
	</section>

	<main class="inner layout">
		<aside class="side">
			{#if confirmation}
				<section class="card sent" data-testid="confirmation-notice" aria-live="polite">
					<Icon name="phone" size={28} stroke="var(--petrol)" />
					<div>
						<h2 class="hd">{t(lang, 'linkInPhone')}</h2>
						<p>{t(lang, 'linkInPhoneText')}</p>
						{#if confirmation.sms_status === 'sent'}
							<p>{t(lang, 'smsAlso', { number: confirmation.sent_to_masked })}</p>
						{/if}
						<a class="btn-phone" href={phoneHref}>{t(lang, 'openPhone')}</a>
					</div>
				</section>
			{/if}

			<section class="card who" class:open={ready && (!account || editing)} data-testid="identity">
				{#if !ready}
					<div class="blank"></div>
				{:else if account && !editing}
					<span class="label">{t(lang, 'orderingAs')}</span>
					<b class="company" data-testid="company">{account.company_name}</b>
					<span class="masked" data-testid="phone-masked">{account.phone_masked}</span>
					<button type="button" class="link-button" onclick={() => (editing = true)}>
						{t(lang, 'changeNumber')}
					</button>
				{:else}
					<h2 class="hd">{t(lang, 'whoTitle')}</h2>
					<p>{t(lang, 'whoText')}</p>
					<div class="entry">
						<NumberEntry
							{lang}
							initial={values}
							{busy}
							error={entryError}
							onsubmit={submit}
							notices={[
								{ icon: 'monitor', text: t(lang, 'noticeDashboard') },
								{ icon: 'chat', text: t(lang, 'noticeInbox') }
							]}
							hint={t(lang, 'phoneHint')}
							submitLabel={t(lang, 'continue')}
							busyLabel={t(lang, 'continuing')}
						/>
					</div>
				{/if}
			</section>

			<section class="card tools" data-testid="tools" data-state={tools}>
				<h2 class="hd">{t(lang, 'toolsTitle')}</h2>
				{#if tools === 'ready'}
					<p class="ok"><Icon name="check" size={18} stroke="var(--lime-text)" weight={3} />{t(lang, 'toolsReady', { n: AGENT_TOOLS.length })}</p>
					<p class="try">{t(lang, 'toolsTry')}</p>
				{:else if tools === 'missing'}
					<p>{t(lang, 'toolsMissing')}</p>
				{/if}
				{#if quote}
					<div class="quote" data-testid="latest-quote">
						<span class="label">{t(lang, 'latestQuote')}</span>
						<b>
							{t(lang, quote.lines.length === 1 ? 'quoteSummaryOne' : 'quoteSummary', {
								lines: quote.lines.length,
								total: money(quote.total_cents)
							})}
						</b>
						<span>
							{quote.decision === 'ready'
								? t(lang, 'quoteReady')
								: quote.decision === 'needs_clarification'
									? t(lang, 'quoteQuestion')
									: t(lang, 'quoteRejected')}
						</span>
					</div>
				{/if}
			</section>
		</aside>

		<section class="products" aria-labelledby="products-title">
			<div class="products-head">
				<h2 id="products-title" class="hd">{shelf ? SHELVES.find((s) => s.key === shelf)?.name[lang] : t(lang, 'productsTitle')}</h2>
				<span>{t(lang, 'productCount', { n: shown.length })}</span>
			</div>
			<p class="note">{t(lang, 'productsNote')}</p>
			<div class="grid">
				{#each shown as product (product.product_id)}
					<ProductCard {product} {lang} />
				{/each}
			</div>
		</section>
	</main>

	<footer class="foot">
		<div class="inner">
			<b>{t(lang, 'footLead')}</b>
			<span>{t(lang, 'footText')}</span>
		</div>
	</footer>
</div>

<style>
	.page {
		min-height: 100dvh;
		display: flex;
		flex-direction: column;
		background: var(--page);
	}
	.inner {
		width: 100%;
		max-width: 1320px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.top {
		background: var(--petrol);
		color: #fff;
	}
	.top .inner {
		height: 56px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
	}
	.shop-name {
		font-size: 24px;
		color: #fff;
	}
	.langs {
		display: flex;
		gap: 4px;
		font-size: 14px;
		font-weight: 600;
	}
	.langs a {
		color: #fff;
		text-decoration: none;
		border-radius: 4px;
		padding: 4px 8px;
	}
	.langs a.active {
		background: #fff;
		color: var(--petrol);
	}

	.band {
		background: var(--lavender);
		border-bottom: 1px solid var(--border);
	}
	.band .inner {
		padding-top: 24px;
		padding-bottom: 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.band h1 {
		font-size: 34px;
		line-height: 1.05;
		color: var(--petrol);
	}
	.band p {
		margin: 0;
		max-width: 760px;
		font-size: 16px;
		line-height: 1.4;
		color: var(--muted-2);
	}
	.tiles {
		margin-top: 8px;
		display: flex;
		gap: 8px;
		overflow-x: auto;
		padding-bottom: 4px;
		scrollbar-width: thin;
	}
	.tile {
		flex-shrink: 0;
		height: 40px;
		padding: 0 16px;
		border-radius: 20px;
		border: 1px solid var(--border-strong);
		background: #fff;
		font-size: 15px;
		font-weight: 600;
		color: var(--ink);
		cursor: pointer;
	}
	.tile[aria-pressed='true'] {
		background: var(--petrol);
		border-color: var(--petrol);
		color: #fff;
	}

	.layout {
		flex-grow: 1;
		padding-top: 20px;
		padding-bottom: 32px;
		display: flex;
		flex-direction: column;
		gap: 24px;
	}
	.side {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 18px;
	}
	.card h2 {
		font-size: 24px;
		line-height: 1.1;
		color: var(--petrol);
	}
	.card p {
		margin: 6px 0 0;
		font-size: 15px;
		line-height: 1.4;
		color: var(--muted-2);
	}
	.label {
		font-size: 13px;
		font-weight: 600;
		color: var(--muted);
	}

	.who {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.who .blank {
		height: 96px;
	}
	.company {
		font-size: 20px;
	}
	.masked {
		font-size: 15px;
		color: var(--muted-2);
	}
	.link-button {
		align-self: flex-start;
		margin-top: 6px;
		padding: 0;
		border: 0;
		background: none;
		font-size: 15px;
		font-weight: 600;
		color: var(--petrol);
		text-decoration: underline;
		cursor: pointer;
	}
	/* The number entry brings its own cards, so its section is not a card. */
	.who.open {
		background: none;
		border: 0;
		padding: 0;
	}
	.entry {
		margin-top: 8px;
	}
	.entry :global(.body) {
		padding: 0;
	}

	.tools .ok {
		display: flex;
		gap: 8px;
		align-items: flex-start;
		font-weight: 600;
		color: var(--ink);
	}
	.tools .ok :global(svg) {
		flex-shrink: 0;
		margin-top: 2px;
	}
	.tools .try {
		font-style: italic;
	}
	.quote {
		margin-top: 14px;
		padding-top: 12px;
		border-top: 1px solid var(--divider);
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 15px;
	}
	.quote b {
		font-size: 18px;
	}

	.sent {
		display: flex;
		gap: 12px;
		align-items: flex-start;
		background: var(--yellow-note);
		border-color: var(--amber);
	}
	.sent :global(svg) {
		flex-shrink: 0;
	}
	.btn-phone {
		margin-top: 12px;
		display: inline-flex;
		align-items: center;
		height: 44px;
		padding: 0 18px;
		border-radius: 8px;
		background: var(--lime);
		color: var(--ink);
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 19px;
		letter-spacing: 0.5px;
		text-transform: uppercase;
		text-decoration: none;
	}

	.products-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 12px;
	}
	.products-head h2 {
		font-size: 28px;
		color: var(--ink);
	}
	.products-head span {
		font-size: 14px;
		color: var(--muted);
	}
	.note {
		margin: 4px 0 14px;
		font-size: 15px;
		color: var(--muted-2);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 12px;
	}

	.foot {
		background: #fff;
		border-top: 1px solid var(--border);
	}
	.foot .inner {
		padding-top: 18px;
		padding-bottom: 22px;
		display: flex;
		flex-wrap: wrap;
		gap: 4px 10px;
		font-size: 14px;
		color: var(--muted-2);
	}

	/* On a computer: the page layout of design 40, products left and the agent column right. */
	@media (min-width: 960px) {
		.inner {
			padding: 0 60px;
		}
		.band .inner {
			padding-top: 32px;
			padding-bottom: 26px;
		}
		.band h1 {
			font-size: 46px;
		}
		.band p {
			font-size: 17px;
		}
		.layout {
			display: grid;
			grid-template-columns: minmax(0, 1fr) 380px;
			align-items: start;
			gap: 28px;
			padding-top: 28px;
			padding-bottom: 48px;
		}
		.side {
			grid-column: 2;
			grid-row: 1;
		}
		.products {
			grid-column: 1;
			grid-row: 1;
		}
		.grid {
			grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
			gap: 18px;
		}
	}
</style>
