<script lang="ts">
	/** Cancelled and expired pages (spec §3): say what happened and what to do next. */
	import { time } from '../format';
	import { t } from '../i18n';
	import type { ConfirmationView, Lang } from '../types';

	let { view, lang }: { view: ConfirmationView; lang: Lang } = $props();
</script>

<section class="closed" data-testid="closed-state">
	{#if view.state === 'cancelled'}
		<h1 class="hd">{t(lang, 'cancelledTitle')}</h1>
		<p>{t(lang, 'cancelledText')}</p>
	{:else}
		<h1 class="hd">{t(lang, 'expiredTitle')}</h1>
		<p>{t(lang, 'expiredText', { time: view.expires_at ? time(view.expires_at, lang) : '' })}</p>
	{/if}
</section>

<style>
	.closed {
		background: var(--lavender);
		padding: 32px 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	h1 {
		font-size: 38px;
		line-height: 1;
		color: var(--petrol);
	}
	p {
		margin: 0;
		font-size: 16px;
		color: var(--muted-2);
	}
</style>
