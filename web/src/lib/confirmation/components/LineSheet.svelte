<script lang="ts">
	/**
	 * The sheet for one line (screen 21, spec §4.3 and §4.4): why this product,
	 * other options, change amount, remove. Opened with ?line=<id>, so it is
	 * server-rendered and works without JavaScript.
	 */
	import { enhance } from '$app/forms';
	import { goto } from '$app/navigation';
	import { askedText, askedUnit, unitPriceText } from '../display';
	import { money, number } from '../format';
	import { actionUrl, pageUrl, submitWithPending, ui, type PageUrl } from '../forms.svelte';
	import { t } from '../i18n';
	import type { Lang, QuoteLine, Text } from '../types';
	import Icon from './Icon.svelte';

	let {
		line,
		lang,
		quoteHash,
		url,
		error
	}: { line: QuoteLine; lang: Lang; quoteHash: string; url: PageUrl; error: Text | null } = $props();

	const closeUrl = $derived(pageUrl(url, { line: null }));
	const quantity = $derived(line.quantity_sales_units);
	const askedAmount = $derived(
		line.asked.unit === 'sales_unit' ? null : `${number(line.quantity_in_asked_unit, lang)} ${askedUnit(line, lang)}`
	);
	// The engine refuses an amount it can't deliver and says why; the page only stops at 1.
	const canLess = $derived(quantity > 1);

	let closeLink: HTMLAnchorElement | undefined = $state();

	$effect(() => {
		closeLink?.focus();
	});

	function onKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') goto(closeUrl, { reset: false, replace: true });
	}
</script>

<svelte:window onkeydown={onKeydown} />

<div class="backdrop">
	<a class="backdrop-link" href={closeUrl} tabindex="-1" aria-hidden="true" data-sveltekit-reset="false"></a>
	<div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title" data-testid="line-sheet">
		<div class="grip" aria-hidden="true"></div>
		<div class="top">
			<div class="names">
				<span class="asked">{t(lang, 'youAsked', { asked: askedText(line, lang) })}</span>
				<h2 class="hd" id="sheet-title">{line.name[lang]}</h2>
				<span class="unit">{unitPriceText(line, lang)}</span>
			</div>
			<a class="close" href={closeUrl} bind:this={closeLink} aria-label={t(lang, 'close')} data-sveltekit-reset="false"
				><Icon name="close" size={18} /></a
			>
		</div>

		<section class="trace">
			<h3 class="hd">{t(lang, 'whyThisOne')}</h3>
			<ul>
				<li><b>{line.trace.found}</b><span>{t(lang, 'traceFound')}</span></li>
				{#each line.trace.removed as removed (removed.reason_code)}
					<li><b class="minus">&minus;{removed.count}</b><span>{removed.text[lang]}</span></li>
				{/each}
				<li class="result">
					<b>{line.trace.left}</b><span
						>{t(lang, 'traceLeft')}. {t(lang, 'tracePicked', { rule: line.trace.ranking_rule[lang] })}</span
					>
				</li>
			</ul>
		</section>

		{#if line.alternatives.length > 0}
			<section>
				<h3 class="hd">{t(lang, 'otherOptions')}</h3>
				<div class="alts">
					<div class="alt current" aria-current="true">
						<span class="alt-words"><b>{line.name[lang]}</b><span>{t(lang, 'inYourOrder')}</span></span>
						<b class="alt-price">{money(line.line_total_cents)}</b>
					</div>
					{#each line.alternatives as alt (alt.product_id)}
						<form method="POST" action={actionUrl(url, 'edit')} use:enhance={submitWithPending}>
							<input type="hidden" name="quote_hash" value={quoteHash} />
							<input type="hidden" name="op" value="choose_alternative" />
							<input type="hidden" name="line_id" value={line.line_id} />
							<input type="hidden" name="alternative_id" value={alt.product_id} />
							<button class="alt" disabled={ui.pending}>
								<span class="alt-words"
									><b>{alt.label[lang]}</b><span>&times; {alt.quantity_sales_units}</span></span
								>
								<b class="alt-price">{money(alt.line_total_cents)}</b>
							</button>
						</form>
					{/each}
				</div>
			</section>
		{/if}

		<section>
			<h3 class="hd">{t(lang, 'changeAmount')}</h3>
			<div class="stepper">
				<form method="POST" action={actionUrl(url, 'edit')} use:enhance={submitWithPending}>
					<input type="hidden" name="quote_hash" value={quoteHash} />
					<input type="hidden" name="op" value="set_quantity" />
					<input type="hidden" name="line_id" value={line.line_id} />
					<button
						class="step"
						name="quantity"
						value={quantity - 1}
						disabled={!canLess || ui.pending}
						aria-label={t(lang, 'less')}><Icon name="minus" size={22} weight={2.6} /></button
					>
				</form>
				<div class="amount" aria-live="polite">
					<b data-testid="sheet-quantity">{quantity} {line.sales_unit_label[lang]}</b>
					<span>{askedAmount ? `= ${askedAmount}, ` : ''}{money(line.line_total_cents)}</span>
				</div>
				<form method="POST" action={actionUrl(url, 'edit')} use:enhance={submitWithPending}>
					<input type="hidden" name="quote_hash" value={quoteHash} />
					<input type="hidden" name="op" value="set_quantity" />
					<input type="hidden" name="line_id" value={line.line_id} />
					<button
						class="step"
						name="quantity"
						value={quantity + 1}
						disabled={ui.pending}
						aria-label={t(lang, 'more')}><Icon name="plus" size={22} weight={2.6} /></button
					>
				</form>
			</div>
			{#if error}
				<p class="error" role="alert">{error[lang]}</p>
			{/if}
			<p class="note">{t(lang, 'anyChange')}</p>
		</section>

		<form class="remove" method="POST" action={actionUrl(url, 'edit')} use:enhance={submitWithPending}>
			<input type="hidden" name="quote_hash" value={quoteHash} />
			<input type="hidden" name="op" value="remove" />
			<input type="hidden" name="line_id" value={line.line_id} />
			<button disabled={ui.pending}><Icon name="trash" size={18} />{t(lang, 'removeLine')}</button>
		</form>
	</div>
</div>

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		background: rgba(30, 79, 104, 0.72);
		display: flex;
		align-items: flex-end;
		justify-content: center;
		z-index: 20;
	}
	.backdrop-link {
		position: absolute;
		inset: 0;
	}
	.sheet {
		position: relative;
		width: 100%;
		max-width: 480px;
		max-height: 92vh;
		overflow-y: auto;
		background: var(--card);
		border-radius: 18px 18px 0 0;
		padding: 10px 18px 24px;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.grip {
		width: 44px;
		height: 5px;
		border-radius: 3px;
		background: var(--border);
		align-self: center;
	}
	.top {
		display: flex;
		gap: 12px;
		align-items: flex-start;
	}
	.names {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex-grow: 1;
		min-width: 0;
	}
	.asked {
		font-size: 13px;
		font-weight: 700;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: var(--muted);
	}
	h2 {
		font-size: 26px;
		line-height: 1.05;
		color: var(--petrol);
	}
	.unit {
		font-size: 14px;
		color: var(--muted);
	}
	.close {
		width: 40px;
		height: 40px;
		flex-shrink: 0;
		border-radius: 20px;
		background: var(--chip);
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--ink);
	}
	section {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	h3 {
		font-size: 22px;
	}
	.trace {
		background: var(--page);
		border-radius: 10px;
		padding: 14px 14px 16px;
	}
	.trace ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.trace li {
		display: grid;
		grid-template-columns: 34px 1fr;
		gap: 8px;
		font-size: 15px;
	}
	.trace li b {
		text-align: right;
	}
	.trace .minus {
		color: var(--red);
	}
	.trace .result {
		border-top: 1px solid var(--border);
		padding-top: 10px;
		font-weight: 600;
	}
	.alts {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.alt {
		width: 100%;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: var(--card);
		padding: 10px 12px;
		text-align: left;
		font-size: 14px;
		cursor: pointer;
	}
	.alt.current {
		border: 2px solid var(--petrol);
		cursor: default;
	}
	.alt-words {
		display: flex;
		flex-direction: column;
		gap: 1px;
		min-width: 0;
	}
	.alt-words b {
		font-size: 15px;
	}
	.alt-words span {
		color: var(--muted);
	}
	.alt-price {
		white-space: nowrap;
	}
	.stepper {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 12px;
	}
	.step {
		width: 48px;
		height: 48px;
		border-radius: 24px;
		border: 0;
		background: var(--petrol);
		color: #fff;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.step:disabled {
		background: var(--border-strong);
		cursor: not-allowed;
	}
	.amount {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
	}
	.amount b {
		font-size: 22px;
	}
	.amount span {
		font-size: 13px;
		color: var(--muted);
	}
	.note {
		margin: 0;
		font-size: 14px;
		color: var(--muted-2);
	}
	.error {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		color: var(--red);
	}
	.remove {
		display: flex;
		justify-content: center;
		padding-top: 8px;
	}
	.remove button {
		display: flex;
		align-items: center;
		gap: 6px;
		border: 0;
		background: transparent;
		color: var(--red);
		font-size: 15px;
		font-weight: 700;
		cursor: pointer;
		padding: 8px;
	}
</style>
