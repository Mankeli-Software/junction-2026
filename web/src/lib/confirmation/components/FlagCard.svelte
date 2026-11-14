<script lang="ts">
	/**
	 * One flag in "Check these first" (spec §4.2). Unacknowledged flags have a
	 * "Got it" button, or a choice between options (keep the rounded amount or take
	 * an exact fit). Picking the option already in the quote acknowledges the flag;
	 * picking another one is an edit that makes a new quote.
	 */
	import { enhance } from '$app/forms';
	import { actionUrl, submitWithPending, ui, type PageUrl } from '../forms.svelte';
	import { t } from '../i18n';
	import type { Flag, Lang } from '../types';
	import Icon from './Icon.svelte';

	let { flag, lang, quoteHash, url }: { flag: Flag; lang: Lang; quoteHash: string; url: PageUrl } = $props();
</script>

<article
	class="flag"
	class:done={flag.acknowledged}
	class:choice={!flag.acknowledged && flag.choice}
	data-testid="flag"
	data-flag-key={flag.key}
>
	<div class="head">
		<div class="ico">
			{#if flag.acknowledged}
				<Icon name="check" weight={3} />
			{:else if flag.kind === 'rounded_up'}
				<Icon name="up" size={18} />
			{:else}
				<Icon name="alert" size={18} />
			{/if}
		</div>
		<div class="words">
			<span class="title">
				{flag.title[lang]}
				{#if flag.is_new && !flag.acknowledged}<span class="new">{t(lang, 'newFlag')}</span>{/if}
			</span>
			<span class="text">
				{#if flag.line_id}
					<a href="#line-{flag.line_id}">{flag.text[lang]}</a>
				{:else}
					{flag.text[lang]}
				{/if}
			</span>
			{#if flag.acknowledged}<span class="checked">{t(lang, 'checked')}</span>{/if}
		</div>
	</div>

	{#if !flag.acknowledged}
		{#if flag.choice}
			<div class="options">
				{#each flag.choice.options as option (option.id)}
					{#if option.current || !option.alternative_id || !flag.line_id}
						<form method="POST" action={actionUrl(url, 'acknowledge')} use:enhance={submitWithPending}>
							<input type="hidden" name="quote_hash" value={quoteHash} />
							<input type="hidden" name="flag_key" value={flag.key} />
							<button class="opt" class:current={option.current} disabled={ui.pending}>
								<b>{option.title[lang]}</b><span>{option.text[lang]}</span>
							</button>
						</form>
					{:else}
						<form method="POST" action={actionUrl(url, 'edit')} use:enhance={submitWithPending}>
							<input type="hidden" name="quote_hash" value={quoteHash} />
							<input type="hidden" name="op" value="choose_alternative" />
							<input type="hidden" name="line_id" value={flag.line_id} />
							<input type="hidden" name="alternative_id" value={option.alternative_id} />
							<button class="opt" disabled={ui.pending}>
								<b>{option.title[lang]}</b><span>{option.text[lang]}</span>
							</button>
						</form>
					{/if}
				{/each}
			</div>
		{:else}
			<form method="POST" action={actionUrl(url, 'acknowledge')} use:enhance={submitWithPending} class="ack">
				<input type="hidden" name="quote_hash" value={quoteHash} />
				<input type="hidden" name="flag_key" value={flag.key} />
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
	.done .head {
		align-items: center;
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
