<script lang="ts">
	import Icon, { type IconName } from '#lib/dashboard/components/Icon.svelte';
	import OrderCardView from '#lib/dashboard/components/OrderCard.svelte';
	import { formatMoney } from '#lib/dashboard/format.ts';
	import { t, type StringKey } from '#lib/dashboard/i18n.ts';
	import { connectStream } from '#lib/dashboard/live.svelte.ts';
	import { applyOrderUpdated } from '#lib/dashboard/merge.ts';
	import { exclusionsSentence } from '#lib/dashboard/states.ts';
	import type { Channel, CompanyGroup, OverviewFilter, StateGroup } from '#lib/dashboard/types.ts';
	import { useUi } from '#lib/dashboard/ui.svelte.ts';
	import { untrack } from 'svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const ui = useUi();

	// The first paint uses the load data; the effect below takes over after that.
	let overview = $state(untrack(() => structuredClone(data.overview)));
	let flash = $state<Record<string, number>>({});

	// A new load (filter change) replaces the local copy.
	$effect.pre(() => {
		const fresh = structuredClone(data.overview);
		untrack(() => (overview = fresh));
	});

	$effect(() => {
		const filter: OverviewFilter = { state: data.filter.state, channel: data.filter.channel };
		const live = connectStream(filter, (message) => {
			if (message.event === 'snapshot') {
				overview = message.data;
			} else if (message.event === 'order_updated') {
				applyOrderUpdated(overview, message.data, filter);
				const id = message.data.order.session_id;
				flash[id] = (flash[id] ?? 0) + 1;
			}
		});
		return () => live.close();
	});

	const counters: { key: StringKey; group: StateGroup }[] = [
		{ key: 'active_now', group: 'active' },
		{ key: 'waiting_for_confirmation', group: 'waiting' },
		{ key: 'confirmed', group: 'confirmed' },
		{ key: 'needs_attention', group: 'attention' }
	];

	const channels: { channel: Channel; icon: IconName }[] = [
		{ channel: 'phone', icon: 'phone' },
		{ channel: 'web_chat', icon: 'chat' },
		{ channel: 'webmcp', icon: 'webmcp' },
		{ channel: 'mcp', icon: 'plug' }
	];

	const chips: { key: StringKey; state: StateGroup | null }[] = [
		{ key: 'filter_all', state: null },
		{ key: 'filter_active', state: 'active' },
		{ key: 'filter_waiting', state: 'waiting' },
		{ key: 'filter_confirmed', state: 'confirmed' },
		{ key: 'filter_attention', state: 'attention' }
	];

	function hrefFor(filter: OverviewFilter): string {
		const params = new URLSearchParams();
		if (filter.state) params.set('state', filter.state);
		if (filter.channel) params.set('channel', filter.channel);
		const query = params.toString();
		return query ? `/dashboard?${query}` : '/dashboard';
	}

	/** "Avoids milk and nuts, +358 40 *** **12", or "webshop session" without a contact. */
	function companyLine(company: CompanyGroup): string {
		const identity = company.orders.find((o) => o.identity_masked)?.identity_masked;
		return `${exclusionsSentence(company.exclusions, ui.lang)}, ${identity ?? t('webshop_session', ui.lang)}`;
	}
</script>

<svelte:head>
	<title>S.I.MO {t('live_dashboard', ui.lang)}</title>
</svelte:head>

<div class="band">
	<div class="wrap hero">
		<div class="intro">
			<h1 class="hd">{t('overview_title', ui.lang)}</h1>
			<p>{t('overview_lead', ui.lang)}</p>
		</div>
		<div class="stats">
			{#each counters as c (c.group)}
				<div class="stat">
					<span class="stat-n n-{c.group}">{overview.totals[c.group]}</span>
					<span class="stat-l">{t(c.key, ui.lang)}</span>
				</div>
			{/each}
			<div class="stat">
				<span class="stat-n">{formatMoney(overview.totals.confirmed_cents, ui.lang)}</span>
				<span class="stat-l">{t('confirmed_value', ui.lang)}</span>
			</div>
		</div>
		<div class="chans">
			{#each channels as c (c.channel)}
				{@const on = data.filter.channel === c.channel}
				<a
					class="chan"
					class:on
					href={hrefFor({ state: data.filter.state, channel: on ? null : c.channel })}
					aria-current={on ? 'true' : undefined}
					data-sveltekit-noscroll
				>
					<span class="chan-ico ico-{c.channel}"><Icon name={c.icon} size={18} /></span>
					<span class="chan-text">
						<b>{t(`ch_${c.channel}`, ui.lang)}</b>
						<span>{t(`ch_${c.channel}_sub`, ui.lang)}</span>
					</span>
					<b class="hd chan-n">{overview.totals.by_channel[c.channel] ?? 0}</b>
				</a>
			{/each}
		</div>
	</div>
</div>

<main class="wrap list">
	<nav class="chips" aria-label="Filter">
		{#each chips as chip (chip.key)}
			{@const on = data.filter.state === chip.state}
			<a
				class="chip"
				class:on
				href={hrefFor({ state: chip.state, channel: data.filter.channel })}
				aria-current={on ? 'true' : undefined}
				data-sveltekit-noscroll>{t(chip.key, ui.lang)}</a
			>
		{/each}
	</nav>

	{#each overview.companies as company (company.name)}
		<section class="company" data-testid="company">
			<div class="co">
				<h2 class="hd">{company.name}</h2>
				<span>{companyLine(company)}</span>
			</div>
			<div class="grid">
				{#each company.orders as order (order.session_id)}
					{#key flash[order.session_id]}
						<OrderCardView {order} flash={!!flash[order.session_id]} />
					{/key}
				{/each}
			</div>
		</section>
	{:else}
		<p class="empty">{t('no_orders', ui.lang)}</p>
	{/each}
</main>

<style>
	.hero {
		padding-top: 28px;
		padding-bottom: 28px;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.intro {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	h1 {
		font-size: 52px;
		line-height: 1;
		color: var(--d-petrol);
	}
	.intro p {
		margin: 0;
		font-size: 17px;
		color: var(--d-ink-2);
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
		gap: 12px;
	}
	.stat {
		background: #fff;
		border-radius: 10px;
		padding: 16px 18px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.stat-n {
		font-family: var(--d-font-head);
		font-weight: 700;
		font-size: 48px;
		line-height: 1;
		font-variant-numeric: tabular-nums;
	}
	.n-active {
		color: var(--d-petrol);
	}
	.n-waiting {
		color: var(--d-waiting-num);
	}
	.n-confirmed {
		color: var(--d-confirmed-fg);
	}
	.n-attention {
		color: var(--d-attention-fg);
	}
	.stat-l {
		font-size: 15px;
		font-weight: 600;
	}
	.chans {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
		gap: 10px;
	}
	.chan {
		background: #fff;
		border: 1px solid var(--d-line);
		border-radius: 10px;
		padding: 12px 14px;
		display: flex;
		align-items: center;
		gap: 12px;
		min-width: 0;
		color: inherit;
		text-decoration: none;
	}
	.chan:hover,
	.chan.on {
		border-color: var(--d-petrol);
		color: inherit;
	}
	.chan.on {
		box-shadow: inset 0 0 0 1px var(--d-petrol);
	}
	.chan-ico {
		width: 38px;
		height: 38px;
		flex-shrink: 0;
		border-radius: 19px;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.ico-phone {
		background: #e3edf2;
		color: var(--d-petrol);
	}
	.ico-web_chat {
		background: #f4f0f9;
		color: var(--d-chat-fg);
	}
	.ico-webmcp {
		background: #fff3b0;
		color: var(--d-waiting-fg);
	}
	.ico-mcp {
		background: #e6f2c2;
		color: var(--d-confirmed-fg);
	}
	.chan-text {
		display: flex;
		flex-direction: column;
		flex-grow: 1;
		min-width: 0;
	}
	.chan-text b {
		font-size: 15px;
	}
	.chan-text span {
		font-size: 13px;
		color: var(--d-muted);
	}
	.chan-n {
		font-size: 30px;
	}
	.list {
		padding-top: 24px;
		padding-bottom: 40px;
		display: flex;
		flex-direction: column;
		gap: 26px;
	}
	.chips {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
	}
	.chip {
		height: 40px;
		padding: 0 16px;
		border-radius: 20px;
		background: var(--d-chip);
		color: var(--d-petrol);
		font-size: 15px;
		font-weight: 700;
		display: inline-flex;
		align-items: center;
		text-decoration: none;
	}
	.chip.on {
		background: var(--d-petrol);
		color: #fff;
	}
	.company {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.co {
		display: flex;
		align-items: baseline;
		gap: 12px;
		flex-wrap: wrap;
	}
	.co h2 {
		font-size: 30px;
	}
	.co span {
		font-size: 14px;
		color: var(--d-muted);
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: 14px;
	}
	.empty {
		font-size: 17px;
		color: var(--d-muted);
	}
	@media (max-width: 640px) {
		h1 {
			font-size: 40px;
		}
		.grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
