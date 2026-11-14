<script lang="ts">
	import { formatDemoTime } from '../format';
	import { t } from '../i18n';
	import type { Lang } from '../types';

	interface Props {
		lang: Lang;
		connected: boolean;
		businessNow: string | null;
		onlang: (lang: Lang) => void;
	}

	let { lang, connected, businessNow, onlang }: Props = $props();
</script>

<header class="top">
	<div class="wrap row">
		<div class="brand">
			<span class="hd name">S.I.MO</span>
			<a href="/dashboard" class="sub">{t('live_dashboard', lang)}</a>
		</div>
		<div class="right">
			<span class="live" class:off={!connected} role="status">
				<span class="dot"></span>{connected ? t('live', lang) : t('reconnecting', lang)}
			</span>
			{#if businessNow}
				<span class="clock">{t('demo_time', lang)} {formatDemoTime(businessNow, lang)}</span>
			{/if}
			<span class="langs" role="group" aria-label="Language">
				<button type="button" class:on={lang === 'en'} aria-pressed={lang === 'en'} onclick={() => onlang('en')}>EN</button>
				<button type="button" class:on={lang === 'fi'} aria-pressed={lang === 'fi'} onclick={() => onlang('fi')}>FI</button>
			</span>
		</div>
	</div>
</header>

<style>
	.top {
		background: var(--d-petrol);
		color: #fff;
	}
	.row {
		min-height: 56px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.name {
		font-size: 24px;
		color: #fff;
	}
	.top .sub {
		font-size: 15px;
		color: var(--d-on-petrol-muted);
		margin-left: 8px;
	}
	.top .sub:hover {
		color: #fff;
	}
	.right {
		display: flex;
		align-items: center;
		gap: 18px;
		font-size: 14px;
		flex-wrap: wrap;
	}
	.live {
		display: flex;
		align-items: center;
		gap: 6px;
		font-weight: 700;
	}
	.dot {
		width: 9px;
		height: 9px;
		border-radius: 5px;
		background: var(--d-lime);
	}
	.live.off {
		color: var(--d-on-petrol-muted);
	}
	.live.off .dot {
		background: #9aa9b1;
	}
	.clock {
		color: var(--d-on-petrol-muted);
	}
	.langs {
		display: flex;
		gap: 4px;
		font-weight: 600;
	}
	.langs button {
		background: transparent;
		color: #fff;
		border: 0;
		border-radius: 4px;
		padding: 4px 8px;
		font: inherit;
		cursor: pointer;
	}
	.langs button.on {
		background: #fff;
		color: var(--d-petrol);
	}
</style>
