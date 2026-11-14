<script lang="ts">
	import { formatUnitPrice } from '../format';
	import { pick, t } from '../i18n';
	import type { RankedCandidate, Trace } from '../types';
	import { useUi } from '../ui.svelte';
	import Icon from './Icon.svelte';

	/** The "Why" drill-down for one line: what was found, what each filter removed, the ranking. */
	let { trace, baseUnit }: { trace: Trace; baseUnit: string | null } = $props();
	const ui = useUi();

	const COLOURS = ['#E7A49C', '#F0C46A', '#B9A4D6', '#9FC3D4', '#E3B7D0', '#C9D88A'];
	let open = $state<Record<string, boolean>>({});

	function stockWord(c: RankedCandidate): string {
		if (c.chosen) return t('chosen', ui.lang);
		if (c.stock_status === 'verified') return t('in_stock', ui.lang);
		if (c.stock_status === 'unverified') return t('not_confirmed', ui.lang);
		return t('unavailable', ui.lang);
	}
</script>

<div class="why">
	<div class="funnel">
		<h3 class="hd">{t('found_left', ui.lang, { found: trace.found, left: trace.left })}</h3>
		<div class="bar" aria-hidden="true">
			{#each trace.removed as r, i (r.reason_code)}
				<span style:flex={r.count} style:background={COLOURS[i % COLOURS.length]}></span>
			{/each}
			<span style:flex={trace.left} style:background="var(--d-petrol)"></span>
		</div>
		{#each trace.removed as r, i (r.reason_code)}
			{@const products = r.products ?? []}
			<button
				type="button"
				class="fl"
				aria-expanded={products.length ? !!open[r.reason_code] : undefined}
				disabled={products.length === 0}
				onclick={() => (open[r.reason_code] = !open[r.reason_code])}
			>
				<span class="sw" style:background={COLOURS[i % COLOURS.length]}></span>
				<b class="n">{r.count}</b>
				<span class="txt">{pick(r.text, ui.lang)}</span>
				{#if products.length}<Icon name={open[r.reason_code] ? 'up' : 'down'} size={14} stroke={2.5} />{/if}
			</button>
			{#if open[r.reason_code]}
				<ul class="removed">
					{#each products as p (p.product_id)}
						<li>{pick(p.name, ui.lang)} <span class="pid">#{p.product_id}</span></li>
					{/each}
				</ul>
			{/if}
		{/each}
		<div class="fl last">
			<span class="sw" style:background="var(--d-petrol)"></span>
			<b class="n">{trace.left}</b>
			<span class="txt strong">{t('safe_left', ui.lang)}</span>
		</div>
	</div>

	{#if trace.ranked.length === 0}
		<!-- The API sends no candidates until the engine records them (#36, #39). -->
		<div class="ranked">
			<h3 class="hd">{pick(trace.ranking_rule, ui.lang)}</h3>
			<p class="none" data-testid="ranked-not-available">{t('ranked_not_available', ui.lang)}</p>
		</div>
	{:else}
		<div class="ranked">
			<h3 class="hd">{pick(trace.ranking_rule, ui.lang)}</h3>
			<div class="cand head">
				<span>{t('rank', ui.lang)}</span><span>{t('product', ui.lang)}</span><span
					>{t('per', ui.lang)} {baseUnit ?? ''}</span
				><span>{t('stock', ui.lang)}</span>
			</div>
			{#each trace.ranked as c (c.product_id)}
				<div class="cand" class:chosen={c.chosen}>
					<span>{c.rank}</span>
					<span title="#{c.product_id}">{pick(c.name, ui.lang)}</span>
					<span>{c.price_per_base_unit !== null ? formatUnitPrice(c.price_per_base_unit, ui.lang) : ''}</span>
					<span>{stockWord(c)}</span>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.why {
		border-top: 1px solid var(--d-line);
		padding: 18px 20px 20px;
		display: flex;
		flex-wrap: wrap;
		gap: 28px;
		background: #fafcfd;
		border-radius: 0 0 10px 10px;
	}
	.funnel {
		flex: 1 1 300px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	h3 {
		font-size: 22px;
		margin-bottom: 4px;
	}
	.bar {
		display: flex;
		height: 14px;
		border-radius: 7px;
		overflow: hidden;
		margin-bottom: 6px;
	}
	.fl {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 15px;
		padding: 8px 0;
		border: 0;
		border-bottom: 1px solid var(--d-line-soft);
		background: none;
		font: inherit;
		color: inherit;
		text-align: left;
		cursor: pointer;
		color: var(--d-petrol);
	}
	.fl:disabled {
		cursor: default;
	}
	.fl .txt {
		color: var(--d-ink);
	}
	.fl.last {
		border-bottom: 0;
		cursor: default;
	}
	.sw {
		width: 12px;
		height: 12px;
		border-radius: 3px;
		flex-shrink: 0;
	}
	.n {
		width: 24px;
		color: var(--d-ink);
	}
	.txt {
		flex-grow: 1;
	}
	.strong {
		font-weight: 600;
	}
	.removed {
		margin: 0 0 4px;
		padding: 6px 0 6px 46px;
		font-size: 14px;
		color: var(--d-ink-2);
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.pid {
		font-size: 12px;
		color: var(--d-faint);
		font-weight: 500;
	}
	.ranked {
		flex: 2 1 420px;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	.ranked h3 {
		margin-bottom: 8px;
	}
	.none {
		margin: 0;
		font-size: 14px;
		color: var(--d-muted);
	}
	.cand {
		display: grid;
		grid-template-columns: 28px minmax(0, 1fr) 110px 150px;
		gap: 12px;
		align-items: center;
		font-size: 15px;
		padding: 9px 0;
		border-bottom: 1px solid var(--d-line-soft);
	}
	.cand:last-child {
		border-bottom: 0;
	}
	.cand.head {
		font-size: 13px;
		color: var(--d-muted);
		font-weight: 700;
		padding-top: 0;
	}
	.cand.chosen {
		background: var(--d-chosen);
		border-radius: 6px;
		padding-left: 8px;
		padding-right: 8px;
		font-weight: 700;
	}
	@media (max-width: 640px) {
		.cand {
			grid-template-columns: 22px minmax(0, 1fr) 70px 90px;
			gap: 8px;
			font-size: 14px;
		}
	}
</style>
