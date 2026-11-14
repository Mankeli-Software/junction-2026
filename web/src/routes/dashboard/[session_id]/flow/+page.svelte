<script lang="ts">
	import Icon, { type IconName } from '#lib/dashboard/components/Icon.svelte';
	import OrderNav from '#lib/dashboard/components/OrderNav.svelte';
	import { formatTimeSeconds } from '#lib/dashboard/format.ts';
	import { pick, t, type StringKey } from '#lib/dashboard/i18n.ts';
	import { combineSteps, combineTranscript, mergeStep, mergeTranscript } from '#lib/dashboard/merge.ts';
	import { sessionLive } from '#lib/dashboard/session-live.svelte.ts';
	import {
		buildTimeline,
		collapse,
		formatRefs,
		rowMatchesFilter,
		stepCount,
		type NoteRow,
		type TimelineFilter,
		type TimelineRow
	} from '#lib/dashboard/timeline.ts';
	import type { Localized, Step, TranscriptLine } from '#lib/dashboard/types.ts';
	import { useUi } from '#lib/dashboard/ui.svelte.ts';
	import { onMount, tick } from 'svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const ui = useUi();

	const summary = $derived(data.summary);
	const base = $derived(`/dashboard/${encodeURIComponent(summary.session_id)}`);
	const connector = $derived(summary.channel === 'mcp');

	let liveSteps = $state<Step[]>([]);
	let liveLines = $state<TranscriptLine[]>([]);
	sessionLive(() => data.summary.session_id, {
		onStep: (step) => mergeStep(liveSteps, step),
		onTranscript: (line) => mergeTranscript(liveLines, line),
		onReset: () => {
			liveSteps = [];
			liveLines = [];
		}
	});

	const rows = $derived(
		buildTimeline(
			combineSteps(data.steps, liveSteps),
			data.events,
			combineTranscript(data.transcript, liveLines)
		)
	);

	let filter = $state<TimelineFilter>('everything');
	let expanded = $state(false);
	let details = $state<Record<number, boolean>>({});

	const visible = $derived(rows.filter((r) => rowMatchesFilter(r, filter)));
	const parts = $derived(
		filter === 'everything' && !expanded ? collapse(visible) : { head: visible, hidden: [], tail: [] }
	);

	// A link to a step hidden in the collapsed middle opens it.
	onMount(async () => {
		const match = /^#e-(\d+)$/.exec(location.hash);
		if (!match) return;
		const n = Number(match[1]);
		if (parts.hidden.some((r) => r.refs.includes(n))) {
			expanded = true;
			await tick();
			document.getElementById(`e-${n}`)?.scrollIntoView({ block: 'center' });
		}
	});

	const filters: { key: TimelineFilter; label: StringKey }[] = [
		{ key: 'everything', label: 'everything' },
		{ key: 'conversation', label: 'conversation' },
		{ key: 'agent_engine', label: 'agent_and_engine' }
	];

	function noteIcon(row: NoteRow): IconName {
		const type = row.types[row.types.length - 1];
		if (row.types[0] === 'session_started') return summary.channel === 'phone' ? 'phone' : 'chat';
		if (type === 'products_searched' || row.types.includes('products_searched')) return 'search';
		if (type === 'line_resolved' || type === 'order_confirmed' || type === 'flags_acknowledged') {
			return row.types[0] === 'link_opened' ? 'link' : 'check';
		}
		if (type === 'link_opened') return 'link';
		if (row.kind === 'engine') return 'engine';
		return 'chat';
	}

	/** "Call started." in bold, then the rest, as on screen 32. */
	function splitLead(text: string): [string, string] {
		const at = text.indexOf('. ');
		return at > 0 && at < 60 ? [text.slice(0, at + 1), text.slice(at + 1)] : ['', text];
	}

	function decisionTone(code: string): string {
		if (code === 'ready') return 'tone-confirmed';
		if (code === 'needs_clarification') return 'tone-waiting';
		if (code === 'rejected') return 'tone-attention';
		return 'tone-active';
	}

	function json(value: unknown): string {
		return value === undefined ? '' : JSON.stringify(value, null, 2);
	}
</script>

<svelte:head>
	<title>{t('flow_title', ui.lang)} {summary.order_number ?? ''} S.I.MO</title>
</svelte:head>

<OrderNav sessionId={summary.session_id} orderNumber={summary.order_number} current="flow">
	<div class="head">
		<h1 class="hd">{t('flow_title', ui.lang)}</h1>
		{#if summary.agent}
			<span class="agent"
				>{pick(summary.agent.name, ui.lang)}{summary.agent.prompt_version
					? `, ${t('prompt', ui.lang)} ${summary.agent.prompt_version}`
					: ''}.</span
			>
		{/if}
	</div>
</OrderNav>

{#snippet refLink(row: TimelineRow)}
	<a class="ref" href="{base}/audit?event={row.refs[0]}">{formatRefs(row.refs)}</a>
{/snippet}

{#snippet anchors(row: TimelineRow)}
	{#each row.refs.slice(1) as n (n)}<span id="e-{n}" class="anchor"></span>{/each}
{/snippet}

{#snippet timelineRow(row: TimelineRow)}
	<div class="ev" id="e-{row.refs[0]}">
		<span class="t">{formatTimeSeconds(row.at, ui.lang)}</span>
		{#if row.kind === 'buyer' || row.kind === 'agent'}
			<span class="mk mk-{row.kind}"><Icon name={row.kind === 'buyer' ? 'user' : 'bot'} size={16} stroke={2} /></span>
			<div class="say">
				<span class="who"
					>{row.transcript
						? t(row.kind === 'buyer' ? 'buyer_transcript' : 'agent_transcript', ui.lang)
						: t(row.kind === 'buyer' ? 'buyer_said' : 'agent_said', ui.lang)}</span
				>
				<div class="bub bub-{row.kind}">{row.text}</div>
			</div>
		{:else if row.kind === 'tool'}
			{@const open = !!details[row.refs[0]]}
			<span class="mk mk-tool"><Icon name="code" size={16} /></span>
			<div class="tool" class:open>
				<div class="tool-head">
					<b class="mono">{row.tool}</b>
					{#if row.summary}<span>{pick(row.summary, ui.lang)}</span>{/if}
					{#if row.decision}
						<span class="dec {decisionTone(row.decision.code)}"
							>{row.decision.label ? pick(row.decision.label, ui.lang) : row.decision.code}</span
						>
					{/if}
					<span class="grow"></span>
					{#if row.hasDetails}
						<button
							type="button"
							class="toggle"
							aria-expanded={open}
							onclick={() => (details[row.refs[0]] = !open)}
							>{t(open ? 'hide_details' : 'show_details', ui.lang)}</button
						>
					{/if}
				</div>
				{#each row.notes as note, i (i)}
					<span class="note">{t('engine_prefix', ui.lang)} {pick(note, ui.lang)}</span>
				{/each}
				{#if open}
					<div class="details">
						<div class="pane">
							<span class="who">{t('arguments', ui.lang)}</span>
							<pre class="mono">{json(row.args)}</pre>
						</div>
						<div class="pane">
							<span class="who">{t('response_to_agent', ui.lang)}</span>
							<pre class="mono">{row.response === null ? t('no_response_yet', ui.lang) : json(row.response)}</pre>
						</div>
					</div>
				{/if}
			</div>
		{:else if row.kind === 'engine' || row.kind === 'system' || row.kind === 'confirmation'}
			<span class="mk mk-{row.kind}"><Icon name={noteIcon(row)} size={16} /></span>
			<span class="eng" class:final={row.types.includes('order_confirmed')}>
				{#if row.kind === 'engine'}
					<b>{t('engine_prefix', ui.lang)}</b>
					{row.texts.map((x: Localized) => pick(x, ui.lang)).join(' ')}
				{:else}
					{@const [lead, rest] = splitLead(row.texts.map((x: Localized) => pick(x, ui.lang)).join(' '))}
					<b>{lead}</b>{rest}
				{/if}
			</span>
		{/if}
		{@render refLink(row)}
		{@render anchors(row)}
	</div>
{/snippet}

<main class="wrap body">
	<div class="bar">
		<div class="segs" role="group" aria-label="Filter">
			{#each filters as f (f.key)}
				<button type="button" class="seg" class:on={filter === f.key} aria-pressed={filter === f.key} onclick={() => (filter = f.key)}
					>{t(f.label, ui.lang)}</button
				>
			{/each}
		</div>
		<div class="legend">
			<span><i class="lg-buyer"></i>{t('legend_buyer', ui.lang)}</span>
			<span><i class="lg-agent"></i>{t('legend_agent', ui.lang)}</span>
			<span><i class="lg-tool"></i>{t('legend_tool', ui.lang)}</span>
			<span><i class="lg-engine"></i>{t('legend_engine', ui.lang)}</span>
			<span><i class="lg-confirmation"></i>{t('legend_confirmation', ui.lang)}</span>
		</div>
	</div>

	<div class="card timeline">
		{#if connector && filter !== 'agent_engine'}
			<p class="connector">{t('connector_flow_note', ui.lang, { client: summary.client })}</p>
		{/if}
		{#each parts.head as row (row.refs[0])}{@render timelineRow(row)}{/each}
		{#if parts.hidden.length}
			<div class="ev">
				<span></span><span></span>
				<button type="button" class="more" onclick={() => (expanded = true)}
					>{t('show_more_steps', ui.lang, { n: stepCount(parts.hidden) })}</button
				>
				<span></span>
			</div>
		{/if}
		{#each parts.tail as row (row.refs[0])}{@render timelineRow(row)}{/each}
		{#if visible.length === 0 && !(connector && filter === 'conversation')}
			<p class="empty">{t('no_steps', ui.lang)}</p>
		{/if}
	</div>
</main>

<style>
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 16px;
		flex-wrap: wrap;
	}
	h1 {
		font-size: 44px;
		line-height: 1;
		color: var(--d-petrol);
	}
	.agent {
		font-size: 14px;
		color: var(--d-ink-2);
	}
	.body {
		padding-top: 20px;
		padding-bottom: 40px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.bar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}
	.segs {
		display: flex;
		gap: 4px;
		background: var(--d-seg);
		padding: 4px;
		border-radius: 8px;
	}
	.seg {
		height: 38px;
		padding: 0 14px;
		border: 0;
		background: transparent;
		border-radius: 6px;
		font-size: 15px;
		font-weight: 700;
		color: var(--d-petrol);
		cursor: pointer;
	}
	.seg.on {
		background: #fff;
		box-shadow: 0 1px 3px rgba(16, 48, 63, 0.15);
	}
	.legend {
		display: flex;
		gap: 16px;
		font-size: 14px;
		color: var(--d-muted);
		flex-wrap: wrap;
	}
	.legend span {
		display: flex;
		gap: 6px;
		align-items: center;
	}
	.legend i {
		width: 12px;
		height: 12px;
		border-radius: 6px;
		display: inline-block;
	}
	.lg-buyer {
		background: #fff;
		border: 1px solid #b9c6ce;
		box-sizing: border-box;
	}
	.lg-agent {
		background: var(--d-petrol);
	}
	.lg-tool {
		background: var(--d-tool);
	}
	.lg-engine {
		background: var(--d-faint);
	}
	.lg-confirmation {
		background: var(--d-lime);
	}
	.timeline {
		padding: 10px 22px;
	}
	.ev {
		display: grid;
		grid-template-columns: 78px 36px minmax(0, 1fr) 70px;
		gap: 14px;
		align-items: start;
		padding: 10px 0;
		scroll-margin-top: 80px;
	}
	.ev:target {
		background: #f8fafb;
	}
	.anchor {
		display: none;
	}
	.t {
		font-size: 14px;
		color: var(--d-muted);
		font-variant-numeric: tabular-nums;
		padding-top: 7px;
	}
	.mk {
		width: 32px;
		height: 32px;
		border-radius: 16px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #fff;
	}
	.mk-buyer {
		background: #fff;
		border: 1px solid #b9c6ce;
		color: var(--d-petrol);
		box-sizing: border-box;
	}
	.mk-agent {
		background: var(--d-petrol);
	}
	.mk-tool {
		background: var(--d-tool);
	}
	.mk-engine,
	.mk-system {
		background: var(--d-faint);
	}
	.mk-confirmation {
		background: var(--d-lime);
		color: var(--d-ink);
	}
	.ref {
		font-size: 13px;
		color: var(--d-faint);
		text-align: right;
		padding-top: 7px;
		text-decoration: none;
	}
	.ref:hover {
		text-decoration: underline;
	}
	.say {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.who {
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: var(--d-muted);
	}
	.bub {
		border-radius: 4px 12px 12px 12px;
		padding: 10px 14px;
		font-size: 17px;
		line-height: 1.4;
		align-self: flex-start;
		max-width: 640px;
		overflow-wrap: anywhere;
	}
	.bub-buyer {
		background: #fff;
		border: 1px solid var(--d-line);
	}
	.bub-agent {
		background: var(--d-active-bg);
	}
	.tool {
		background: var(--d-chat-bg);
		border: 1px solid var(--d-tool-border);
		border-radius: 8px;
		padding: 10px 14px;
		font-size: 15px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		max-width: 760px;
		min-width: 0;
	}
	.tool.open {
		border: 2px solid var(--d-tool);
		padding: 9px 13px;
	}
	.tool-head {
		display: flex;
		gap: 10px;
		align-items: center;
		flex-wrap: wrap;
	}
	.grow {
		flex-grow: 1;
	}
	.dec {
		font-size: 13px;
		font-weight: 700;
		padding: 2px 8px;
		border-radius: 10px;
	}
	.toggle {
		border: 0;
		background: none;
		font-size: 14px;
		font-weight: 700;
		color: var(--d-petrol);
		cursor: pointer;
	}
	.note {
		font-size: 14px;
		color: var(--d-muted);
	}
	.details {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
	}
	.pane {
		background: #fff;
		border-radius: 6px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	pre {
		margin: 0;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
		color: var(--d-ink-2);
	}
	.eng {
		font-size: 16px;
		line-height: 1.4;
		padding-top: 5px;
	}
	.eng.final {
		font-size: 18px;
	}
	.more {
		justify-self: start;
		border: 1px dashed #b9c6ce;
		background: #f8fafb;
		border-radius: 8px;
		padding: 10px 16px;
		font-size: 15px;
		font-weight: 700;
		color: var(--d-petrol);
		cursor: pointer;
	}
	.connector {
		margin: 10px 0;
		padding: 12px 14px;
		background: var(--d-page);
		border-radius: 8px;
		font-size: 16px;
		color: var(--d-ink-2);
	}
	.empty {
		font-size: 16px;
		color: var(--d-muted);
	}
	@media (max-width: 700px) {
		.ev {
			grid-template-columns: 60px 32px minmax(0, 1fr);
		}
		.ref {
			grid-column: 3;
			text-align: left;
			padding-top: 0;
		}
		.details {
			grid-template-columns: minmax(0, 1fr);
		}
	}
</style>
