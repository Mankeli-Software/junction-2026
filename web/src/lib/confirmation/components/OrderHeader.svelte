<script lang="ts">
	/** "Your order": company and call time, delivery date, total, kitchen exclusions (spec §4.1). */
	import { date, money, time } from '../format';
	import { channelText, t } from '../i18n';
	import type { ConfirmationView, Lang } from '../types';

	let { view, lang }: { view: ConfirmationView; lang: Lang } = $props();
</script>

<section class="hero">
	<div class="title">
		<h1 class="hd">{t(lang, 'yourOrder')}</h1>
		<span class="sub"
			>{view.company.name}, {channelText(lang, view.session.channel, time(view.session.started_at, lang))}</span
		>
	</div>
	<div class="facts">
		<div class="fact">
			<span class="label">{t(lang, 'delivery')}</span>
			<span class="value">{date(view.quote.delivery.date, lang)}</span>
		</div>
		<div class="fact">
			<span class="label">{t(lang, 'totalInclVat')}</span>
			<span class="value total" data-testid="total">{money(view.quote.total_cents)}</span>
		</div>
	</div>
	{#if view.exclusions.length > 0}
		<ul class="chips" aria-label={t(lang, 'exclusions')}>
			{#each view.exclusions as exclusion (exclusion.key)}
				<li>{exclusion.label[lang]}</li>
			{/each}
		</ul>
	{/if}
	{#if view.expires_at && view.state === 'ready'}
		<span class="sub">{t(lang, 'validUntil', { time: time(view.expires_at, lang) })}</span>
	{/if}
</section>

<style>
	.hero {
		background: var(--lavender);
		padding: 20px 20px 18px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.title {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	h1 {
		font-size: 38px;
		line-height: 1;
		color: var(--petrol);
	}
	.sub {
		font-size: 15px;
		color: var(--muted);
	}
	.facts {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px;
	}
	.fact {
		background: var(--card);
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
	.chips {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		margin: 0;
		padding: 0;
		list-style: none;
	}
	.chips li {
		font-size: 13px;
		font-weight: 600;
		background: var(--card);
		border-radius: 12px;
		padding: 4px 10px;
		color: var(--petrol);
	}
</style>
