<script lang="ts">
	import { chainCheck } from '#lib/dashboard/chain.svelte.ts';
	import Icon, { type IconName } from '#lib/dashboard/components/Icon.svelte';
	import OrderNav from '#lib/dashboard/components/OrderNav.svelte';
	import ProductThumb from '#lib/dashboard/components/ProductThumb.svelte';
	import StatusPill from '#lib/dashboard/components/StatusPill.svelte';
	import WhyPanel from '#lib/dashboard/components/WhyPanel.svelte';
	import { formatDay, formatMoney, formatTime } from '#lib/dashboard/format.ts';
	import { pick, t } from '#lib/dashboard/i18n.ts';
	import { lineQuantityText } from '#lib/dashboard/lines.ts';
	import { combineSteps, mergeStep } from '#lib/dashboard/merge.ts';
	import { sessionLive } from '#lib/dashboard/session-live.svelte.ts';
	import { channelBadge, exclusionsShort } from '#lib/dashboard/states.ts';
	import type { Step } from '#lib/dashboard/types.ts';
	import { useUi } from '#lib/dashboard/ui.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const ui = useUi();

	const summary = $derived(data.summary);
	const base = $derived(`/dashboard/${encodeURIComponent(summary.session_id)}`);

	let liveSteps = $state<Step[]>([]);
	const steps = $derived(combineSteps(data.steps, liveSteps));
	const chain = chainCheck(() => steps);

	sessionLive(() => data.summary.session_id, {
		onStep: (step) => mergeStep(liveSteps, step),
		onReset: () => (liveSteps = [])
	});

	// The first line's "Why" is open, as on screen 31.
	let openWhy = $state<string | null>(null);
	let touched = $state(false);
	const shownWhy = $derived(touched ? openWhy : (summary.requests[0]?.lines[0]?.line_id ?? null));

	function toggleWhy(lineId: string) {
		openWhy = shownWhy === lineId ? null : lineId;
		touched = true;
	}

	const FLAG_ICONS: Record<string, IconName> = {
		rounded_up: 'arrowup',
		stock_unverified: 'plus',
		no_allergen_info: 'alert'
	};

	const quoteText = $derived(
		!summary.quote
			? t('no_quote', ui.lang)
			: summary.quote.version === 1
				? t('quote_no_edits', ui.lang, { v: 1 })
				: t('quote_edited', ui.lang, { v: summary.quote.version })
	);
</script>

<svelte:head>
	<title>{summary.company.name} {summary.order_number ?? ''} S.I.MO</title>
</svelte:head>

<OrderNav sessionId={summary.session_id} orderNumber={summary.order_number} current="summary">
	<div class="head">
		<div class="who">
			<h1 class="hd">{summary.company.name}</h1>
			<div class="status">
				<StatusPill state={summary.state} since={summary.state_since} channel={summary.channel} big />
				{#if summary.status_line}<span>{pick(summary.status_line, ui.lang)}</span>{/if}
			</div>
		</div>
		<div class="kvs">
			<div class="kv">
				<span>{t('delivery', ui.lang)}</span><b
					>{summary.delivery_date ? formatDay(summary.delivery_date, ui.lang) : '–'}</b
				>
			</div>
			<div class="kv">
				<span>{t('total_incl_vat', ui.lang)}</span><b
					>{summary.total_cents !== null ? formatMoney(summary.total_cents, ui.lang) : '–'}</b
				>
			</div>
			<div class="kv">
				<span>{t('channel', ui.lang)}</span><b>{channelBadge(summary.channel, summary.client, ui.lang)}</b>
			</div>
			<div class="kv">
				<span>{t('kitchen_avoids', ui.lang)}</span><b>{exclusionsShort(summary.company.exclusions, ui.lang)}</b>
			</div>
		</div>
	</div>
</OrderNav>

<main class="wrap body">
	<div class="main">
		<h2 class="hd">{t('ordered_and_why', ui.lang)}</h2>
		{#each summary.requests as request (request.request_id)}
			{@const open = request.lines.find((l) => l.line_id === shownWhy)}
			<article class="card req" class:open>
				<div class="lrow">
					<div class="asked">
						<span class="label">{t('asked', ui.lang)}</span>
						<span class="text">{pick(request.asked_text, ui.lang)}</span>
						{#if request.group}<span class="group">{pick(request.group, ui.lang)}</span>{/if}
					</div>
					<span class="arrow"><Icon name="arrow" size={20} color="var(--d-faint)" stroke={2} /></span>
					<div class="lines">
						{#each request.lines as line (line.line_id)}
							<div class="line">
								<ProductThumb src={line.image_url} alt={pick(line.name, ui.lang)} />
								<div class="desc">
									<span class="name"
										>{pick(line.name, ui.lang)} <span class="pid">#{line.product_id}</span></span
									>
									<span class="qty"
										>{lineQuantityText(line, request.asked, ui.lang, request.lines.length === 1)}</span
									>
									<span>{pick(line.reason_text, ui.lang)}</span>
								</div>
								<b class="price">{formatMoney(line.line_total_cents, ui.lang)}</b>
								<button
									type="button"
									class="why"
									aria-expanded={shownWhy === line.line_id}
									onclick={() => toggleWhy(line.line_id)}
								>
									{t('why', ui.lang)}
									<Icon name={shownWhy === line.line_id ? 'up' : 'down'} size={14} stroke={2.5} />
								</button>
							</div>
						{/each}
						{#each request.not_ordered as item, i (i)}
							<div class="line not">
								<span class="badge">{t('not_ordered', ui.lang)}</span>
								<span
									>{item.name}{item.quantity !== null ? `, ${item.quantity} ${item.unit ?? ''}` : ''}.
									{pick(item.reason, ui.lang)}</span
								>
							</div>
						{/each}
					</div>
				</div>
				{#if open}
					<WhyPanel trace={open.trace} baseUnit={open.base_unit} />
				{/if}
			</article>
		{:else}
			<p class="empty">{t('nothing_ordered_yet', ui.lang)}</p>
		{/each}
	</div>

	<aside class="side">
		<section class="card panel">
			<h2 class="hd">{t('flags_checked', ui.lang)}</h2>
			{#each summary.flags as flag (flag.flag_key)}
				<div class="flag">
					<span class="ico"><Icon name={FLAG_ICONS[flag.code] ?? 'alert'} size={16} /></span>
					<div class="ftext">
						<b>{pick(flag.text, ui.lang)}</b>
						{#if flag.detail}<span>{pick(flag.detail, ui.lang)}</span>{/if}
					</div>
					{#if flag.acknowledged_at}
						<span class="ack">✓ {formatTime(flag.acknowledged_at, ui.lang)}</span>
					{:else}
						<span class="ack no">{t('not_acknowledged', ui.lang)}</span>
					{/if}
				</div>
			{:else}
				<p class="empty small">{t('no_flags', ui.lang)}</p>
			{/each}
		</section>

		<section class="card panel trust">
			<h2 class="hd">{t('can_we_trust', ui.lang)}</h2>
			<div class="tl">
				{#if summary.signature_valid === true}
					<Icon name="shield" size={20} color="var(--d-confirmed-fg)" />
					<span>{t('sig_valid', ui.lang)}</span>
				{:else if summary.signature_valid === false}
					<Icon name="shieldx" size={20} color="var(--d-attention-fg)" />
					<span class="bad">{t('sig_invalid', ui.lang)}</span>
				{:else}
					<Icon name="alert" size={20} color="var(--d-faint)" />
					<span>{t('sig_unknown', ui.lang)}</span>
				{/if}
			</div>
			<div class="tl">
				{#if chain.result?.ok}
					<Icon name="link" size={20} color="var(--d-confirmed-fg)" />
					<a href="{base}/audit">{t('chain_intact_n', ui.lang, { n: chain.result.checked })}</a>
				{:else if chain.result}
					<Icon name="x" size={20} color="var(--d-attention-fg)" />
					<a href="{base}/audit" class="bad"
						>{t('chain_broken_at', ui.lang, { n: chain.result.first_bad_order_index ?? '?' })}</a
					>
				{:else}
					<Icon name="link" size={20} color="var(--d-faint)" />
					<a href="{base}/audit">{t('chain_checking', ui.lang)}</a>
				{/if}
			</div>
			<div class="tl">
				<Icon name="list" size={20} color="var(--d-petrol)" stroke={2} />
				<a href="{base}/flow">{quoteText}</a>
			</div>
		</section>
	</aside>
</main>

<style>
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
	}
	.who {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	h1 {
		font-size: 52px;
		line-height: 1;
		color: var(--d-petrol);
	}
	.status {
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
		font-size: 15px;
		color: var(--d-ink-2);
	}
	.kvs {
		display: grid;
		grid-template-columns: repeat(4, minmax(120px, auto));
		gap: 8px;
	}
	.kv {
		background: #fff;
		border-radius: 8px;
		padding: 12px 16px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.kv span {
		font-size: 13px;
		color: var(--d-muted);
	}
	.kv b {
		font-size: 18px;
	}
	.body {
		padding-top: 24px;
		padding-bottom: 40px;
		display: flex;
		flex-wrap: wrap;
		gap: 20px;
		align-items: flex-start;
	}
	.main {
		flex: 999 1 640px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.main > h2 {
		font-size: 30px;
	}
	.req.open {
		border: 2px solid var(--d-petrol);
	}
	.lrow {
		display: flex;
		flex-wrap: wrap;
		gap: 16px 24px;
		align-items: center;
		padding: 18px 20px;
	}
	.asked {
		flex: 1 1 200px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.label {
		font-size: 13px;
		font-weight: 700;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: var(--d-muted);
	}
	.asked .text {
		font-size: 18px;
		font-weight: 700;
	}
	.group {
		font-size: 14px;
		color: var(--d-muted);
	}
	.arrow {
		display: flex;
	}
	.lines {
		flex: 3 1 480px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.line {
		display: flex;
		gap: 14px 24px;
		align-items: center;
		flex-wrap: wrap;
	}
	.desc {
		flex: 1 1 260px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
		font-size: 15px;
	}
	.name {
		font-size: 18px;
		font-weight: 700;
		color: var(--d-petrol);
	}
	.pid {
		font-size: 13px;
		color: var(--d-faint);
		font-weight: 500;
	}
	.qty {
		color: var(--d-muted);
	}
	.price {
		font-size: 22px;
		white-space: nowrap;
	}
	.why {
		font-size: 15px;
		font-weight: 700;
		color: var(--d-petrol);
		background: var(--d-chip);
		border: 0;
		border-radius: 18px;
		padding: 8px 14px;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.line.not {
		font-size: 15px;
		color: var(--d-ink-2);
		gap: 10px;
	}
	.badge {
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.5px;
		text-transform: uppercase;
		border-radius: 4px;
		padding: 3px 7px;
		background: var(--d-ended-bg);
		color: var(--d-muted);
	}
	.side {
		flex: 1 1 340px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.panel {
		padding: 18px 20px;
	}
	.panel h2 {
		font-size: 26px;
		margin-bottom: 4px;
	}
	.flag {
		display: flex;
		gap: 12px;
		align-items: flex-start;
		padding: 12px 0;
		border-bottom: 1px solid var(--d-line-soft);
	}
	.flag:last-child {
		border-bottom: 0;
	}
	.ico {
		width: 30px;
		height: 30px;
		flex-shrink: 0;
		border-radius: 15px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--d-waiting-bg);
	}
	.ftext {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex-grow: 1;
	}
	.ftext b {
		font-size: 15px;
	}
	.ftext span {
		font-size: 14px;
		color: var(--d-muted);
	}
	.ack {
		font-size: 13px;
		color: var(--d-confirmed-fg);
		font-weight: 700;
		white-space: nowrap;
	}
	.ack.no {
		color: var(--d-waiting-fg);
	}
	.trust {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.tl {
		display: flex;
		gap: 10px;
		align-items: center;
		font-size: 15px;
	}
	.bad {
		color: var(--d-attention-fg);
		font-weight: 700;
	}
	.empty {
		font-size: 16px;
		color: var(--d-muted);
	}
	.empty.small {
		font-size: 15px;
		margin: 8px 0 0;
	}
	@media (max-width: 900px) {
		.kvs {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
</style>
