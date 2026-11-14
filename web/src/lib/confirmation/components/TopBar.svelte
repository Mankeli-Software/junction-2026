<script lang="ts" module>
	/** One home for every visitor: the phone app, which also serves a link opened on another device. */
	export function homeHref(lang: 'en' | 'fi'): string {
		return lang === 'fi' ? '/phone?lang=fi' : '/phone';
	}
</script>

<script lang="ts">
	/** Dark top bar with S.I.MO and the language toggle (or the company name on the receipt). */
	import { pageUrl, type PageUrl } from '../forms.svelte';
	import { t } from '../i18n';
	import type { Lang } from '../types';

	let { lang, url, right = null }: { lang: Lang; url: PageUrl; right?: string | null } = $props();
</script>

<header class="bar">
	<a class="hd brand" href={homeHref(lang)}>S.I.MO</a>
	{#if right}
		<span class="right">{right}</span>
	{:else}
		<nav class="langs" aria-label={t(lang, 'language')}>
			{#each ['en', 'fi'] as const as option (option)}
				<a
					href={pageUrl(url, { lang: option })}
					class:active={lang === option}
					aria-current={lang === option ? 'true' : undefined}
					hreflang={option}
					data-sveltekit-reset="false"
					data-sveltekit-replacestate>{option.toUpperCase()}</a
				>
			{/each}
		</nav>
	{/if}
</header>

<style>
	.bar {
		background: var(--petrol);
		color: #fff;
		height: 52px;
		padding: 0 20px;
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.brand {
		font-size: 22px;
		color: #fff;
		text-decoration: none;
	}
	.right {
		font-size: 15px;
		font-weight: 500;
	}
	.langs {
		display: flex;
		gap: 4px;
		font-size: 14px;
		font-weight: 600;
	}
	.langs a {
		color: #fff;
		text-decoration: none;
		border-radius: 4px;
		padding: 4px 8px;
	}
	.langs a.active {
		background: #fff;
		color: var(--petrol);
	}
</style>
