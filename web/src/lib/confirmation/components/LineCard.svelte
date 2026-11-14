<script lang="ts">
	/** One order line under "You asked, we added" (spec §4.3): asked versus added, price, why. */
	import { money } from '../format';
	import { pageUrl, type PageUrl } from '../forms.svelte';
	import { flagMark, t } from '../i18n';
	import type { Flag, Lang, Line } from '../types';
	import Icon from './Icon.svelte';

	let {
		line,
		asked,
		flags,
		lang,
		url,
		changed
	}: { line: Line; asked: string; flags: Flag[]; lang: Lang; url: PageUrl; changed: boolean } = $props();

	const lineFlags = $derived(flags.filter((f) => line.flag_keys.includes(f.key)));
	const mark = $derived(
		lineFlags.length === 1
			? flagMark(lang, lineFlags[0].kind)
			: lineFlags.length > 1
				? t(lang, 'flagsCount', { n: lineFlags.length })
				: null
	);
	const sheetUrl = $derived(pageUrl(url, { line: line.id, cancel: null }));
</script>

<article class="card" class:changed id="line-{line.id}" data-testid="line" data-line-id={line.id}>
	<span class="asked">{t(lang, 'youAsked', { asked })}</span>
	<div class="row">
		<div class="thumb">
			{#if line.product.image_url}
				<img src={line.product.image_url} alt="" width="56" height="56" />
			{:else}
				<Icon name="box" size={26} stroke="var(--faint)" weight={1.8} />
			{/if}
		</div>
		<div class="what">
			<a class="name" href={sheetUrl} data-sveltekit-reset="false">{line.product.name[lang]}</a>
			<span class="qty">
				{line.quantity_text[lang]}
				{#if mark}<span class="mark">{mark}</span>{/if}
				{#if changed}<span class="mark changed-mark">{t(lang, 'changed')}</span>{/if}
			</span>
		</div>
		<span class="price">{money(line.line_total_cents)}</span>
	</div>
	<div class="foot">
		<span class="why">{line.why[lang]}</span>
		<span class="actions">
			<a class="chip" href={sheetUrl} aria-label={t(lang, 'whyLabel')} data-sveltekit-reset="false"
				><Icon name="info" />{t(lang, 'why')}</a
			>
			<a class="chip round" href={sheetUrl} aria-label={t(lang, 'changeLine')} data-sveltekit-reset="false"
				><Icon name="pencil" /></a
			>
		</span>
	</div>
</article>

<style>
	.card {
		background: var(--card);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		scroll-margin-top: 16px;
	}
	.card.changed {
		border: 2px solid var(--petrol);
	}
	.asked {
		font-size: 13px;
		font-weight: 700;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: var(--muted);
	}
	.row {
		display: flex;
		gap: 12px;
		align-items: center;
	}
	.thumb {
		width: 56px;
		height: 56px;
		flex-shrink: 0;
		border-radius: 8px;
		background: var(--page);
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	.thumb img {
		width: 100%;
		height: 100%;
		object-fit: contain;
	}
	.what {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex-grow: 1;
		min-width: 0;
	}
	.name {
		font-weight: 700;
		font-size: 16px;
		text-decoration: none;
	}
	.qty {
		font-size: 14px;
		color: var(--muted);
	}
	.mark {
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 12px;
		background: var(--yellow);
		color: var(--ink);
		padding: 1px 6px;
		border-radius: 3px;
		letter-spacing: 0.4px;
		text-transform: uppercase;
		white-space: nowrap;
	}
	.changed-mark {
		background: var(--chip);
		color: var(--petrol);
	}
	.price {
		font-weight: 800;
		font-size: 18px;
		white-space: nowrap;
	}
	.foot {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 8px;
		border-top: 1px solid var(--divider);
		padding-top: 10px;
	}
	.why {
		font-size: 14px;
		color: var(--muted-2);
	}
	.actions {
		display: flex;
		gap: 6px;
		flex-shrink: 0;
	}
	.chip {
		height: 36px;
		padding: 0 12px;
		border-radius: 18px;
		background: var(--chip);
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 14px;
		font-weight: 700;
		text-decoration: none;
	}
	.chip.round {
		width: 36px;
		padding: 0;
		justify-content: center;
	}
</style>
