<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import '#lib/dashboard/dashboard.css';
	import Header from '#lib/dashboard/components/Header.svelte';
	import { readStoredLang, resolveLang, storeLang } from '#lib/dashboard/i18n.ts';
	import { connection } from '#lib/dashboard/live.svelte.ts';
	import type { Lang } from '#lib/dashboard/types.ts';
	import { createUi } from '#lib/dashboard/ui.svelte.ts';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	// The server renders English unless ?lang=fi; the stored choice applies after hydration.
	const ui = createUi(resolveLang(page.url.searchParams.get('lang'), null));

	onMount(() => {
		ui.lang = resolveLang(page.url.searchParams.get('lang'), readStoredLang());
		ui.now = Date.now();
		const ticker = setInterval(() => (ui.now = Date.now()), 1000);
		return () => clearInterval(ticker);
	});

	$effect(() => {
		document.documentElement.lang = ui.lang;
	});

	function setLang(lang: Lang) {
		ui.lang = lang;
		storeLang(lang);
		if (page.url.searchParams.has('lang')) {
			const url = new URL(page.url.href);
			url.searchParams.delete('lang');
			goto(url, { replace: true, reset: false });
		}
	}
</script>

<svelte:head>
	<link rel="preconnect" href="https://fonts.googleapis.com" />
	<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous" />
	<link
		href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Figtree:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<div class="dash">
	<Header lang={ui.lang} connected={connection.connected} businessNow={connection.businessNow ?? page.data.overview?.business_now ?? null} onlang={setLang} />
	{@render children()}
</div>

<style>
	:global(body) {
		margin: 0;
		background: var(--d-page);
	}
</style>
