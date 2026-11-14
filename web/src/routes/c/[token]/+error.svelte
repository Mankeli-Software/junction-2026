<script lang="ts">
	/** Unknown or invalid confirmation link (spec §3): say so, with no details about why. */
	import { page } from '$app/state';
	import TopBar from '#lib/confirmation/components/TopBar.svelte';
	import { t } from '#lib/confirmation/i18n.js';
	import type { Lang } from '#lib/confirmation/types.js';

	const lang: Lang = $derived(page.url.searchParams.get('lang') === 'fi' ? 'fi' : 'en');
</script>

<svelte:head>
	<title>S.I.MO</title>
	<meta name="referrer" content="no-referrer" />
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="page">
	<TopBar {lang} url={page.url} />
	<section class="closed" data-testid="invalid-link">
		<h1 class="hd">
			{page.status === 404 ? t(lang, 'invalidTitle') : t(lang, 'errorGeneric')}
		</h1>
	</section>
</div>

<style>
	.page {
		max-width: 480px;
		min-height: 100vh;
		margin: 0 auto;
		background: var(--page);
	}
	.closed {
		background: var(--lavender);
		padding: 32px 20px;
	}
	h1 {
		font-size: 34px;
		line-height: 1.05;
		color: var(--petrol);
	}
</style>
