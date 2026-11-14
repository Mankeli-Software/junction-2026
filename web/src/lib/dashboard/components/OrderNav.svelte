<script lang="ts">
	import type { Snippet } from 'svelte';
	import { shortSessionId } from '../format';
	import { t } from '../i18n';
	import { useUi } from '../ui.svelte';

	interface Props {
		sessionId: string;
		orderNumber: string | null;
		current: 'summary' | 'flow' | 'audit';
		children: Snippet;
	}

	let { sessionId, orderNumber, current, children }: Props = $props();
	const ui = useUi();

	const base = $derived(`/dashboard/${encodeURIComponent(sessionId)}`);
	const orderLabel = $derived(
		orderNumber ? `${t('order', ui.lang)} ${orderNumber}` : `${t('session', ui.lang)} ${shortSessionId(sessionId)}`
	);
	const tabs = $derived([
		{ key: 'summary', href: base, label: t('tab_summary', ui.lang) },
		{ key: 'flow', href: `${base}/flow`, label: t('tab_flow', ui.lang) },
		{ key: 'audit', href: `${base}/audit`, label: t('tab_audit', ui.lang) }
	] as const);
	const here = $derived(tabs.find((tab) => tab.key === current)!);
</script>

<div class="band">
	<div class="wrap inner">
		<nav class="crumbs" aria-label="Breadcrumb">
			<a href="/dashboard">{t('all_orders', ui.lang)}</a>
			<span class="sep" aria-hidden="true">›</span>
			{#if current === 'summary'}
				<span class="here" aria-current="page">{orderLabel}</span>
			{:else}
				<a href={base}>{orderLabel}</a>
				<span class="sep" aria-hidden="true">›</span>
				<span class="here" aria-current="page">{here.label}</span>
			{/if}
		</nav>
		{@render children()}
		<nav class="tabs" aria-label="Order views">
			{#each tabs as tab (tab.key)}
				<a class="tab" href={tab.href} aria-current={tab.key === current ? 'page' : undefined}>{tab.label}</a>
			{/each}
		</nav>
	</div>
</div>

<style>
	.inner {
		padding-top: 18px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
</style>
