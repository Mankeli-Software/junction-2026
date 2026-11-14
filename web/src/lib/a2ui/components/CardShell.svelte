<script lang="ts">
	/**
	 * The frame every chat card shares (UI-01, UI-02): eyebrow, title, and the
	 * loading (grey bars, aria-busy), could-not-load (with Try again) and not-found states.
	 */
	import type { Snippet } from 'svelte';
	import { chatContext } from '../context';
	import { t } from '../i18n';
	import type { LoadStatus } from '../load.svelte';
	import Icon from './Icon.svelte';

	let {
		eyebrow,
		title,
		status,
		testid,
		variant = 'plain',
		onretry,
		aside,
		children
	}: {
		eyebrow?: string;
		title?: string;
		status: LoadStatus;
		testid: string;
		/** `done`: the green frame of a chosen card; `alert`: the red frame of a rejection; `faded`: replaced. */
		variant?: 'plain' | 'done' | 'alert' | 'faded';
		onretry?: () => void;
		/** Shown at the end of the title row (the quote's total). */
		aside?: Snippet;
		children: Snippet;
	} = $props();
	const { lang } = chatContext();
	const L = $derived(lang());
</script>

<section class="card {variant}" data-testid={testid} data-status={status} aria-busy={status === 'loading'}>
	{#if eyebrow}<span class="eyebrow">{eyebrow}</span>{/if}
	{#if title}
		<div class="title-row">
			<h3 class="title">{title}</h3>
			{#if aside && status === 'ready'}{@render aside()}{/if}
		</div>
	{/if}
	{#if status === 'loading'}
		<span class="visually-hidden">{t(L, 'loading')}</span>
		<span class="bar" style="width: 70%"></span>
		<span class="bar"></span>
		<span class="bar" style="width: 85%"></span>
		<span class="bar" style="width: 50%"></span>
	{:else if status === 'error'}
		<p class="state error" role="alert"><Icon name="alert" stroke="var(--red)" />{t(L, 'loadFailed')}</p>
		{#if onretry}
			<button type="button" class="pill" onclick={onretry}>{t(L, 'tryAgain')}</button>
		{/if}
	{:else if status === 'notfound'}
		<p class="state">{t(L, 'notFound')}</p>
	{:else}
		{@render children()}
	{/if}
</section>

<style>
	.card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
		font-size: 15px;
		line-height: 1.4;
		color: var(--ink);
	}
	.card.done {
		border: 2px solid var(--ok-border);
	}
	.card.alert {
		border-color: #e8b3ad;
	}
	.card.faded {
		opacity: 0.75;
	}
	.eyebrow {
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 13px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: var(--muted);
	}
	.eyebrow + .title-row {
		margin-top: -6px;
	}
	.title-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 10px;
	}
	.title {
		margin: 0;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 26px;
		line-height: 1;
		letter-spacing: -0.2px;
		color: var(--petrol);
	}
	.bar {
		display: block;
		height: 14px;
		border-radius: 7px;
		background: var(--chip);
	}
	.state {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}
	.state.error {
		display: flex;
		gap: 8px;
		align-items: center;
		color: var(--red);
		font-weight: 600;
	}
	.pill {
		align-self: flex-start;
		min-height: 42px;
		padding: 0 16px;
		border-radius: 21px;
		border: 2px solid var(--petrol);
		background: var(--card);
		color: var(--petrol);
		font-size: 15px;
		font-weight: 700;
		cursor: pointer;
	}
</style>
