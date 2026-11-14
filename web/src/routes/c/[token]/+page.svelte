<script lang="ts">
	/**
	 * The confirmation page /c/[token] (docs/specs/confirmation-page.md, screens 20 to 22):
	 * the only place an order can be confirmed. Server-rendered from engine data only;
	 * all product text is escaped (never {@html}).
	 */
	import { page } from '$app/state';
	import ClosedState from '#lib/confirmation/components/ClosedState.svelte';
	import ConfirmBar from '#lib/confirmation/components/ConfirmBar.svelte';
	import FlagCard from '#lib/confirmation/components/FlagCard.svelte';
	import LineCard from '#lib/confirmation/components/LineCard.svelte';
	import LineSheet from '#lib/confirmation/components/LineSheet.svelte';
	import OrderHeader from '#lib/confirmation/components/OrderHeader.svelte';
	import Receipt from '#lib/confirmation/components/Receipt.svelte';
	import TopBar from '#lib/confirmation/components/TopBar.svelte';
	import { money } from '#lib/confirmation/format.js';
	import { ui } from '#lib/confirmation/forms.svelte.js';
	import { t } from '#lib/confirmation/i18n.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const view = $derived(data.view);
	const lang = $derived(data.lang);
	const url = $derived(page.url);
	const active = $derived(view.state === 'ready' || view.state === 'requote_needed');
	const done = $derived(view.flags.filter((f) => f.acknowledged).length);

	const openRequest = $derived(
		data.lineId ? view.requests.find((r) => r.lines.some((l) => l.id === data.lineId)) : undefined
	);
	const openLine = $derived(openRequest?.lines.find((l) => l.id === data.lineId));

	const failure = $derived(form && 'status' in form ? form : null);
	const sheetError = $derived(failure && failure.lineId && failure.lineId === openLine?.id ? failure.text : null);
	const pageError = $derived(
		failure && !sheetError && !(failure.status === 409 && view.change?.reason === 'requote')
			? (failure.text?.[lang] ?? (failure.status === 409 ? t(lang, 'errorStale') : t(lang, 'errorGeneric')))
			: null
	);
	const totalChanged = $derived(
		view.change && view.change.previous_total_cents !== view.quote.total_cents
			? t(lang, 'totalChanged', {
					from: money(view.change.previous_total_cents),
					to: money(view.quote.total_cents)
				})
			: null
	);
</script>

<svelte:head>
	<title>{view.state === 'confirmed' ? t(lang, 'orderReceived') : t(lang, 'yourOrder')}: S.I.MO</title>
	<meta name="referrer" content="no-referrer" />
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="page" {lang}>
	{#if view.state === 'confirmed' && view.order}
		<TopBar {lang} {url} right={view.company.name} />
		<Receipt {view} order={view.order} {lang} />
	{:else if !active}
		<TopBar {lang} {url} />
		<ClosedState {view} {lang} />
	{:else}
		<TopBar {lang} {url} />
		<OrderHeader {view} {lang} />

		<div class="live" aria-live="polite">
			{#if ui.pending}<p class="updating" data-testid="updating">{t(lang, 'updating')}</p>{/if}
		</div>

		{#if pageError}
			<p class="notice error" role="alert">{pageError}</p>
		{/if}
		{#if view.change?.text}
			<p class="notice change" data-testid="requote">{view.change.text[lang]}</p>
		{/if}
		{#if totalChanged}
			<p class="notice change" data-testid="total-changed">{totalChanged}</p>
		{/if}

		{#if view.flags.length > 0}
			<section class="block">
				<div class="block-head">
					<h2 class="hd">{t(lang, 'checkFirst')}</h2>
					<span class="count" data-testid="flag-count">{t(lang, 'doneCount', { done, total: view.flags.length })}</span>
				</div>
				{#each view.flags as flag (flag.key)}
					<FlagCard {flag} {lang} quoteHash={view.quote.hash} {url} />
				{/each}
			</section>
		{/if}

		<section class="block">
			<h2 class="hd">{t(lang, 'askedAdded')}</h2>
			{#each view.requests as request (request.id)}
				{#each request.lines as line (line.id)}
					<LineCard
						{line}
						asked={request.asked[lang]}
						flags={view.flags}
						{lang}
						{url}
						changed={Boolean(view.change?.line_ids.includes(line.id))}
					/>
				{/each}
				{#if request.not_ordered.length > 0}
					<p class="not-ordered">
						{t(lang, 'notOrdered', { items: request.not_ordered.map((item) => item[lang]).join(', ') })}
					</p>
				{/if}
			{/each}
		</section>

		<div class="spacer"></div>
		<ConfirmBar {view} {lang} {url} askCancel={data.askCancel} />

		{#if openLine && openRequest}
			<LineSheet
				line={openLine}
				asked={openRequest.asked[lang]}
				{lang}
				quoteHash={view.quote.hash}
				{url}
				error={sheetError}
			/>
		{/if}
	{/if}
</div>

<style>
	.page {
		max-width: 480px;
		min-height: 100vh;
		margin: 0 auto;
		background: var(--page);
		display: flex;
		flex-direction: column;
	}
	@media (min-width: 520px) {
		.page {
			box-shadow: 0 0 0 1px var(--border);
		}
	}
	.block {
		padding: 20px 16px 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.block h2 {
		font-size: 26px;
	}
	.block-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 12px;
	}
	.count {
		font-size: 14px;
		font-weight: 700;
		color: var(--petrol);
	}
	.live {
		position: sticky;
		top: 0;
		z-index: 15;
	}
	.updating {
		margin: 0;
		background: var(--petrol);
		color: #fff;
		font-weight: 600;
		font-size: 14px;
		padding: 8px 16px;
	}
	.notice {
		margin: 16px 16px 0;
		border-radius: 8px;
		padding: 10px 14px;
		font-size: 15px;
		font-weight: 600;
	}
	.notice.change {
		background: var(--chip);
		color: var(--petrol);
	}
	.notice.error {
		background: #fbe9e7;
		color: var(--red);
	}
	.not-ordered {
		margin: -4px 4px 0;
		font-size: 14px;
		color: var(--muted-2);
	}
	.spacer {
		flex-grow: 1;
	}
</style>
