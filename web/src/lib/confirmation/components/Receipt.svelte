<script lang="ts">
	/** "Order received" (screen 22, spec §7): stays readable at the same link after confirming. */
	import { quantityText } from '../display';
	import { date, money, time } from '../format';
	import { t } from '../i18n';
	import type { ConfirmationView, Lang, Order } from '../types';
	import Icon from './Icon.svelte';
	import { homeHref } from './TopBar.svelte';

	let { view, order, lang }: { view: ConfirmationView; order: Order; lang: Lang } = $props();

	const checked = $derived(order.acknowledged.length);
</script>

<section class="hero">
	<div class="tick"><Icon name="check" size={34} weight={2.6} /></div>
	<h1 class="hd">{t(lang, 'orderReceived')}</h1>
	<p data-testid="order-number">
		{t(lang, 'orderConfirmedAt', { number: order.order_number, time: time(order.confirmed_at, lang) })}
	</p>
</section>

<div class="body">
	<div class="facts">
		<div class="fact">
			<span class="label">{t(lang, 'delivery')}</span>
			<span class="value">{view.quote.delivery ? date(view.quote.delivery.earliest, lang) : ''}</span>
		</div>
		<div class="fact">
			<span class="label">{t(lang, 'totalInclVat')}</span>
			<span class="value total">{money(view.quote.total_cents)}</span>
		</div>
	</div>

	<ul class="lines">
		{#each view.lines as line (line.line_id)}
			<li>
				<span class="words"><b>{line.name[lang]}</b><span>{quantityText(line, lang)}</span></span>
				<b>{money(line.line_total_cents)}</b>
			</li>
		{/each}
	</ul>

	{#if checked > 0}
		<p class="checked">
			<Icon name="shield" size={18} />
			{checked === 1 ? t(lang, 'youCheckedOne') : t(lang, 'youChecked', { n: checked })}
		</p>
	{/if}

	<p class="note"><b>{t(lang, 'demoNoteLead')}</b> {t(lang, 'demoNote')}</p>

	<a class="home" href={homeHref(lang)} data-testid="return-home">{t(lang, 'returnHome')}</a>
</div>

<style>
	.hero {
		background: var(--lavender);
		padding: 28px 20px 26px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		text-align: center;
	}
	.tick {
		width: 76px;
		height: 76px;
		border-radius: 38px;
		background: var(--lime);
		color: var(--ink);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	h1 {
		font-size: 42px;
		line-height: 1;
		color: var(--petrol);
	}
	.hero p {
		margin: 0;
		font-size: 16px;
		color: var(--muted-2);
	}
	.body {
		padding: 20px 16px 28px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.facts {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px;
	}
	.fact {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.label {
		font-size: 13px;
		color: var(--muted);
	}
	.value {
		font-weight: 700;
		font-size: 17px;
	}
	.total {
		font-weight: 800;
	}
	.lines {
		list-style: none;
		margin: 0;
		padding: 0 14px;
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 10px;
	}
	.lines li {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		padding: 12px 0;
		border-top: 1px solid var(--divider);
	}
	.lines li:first-child {
		border-top: 0;
	}
	.words {
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.words span {
		color: var(--muted);
		font-size: 15px;
	}
	.checked {
		margin: 0;
		display: flex;
		gap: 8px;
		align-items: center;
		font-size: 14px;
		color: var(--muted-2);
	}
	.home {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 48px;
		border-radius: 8px;
		background: var(--petrol);
		color: #fff;
		font-weight: 700;
		font-size: 16px;
		text-decoration: none;
	}
	.note {
		margin: 24px 0 0;
		background: var(--yellow-note);
		border-radius: 8px;
		padding: 12px 14px;
		font-size: 14px;
	}
</style>
