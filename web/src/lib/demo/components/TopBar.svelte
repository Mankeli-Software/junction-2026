<script lang="ts">
	/** Dark petrol bar with S.I.MO and the EN/FI toggle (design 00, 01, 10; the agent is always written S.I.MO). */
	import { t } from '../i18n';
	import type { Lang } from '../types';

	let {
		lang,
		langHref,
		wide = false
	}: { lang: Lang; langHref: (lang: Lang) => string; wide?: boolean } = $props();
</script>

<header class="bar" class:wide>
	<div class="inner">
		<span class="hd brand">{t(lang, 'brand')}</span>
		<nav class="langs" aria-label={t(lang, 'language')}>
			{#each ['en', 'fi'] as const as option (option)}
				<a
					href={langHref(option)}
					class:active={lang === option}
					aria-current={lang === option ? 'true' : undefined}
					hreflang={option}
					data-sveltekit-reset="false"
					data-sveltekit-replacestate>{option.toUpperCase()}</a
				>
			{/each}
		</nav>
	</div>
</header>

<style>
	.bar {
		background: var(--petrol);
		color: #fff;
		flex-shrink: 0;
	}
	.inner {
		height: 52px;
		padding: 0 20px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
	}
	.wide .inner {
		max-width: 1200px;
		margin: 0 auto;
		height: 56px;
		padding: 0 32px;
	}
	.brand {
		font-size: 22px;
		color: #fff;
	}
	.wide .brand {
		font-size: 24px;
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
