<script lang="ts">
	import { formatDay, formatMoney } from '../format';
	import { pick, t } from '../i18n';
	import { connectorNote, isActive, isAttention } from '../states';
	import type { OrderCard } from '../types';
	import { useUi } from '../ui.svelte';
	import ChannelBadge from './ChannelBadge.svelte';
	import StatusPill from './StatusPill.svelte';

	let { order, flash = false }: { order: OrderCard; flash?: boolean } = $props();
	const ui = useUi();

	const active = $derived(isActive(order.state));
	const attention = $derived(isAttention(order.state));
	const linesText = $derived.by(() => {
		const n = order.line_count;
		let text = `${n} ${t(n === 1 ? 'line' : 'lines', ui.lang)}`;
		if (order.recipe_count) text = `${order.recipe_count} ${t('recipes', ui.lang)}, ${text}`;
		if (active) text = `${text} ${t('lines_so_far', ui.lang)}`;
		return text;
	});
	const flagsText = $derived.by(() => {
		const n = order.flags.length;
		if (n === 0) return '';
		const words = order.flags.map((f) => pick(f.short, ui.lang)).join(', ');
		return `${n} ${t(n === 1 ? 'flag' : 'flags', ui.lang)}: ${words}`;
	});
</script>

<a href="/dashboard/{encodeURIComponent(order.session_id)}" class="ocard" data-testid="order-card" class:active class:attention class:flash>
	<div class="top">
		<StatusPill state={order.state} since={order.state_since} channel={order.channel} />
		<ChannelBadge channel={order.channel} client={order.client} />
	</div>
	<span class="title">{pick(order.title, ui.lang)}</span>
	{#if active && order.step_text}
		<span class="step">{pick(order.step_text, ui.lang)}</span>
	{/if}
	<div class="meta">
		{#if order.order_number}<span class="num" data-testid="order-number">{order.order_number}</span>{/if}
		{#if order.line_count > 0}<span>{linesText}</span>{/if}
		<!-- The API sends 0 for a quote with no lines (a question to the buyer): no total then. -->
		{#if order.total_cents !== null && (order.total_cents > 0 || order.line_count > 0)}<b>{formatMoney(order.total_cents, ui.lang)}</b>{/if}
		{#if order.delivery_date}<span>{formatDay(order.delivery_date, ui.lang)}</span>{/if}
	</div>
	{#if flagsText}<span class="flags">{flagsText}</span>{/if}
	{#if attention && order.next_step}<span class="next">{pick(order.next_step, ui.lang)}</span>{/if}
	{#if order.channel === 'mcp'}<span class="note">{connectorNote(order.client, ui.lang)}</span>{/if}
</a>

<style>
	.ocard {
		background: #fff;
		border: 1px solid var(--d-line);
		border-radius: 10px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		text-decoration: none;
		color: var(--d-ink);
		transition: border-color 0.2s;
		/* A grid item: without this, long content widens the card past its column. */
		min-width: 0;
	}
	.ocard:hover {
		border-color: var(--d-petrol);
		color: var(--d-ink);
	}
	.ocard.active {
		border: 2px solid var(--d-petrol);
		padding: 15px;
		box-shadow: 0 6px 18px rgba(30, 79, 104, 0.14);
	}
	.ocard.attention {
		border-color: var(--d-attention-border);
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
	}
	.title {
		font-size: 18px;
		font-weight: 700;
	}
	.step {
		font-size: 15px;
		color: var(--d-petrol);
		font-weight: 600;
	}
	.meta {
		display: flex;
		gap: 16px;
		font-size: 14px;
		color: var(--d-muted);
		flex-wrap: wrap;
	}
	.meta b {
		color: var(--d-ink);
	}
	.num {
		font-weight: 600;
		color: var(--d-petrol);
	}
	.flags {
		font-size: 14px;
		color: var(--d-waiting-fg);
		font-weight: 600;
	}
	.next {
		font-size: 14px;
		color: var(--d-attention-fg);
		font-weight: 600;
	}
	.note {
		font-size: 13px;
		color: var(--d-muted);
	}
</style>
