<script lang="ts">
	import { page } from '$app/state';
	import { t } from '#lib/dashboard/i18n.ts';
	import { useUi } from '#lib/dashboard/ui.svelte.ts';

	const ui = useUi();
	const notFound = $derived(page.status === 404);
</script>

<svelte:head>
	<title>S.I.MO {t(notFound ? 'not_found_title' : 'error_title', ui.lang)}</title>
</svelte:head>

<main class="wrap box">
	<h1 class="hd">{t(notFound ? 'not_found_title' : 'error_title', ui.lang)}</h1>
	<p>{t(notFound ? 'not_found_text' : 'error_text', ui.lang)}</p>
	<a href="/dashboard">{t('back_to_all', ui.lang)}</a>
</main>

<style>
	.box {
		padding-top: 48px;
		padding-bottom: 48px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		align-items: flex-start;
	}
	h1 {
		font-size: 44px;
		color: var(--d-petrol);
	}
	p {
		margin: 0;
		font-size: 17px;
		color: var(--d-ink-2);
	}
	a {
		font-size: 16px;
		font-weight: 700;
	}
</style>
