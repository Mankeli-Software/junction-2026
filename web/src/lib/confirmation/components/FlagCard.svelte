<script lang="ts">
	/**
	 * One flag in "Check these first" (spec §4.2). A flag that needs a check has a
	 * "Got it" button, or for a `choose` flag one button per option (keep the rounded
	 * amount or take an exact fit). Picking an option acknowledges the flag; an option
	 * that changes the order makes a new quote. Flags whose code needs no check
	 * (policy/messages.yaml `ack: false`) are shown for information only.
	 */
	import { enhance } from '$app/forms';
	import { flagTitle } from '../display';
	import { money } from '../format';
	import { actionUrl, submitWithPending, ui, type PageUrl } from '../forms.svelte';
	import { t } from '../i18n';
	import type { Lang, QuoteLine, ViewFlag } from '../types';
	import Icon from './Icon.svelte';

	let {
		flag,
		lines,
		lang,
		quoteHash,
		url
	}: { flag: ViewFlag; lines: QuoteLine[]; lang: Lang; quoteHash: string; url: PageUrl } = $props();

	const done = $derived(flag.acknowledged_at !== null);
	const open = $derived(flag.requires_ack && !done);
</script>

<article
	class="flag"
	class:done
	class:choice={open && flag.kind === 'choose'}
	data-testid="flag"
	data-flag-key={flag.flag_key}
>
	<div class="head">
		<div class="ico">
			{#if done}
				<Icon name="check" weight={3} />
			{:else if flag.code === 'ROUNDED_UP'}
				<Icon name="up" size={18} />
			{:else}
				<Icon name="alert" size={18} />
			{/if}
		</div>
		<div class="words">
			<span class="title">
				{flagTitle(flag, lines, lang)}
				{#if flag.is_new && !done}<span class="new">{t(lang, 'newFlag')}</span>{/if}
			</span>
			<span class="text">
				{#if flag.line_ids.length === 1}
					<a href="#line-{flag.line_ids[0]}">{flag.text[lang]}</a>
				{:else}
					{flag.text[lang]}
				{/if}
			</span>
			{#if done}<span class="checked">{t(lang, 'checked')}</span>{/if}
		</div>
	</div>

	{#if open}
		{#if flag.kind === 'choose' && flag.options.length > 0}
			<div class="options">
				{#each flag.options as option (option.option_id)}
					<form method="POST" action={actionUrl(url, 'acknowledge')} use:enhance={submitWithPending}>
						<input type="hidden" name="quote_hash" value={quoteHash} />
						<input type="hidden" name="flag_key" value={flag.flag_key} />
						<input type="hidden" name="option_id" value={option.option_id} />
						<button
							class="opt"
							class:current={option.option_id === flag.current_option_id}
							disabled={ui.pending}
						>
							<b>{option.label[lang]}</b><span>{money(option.line_total_cents)}</span>
						</button>
					</form>
				{/each}
			</div>
		{:else}
			<form method="POST" action={actionUrl(url, 'acknowledge')} use:enhance={submitWithPending} class="ack">
				<input type="hidden" name="quote_hash" value={quoteHash} />
				<input type="hidden" name="flag_key" value={flag.flag_key} />
				<button class="ok" disabled={ui.pending}>{t(lang, 'gotIt')}</button>
			</form>
		{/if}
	{/if}
</article>

<style>
	.flag {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.flag.choice {
		border: 2px solid var(--amber);
	}
	.flag.done {
		background: var(--ok-bg);
		border-color: var(--ok-border);
	}
	.head {
		display: flex;
		gap: 10px;
		align-items: flex-start;
	}
	.ico {
		width: 32px;
		height: 32px;
		flex-shrink: 0;
		border-radius: 16px;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--yellow-soft);
		color: var(--ink);
	}
	.done .ico {
		background: var(--lime);
	}
	.words {
		display: flex;
		flex-direction: column;
		gap: 1px;
		flex-grow: 1;
		min-width: 0;
	}
	.title {
		font-weight: 700;
		font-size: 16px;
	}
	.text {
		font-size: 14px;
		color: var(--muted);
	}
	.text a {
		color: inherit;
		text-decoration: none;
	}
	.text a:hover {
		text-decoration: underline;
	}
	.checked {
		font-size: 13px;
		font-weight: 700;
		color: var(--lime-text);
	}
	.new {
		font-family: var(--font-head);
		font-size: 12px;
		letter-spacing: 0.4px;
		text-transform: uppercase;
		background: var(--yellow);
		padding: 1px 6px;
		border-radius: 3px;
		margin-left: 4px;
		vertical-align: 2px;
	}
	.options {
		display: flex;
		gap: 8px;
	}
	.options form {
		flex: 1;
		min-width: 0;
		display: flex;
	}
	.opt {
		flex: 1;
		min-width: 0;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		background: var(--card);
		padding: 10px;
		text-align: left;
		font-size: 14px;
		color: var(--ink);
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.opt span {
		color: var(--muted);
	}
	.opt.current {
		border: 2px solid var(--petrol);
	}
	.ack {
		display: flex;
		justify-content: flex-end;
	}
	.ok {
		height: 40px;
		padding: 0 16px;
		border-radius: 20px;
		border: 2px solid var(--petrol);
		background: var(--card);
		color: var(--petrol);
		font-size: 15px;
		font-weight: 700;
		cursor: pointer;
	}
	button:disabled {
		cursor: progress;
		opacity: 0.7;
	}
</style>
