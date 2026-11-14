<script lang="ts">
	import { PUBLIC_DASHBOARD_MOCK } from '$app/env/public';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { eventsDownloadUrl } from '#lib/dashboard/api.ts';
	import { chainCheck } from '#lib/dashboard/chain.svelte.ts';
	import Icon from '#lib/dashboard/components/Icon.svelte';
	import OrderNav from '#lib/dashboard/components/OrderNav.svelte';
	import { formatTimeSeconds, shortHash } from '#lib/dashboard/format.ts';
	import { pick, t } from '#lib/dashboard/i18n.ts';
	import { combineSteps, mergeStep } from '#lib/dashboard/merge.ts';
	import { sessionLive } from '#lib/dashboard/session-live.svelte.ts';
	import { channelName } from '#lib/dashboard/states.ts';
	import type { Step } from '#lib/dashboard/types.ts';
	import { useUi } from '#lib/dashboard/ui.svelte.ts';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const ui = useUi();

	const FIRST_ROWS = 12;

	const summary = $derived(data.summary);
	const base = $derived(`/dashboard/${encodeURIComponent(summary.session_id)}`);

	let liveSteps = $state<Step[]>([]);
	sessionLive(() => data.summary.session_id, {
		onStep: (step) => mergeStep(liveSteps, step),
		onReset: () => (liveSteps = [])
	});
	const steps = $derived(combineSteps(data.steps, liveSteps));
	const chain = chainCheck(() => steps);
	const eventsBySeq = $derived(new Map(data.events.map((e) => [e.seq, e])));

	const selectedIndex = $derived(Number(page.url.searchParams.get('event')) || steps[0]?.order_index || 0);
	const selected = $derived(steps.find((s) => s.order_index === selectedIndex) ?? null);
	const selectedEvent = $derived(selected ? (eventsBySeq.get(selected.seq) ?? null) : null);

	let showAll = $state(false);
	const badIndex = $derived(chain.result?.ok === false ? chain.result.first_bad_order_index : null);
	// Everything shows when the selected or the broken event is past the first rows.
	const allShown = $derived(
		showAll || steps.length <= FIRST_ROWS || selectedIndex > FIRST_ROWS || (badIndex ?? 0) > FIRST_ROWS
	);
	const shownSteps = $derived(allShown ? steps : steps.slice(0, FIRST_ROWS));

	function select(step: Step) {
		goto(`?event=${step.order_index}`, { replace: true, reset: false });
	}

	const reasonKey = {
		seq_gap: 'reason_seq_gap',
		prev_hash: 'reason_prev_hash',
		session_prev_hash: 'reason_session_prev_hash',
		payload_hash: 'reason_payload_hash',
		hash: 'reason_hash'
	} as const;

	const signatureText = $derived(
		summary.signature_valid === true
			? t('sig_valid_short', ui.lang)
			: summary.signature_valid === false
				? t('sig_invalid_short', ui.lang)
				: t('sig_unknown_short', ui.lang)
	);

	/** In the mock there is no API, so the file is made from the loaded events. */
	function downloadMock(event: MouseEvent) {
		event.preventDefault();
		const blob = new Blob([JSON.stringify(data.events, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${summary.session_id}-events.json`;
		a.click();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
</script>

<svelte:head>
	<title>{t('audit_title', ui.lang)} {summary.order_number ?? ''} S.I.MO</title>
</svelte:head>

<OrderNav sessionId={summary.session_id} orderNumber={summary.order_number} current="audit">
	<h1 class="hd">{t('audit_title', ui.lang)}</h1>
</OrderNav>

<main class="wrap body">
	<div
		class="banner"
		class:ok={chain.result?.ok === true}
		class:broken={chain.result?.ok === false}
		role="status"
		aria-live="polite"
	>
		<div class="badge">
			<Icon name={chain.result?.ok === false ? 'shieldx' : 'shield'} size={22} />
		</div>
		<div class="msg">
			{#if chain.result === null}
				<b>{t('chain_checking', ui.lang)}</b>
				<span>&nbsp;</span>
			{:else if chain.result.ok}
				<b>{t('chain_intact', ui.lang)}</b>
				<span>{t('recomputed', ui.lang, { n: chain.result.checked })} {signatureText}</span>
			{:else}
				<b>{t('chain_broken', ui.lang, { n: chain.result.first_bad_order_index ?? '?' })}</b>
				<span
					>{t('recomputed_broken', ui.lang, {
						n: chain.result.first_bad_order_index ?? '?',
						reason: t(reasonKey[chain.result.reason ?? 'hash'], ui.lang)
					})}
					{signatureText}</span
				>
			{/if}
		</div>
		<button type="button" class="btn outline" onclick={() => chain.again()} disabled={chain.checking}>
			<Icon name="refresh" size={16} stroke={2.4} />{t('verify_again', ui.lang)}
		</button>
		{#if PUBLIC_DASHBOARD_MOCK}
			<a class="btn solid" href={eventsDownloadUrl(summary.session_id)} onclick={downloadMock}>
				<Icon name="download" size={16} stroke={2.4} />{t('download_json', ui.lang)}
			</a>
		{:else}
			<a class="btn solid" href={eventsDownloadUrl(summary.session_id)} download>
				<Icon name="download" size={16} stroke={2.4} />{t('download_json', ui.lang)}
			</a>
		{/if}
	</div>

	<div class="cols">
		<div class="card table">
			<div class="row headrow">
				<span>#</span><span>{t('col_time', ui.lang)}</span><span>{t('col_type', ui.lang)}</span><span
					>{t('col_what', ui.lang)}</span
				><span>{t('col_hash', ui.lang)}</span>
			</div>
			{#each shownSteps as step (step.seq)}
				{@const on = selected?.seq === step.seq}
				<button
					type="button"
					class="row"
					class:on
					class:bad={badIndex === step.order_index}
					aria-pressed={on}
					onclick={() => select(step)}
				>
					<span class="mono">{step.order_index}</span>
					<span class="mono">{formatTimeSeconds(step.at, ui.lang)}</span>
					<span class="ty mono" class:tool={step.type.startsWith('tool_')}>{step.type}</span>
					{#if on}<b>{pick(step.text, ui.lang)}</b>{:else}<span>{pick(step.text, ui.lang)}</span>{/if}
					<span class="mono hash">{shortHash(step.hash)}</span>
				</button>
			{/each}
			{#if !allShown}
				<button type="button" class="row more" onclick={() => (showAll = true)}
					>{t('show_events', ui.lang, { from: FIRST_ROWS + 1, to: steps.length })}</button
				>
			{/if}
		</div>

		<aside class="card detail">
			{#if selected}
				<div class="dhead">
					<h2 class="hd">{t('event_n', ui.lang, { n: selected.order_index })}</h2>
					<a href="{base}/flow#e-{selected.order_index}">{t('show_in_flow', ui.lang)}</a>
				</div>
				<div class="kvs">
					<div class="kv"><span>{t('col_type', ui.lang)}</span><span class="mono">{selected.type}</span></div>
					<div class="kv"><span>{t('session', ui.lang)}</span><span class="mono">{summary.session_id}</span></div>
					<div class="kv"><span>{t('channel', ui.lang)}</span><span>{channelName(summary.channel, ui.lang)}</span></div>
					<div class="kv">
						<span>{t('identity', ui.lang)}</span><span>{selectedEvent?.identity_masked ?? summary.identity_masked ?? '–'}</span>
					</div>
					<div class="kv"><span>{t('previous', ui.lang)}</span><span class="mono hx">{selected.prev_hash}</span></div>
					<div class="kv">
						<span>{t('session_previous', ui.lang)}</span><span class="mono hx">{selected.session_prev_hash ?? '–'}</span>
					</div>
					<div class="kv"><span>{t('payload_hash', ui.lang)}</span><span class="mono hx">{selected.payload_hash}</span></div>
					<div class="kv last"><span>{t('col_hash', ui.lang)}</span><span class="mono hx">{selected.hash}</span></div>
				</div>
				<pre class="mono">{JSON.stringify(selectedEvent ?? selected, null, 2)}</pre>
				{#if !selectedEvent}<span class="small">{t('record_not_loaded', ui.lang)}</span>{/if}
			{:else}
				<p class="small">{t('pick_event', ui.lang)}</p>
			{/if}
			<span class="small">{t('read_only', ui.lang)}</span>
		</aside>
	</div>
</main>

<style>
	h1 {
		font-size: 44px;
		line-height: 1;
		color: var(--d-petrol);
	}
	.body {
		padding-top: 20px;
		padding-bottom: 40px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.banner {
		background: #fff;
		border: 1px solid var(--d-line);
		border-radius: 10px;
		padding: 14px 18px;
		display: flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
	}
	.banner.ok {
		background: var(--d-chosen);
		border-color: var(--d-ok-border);
	}
	.banner.broken {
		background: var(--d-attention-bg);
		border-color: var(--d-attention-border);
	}
	.badge {
		width: 40px;
		height: 40px;
		border-radius: 20px;
		background: var(--d-line);
		color: var(--d-ink);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.ok .badge {
		background: var(--d-lime);
	}
	.broken .badge {
		background: var(--d-attention-fg);
		color: #fff;
	}
	.msg {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex-grow: 1;
		min-width: 0;
	}
	.msg b {
		font-size: 18px;
	}
	.broken .msg b {
		color: var(--d-attention-fg);
	}
	.msg span {
		font-size: 14px;
		color: var(--d-ink-2);
	}
	.btn {
		height: 42px;
		padding: 0 16px;
		border-radius: 8px;
		font-size: 15px;
		font-weight: 700;
		display: flex;
		align-items: center;
		gap: 8px;
		cursor: pointer;
		box-sizing: border-box;
		text-decoration: none;
	}
	.btn.outline {
		border: 2px solid var(--d-petrol);
		background: #fff;
		color: var(--d-petrol);
	}
	.btn.outline:disabled {
		opacity: 0.6;
		cursor: progress;
	}
	.btn.solid {
		border: 0;
		background: var(--d-petrol);
		color: #fff;
	}
	.btn.solid:hover {
		color: #fff;
		background: var(--d-petrol-dark);
	}
	.cols {
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
		align-items: flex-start;
	}
	.table {
		flex: 999 1 640px;
		min-width: 0;
		overflow-x: auto;
	}
	.row {
		display: grid;
		grid-template-columns: 44px 84px 180px minmax(0, 1fr) 70px;
		gap: 12px;
		align-items: center;
		padding: 10px 14px;
		border: 0;
		border-bottom: 1px solid var(--d-line-soft);
		font-size: 15px;
		background: none;
		text-align: left;
		color: inherit;
		width: 100%;
		cursor: pointer;
		min-width: 560px;
	}
	.row:hover {
		background: #f8fafb;
	}
	.headrow {
		font-size: 13px;
		font-weight: 700;
		color: var(--d-muted);
		cursor: default;
		background: #f8fafb;
	}
	.row.on {
		background: var(--d-active-bg);
		box-shadow: inset 4px 0 0 var(--d-petrol);
	}
	.row.bad {
		background: var(--d-attention-bg);
		box-shadow: inset 4px 0 0 var(--d-attention-fg);
	}
	.ty {
		padding: 2px 6px;
		border-radius: 4px;
		justify-self: start;
		background: var(--d-line-soft);
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.ty.tool {
		background: var(--d-chat-bg);
	}
	.row.on .ty {
		background: #fff;
	}
	.hash {
		color: var(--d-faint);
	}
	.row.on .hash {
		color: var(--d-petrol);
	}
	.row.more {
		display: flex;
		justify-content: center;
		color: var(--d-petrol);
		font-weight: 700;
		border-bottom: 0;
	}
	.detail {
		flex: 1 1 380px;
		min-width: 0;
		padding: 18px 20px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.dhead {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 12px;
	}
	.dhead h2 {
		font-size: 26px;
	}
	.dhead a {
		font-size: 14px;
		font-weight: 700;
	}
	.kvs {
		display: flex;
		flex-direction: column;
	}
	.kv {
		display: grid;
		grid-template-columns: 130px minmax(0, 1fr);
		gap: 10px;
		font-size: 14px;
		padding: 6px 0;
		border-bottom: 1px solid var(--d-line-soft);
	}
	.kv > span:first-child {
		color: var(--d-muted);
	}
	.kv.last {
		border-bottom: 0;
	}
	.hx {
		word-break: break-all;
	}
	pre {
		margin: 0;
		background: var(--d-page);
		border-radius: 8px;
		padding: 12px 14px;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		color: var(--d-ink-2);
		line-height: 1.5;
		max-height: 520px;
		overflow-y: auto;
	}
	.small {
		font-size: 13px;
		color: var(--d-muted);
		margin: 0;
	}
</style>
