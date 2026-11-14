<script lang="ts">
	/**
	 * The quote in the chat (design UI-05, Chat-A4): what the buyer asked next to what
	 * was added, per recipe or photo, with subtotals, "Not ordered", the flags as a
	 * read-only preview, total and delivery; a clarification as one-tap answers; a
	 * rejection with its next step; and "Send to my phone". Everything shown comes from
	 * `GET /api/v1/quotes/{id}`; the model only gives the id. The confirmation link
	 * never shows here.
	 */
	import { untrack } from 'svelte';
	import { codeTitle } from '#lib/confirmation/display.js';
	import '../cards.css';
	import { chatContext } from '../context';
	import { date, money } from '../format';
	import { t } from '../i18n';
	import { Loaded } from '../load.svelte';
	import { askedLabel, lineFlagCodes, newerQuoteSurface, productLabel, quoteSections } from '../quote';
	import type { Quote } from '../types';
	import CardShell from './CardShell.svelte';
	import Icon from './Icon.svelte';
	import Thumb from './Thumb.svelte';

	let { quoteId, surfaceId, componentId }: { quoteId: string; surfaceId: string; componentId: string } = $props();
	const { store, data, lang, revision } = chatContext();
	const L = $derived(lang());
	const uid = $props.id();

	const loaded = new Loaded<Quote>(() => data.getQuote(quoteId));
	/** Portions of the photo drafts behind the groups, for "Karjalanpiirakat, 120 portions". */
	let draftPortions = $state<Record<string, number>>({});
	let flagsOpen = $state(false);

	$effect(() => {
		void quoteId;
		untrack(() => loaded.load());
	});

	$effect(() => {
		const r = revision?.();
		if (r === undefined) return;
		untrack(() => loaded.refresh());
	});

	$effect(() => {
		const quote = loaded.value;
		if (!quote) return;
		for (const g of quote.groups) {
			const id = g.recipe_draft_id;
			if (g.source !== 'photo' || !id || untrack(() => id in draftPortions)) continue;
			data.getDraft(id).then(
				(d) => (draftPortions[id] = d.portions),
				() => {}
			);
		}
	});

	$effect(() => {
		const id = loaded.status === 'ready' ? loaded.value?.quote_id : undefined;
		if (id) untrack(() => store.markActed(surfaceId, `${componentId}#loaded`, quoteId));
	});

	const quote = $derived(loaded.value);
	const sections = $derived(quote ? quoteSections(quote) : []);
	const newer = $derived(newerQuoteSurface(store, surfaceId, componentId, quoteId));
	const replaced = $derived(Boolean(newer) || quote?.status === 'void');
	const answered = $derived(store.actedOn(surfaceId, `${componentId}#answer`));
	const sendAsked = $derived(store.actedOn(surfaceId, `${componentId}#send`) === quote?.quote_id);
	const canSend = $derived(quote?.status === 'ready' && quote.decision === 'ready' && quote.lines.length > 0);
	const notOrderedReasons = $derived(quote ? [...new Set(quote.not_ordered.map((n) => n.reason[L]))] : []);

	function delivery(q: Quote): string {
		if (!q.delivery) return t(L, 'inclVat');
		const { earliest, latest } = q.delivery;
		return earliest === latest
			? t(L, 'deliveryVat', { date: date(earliest, L) })
			: t(L, 'deliveryRangeVat', { from: date(earliest, L), to: date(latest, L) });
	}

	/** `label` is the engine's own text for the answer, so the chat can echo it as the buyer's turn. */
	function answer(lineId: string, productId: string, label: string) {
		if (!quote || answered) return;
		store.markActed(surfaceId, `${componentId}#answer`, productId);
		store.emit(surfaceId, componentId, 'clarification_answered', { quoteId: quote.quote_id, lineId, productId, label });
	}

	function nextStep(lineId: string) {
		if (!quote || store.actedOn(surfaceId, `${componentId}#next:${lineId}`)) return;
		store.markActed(surfaceId, `${componentId}#next:${lineId}`, 'yes');
		store.emit(surfaceId, componentId, 'rejection_next_step', { quoteId: quote.quote_id, lineId });
	}

	function send() {
		if (!quote || !canSend || sendAsked) return;
		store.markActed(surfaceId, `${componentId}#send`, quote.quote_id);
		store.emit(surfaceId, componentId, 'send_for_confirmation', { quoteId: quote.quote_id });
	}

	function goLatest() {
		if (!newer) return;
		document.querySelector(`[data-surface-id="${CSS.escape(newer)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}
</script>

{#snippet total()}
	{#if quote && quote.lines.length && !replaced}<b class="total" data-testid="quote-total">{money(quote.total_cents)}</b>{/if}
{/snippet}

<CardShell
	testid="quote-card"
	eyebrow={replaced || loaded.status !== 'ready' ? t(L, 'quoteTitle') : undefined}
	title={replaced || loaded.status !== 'ready' ? undefined : t(L, 'quoteTitle')}
	status={loaded.status}
	variant={replaced ? 'faded' : 'plain'}
	onretry={() => loaded.load()}
	aside={total}
>
	{#if quote}
		{#if replaced}
			<p class="plain-text" data-testid="quote-replaced">{t(L, 'replaced')}</p>
			{#if newer}<button type="button" class="link" onclick={goLatest}>{t(L, 'goLatest')}</button>{/if}
		{:else}
			{#if quote.lines.length}<span class="a2-cap sub">{delivery(quote)}</span>{/if}

			{#if quote.clarification}
				{@const c = quote.clarification}
				<div class="block" data-testid="quote-question">
					<span class="eyebrow">{t(L, 'question')}</span>
					<b class="question">{c.question[L]}</b>
					{#each c.options as option, oi (oi)}
						{@const chosen = answered === option.product_id}
						{#if !answered || chosen}
							<button
								type="button"
								class="opt"
								class:chosen
								aria-pressed={chosen}
								disabled={Boolean(answered) || quote.status !== 'needs_clarification'}
								onclick={() => answer(c.line_id, option.product_id, option.label[L])}
							>
								<span class="opt-label">{#if chosen}<Icon name="check" stroke="#fff" weight={2.6} />{/if}{option.label[L]}</span>
								<b>{money(option.line_total_cents)}</b>
							</button>
						{/if}
					{/each}
				</div>
			{/if}

			{#each quote.rejections as r, ri (ri)}
				{@const done = Boolean(store.actedOn(surfaceId, `${componentId}#next:${r.line_id}`))}
				<div class="block alert" data-testid="quote-rejection">
					<span class="rej-head"><Icon name="alert" stroke="var(--red)" />{t(L, 'cantAdd')}</span>
					<span>{r.text[L]}</span>
					<span class="a2-cap">{r.next_step[L]}</span>
					<button type="button" class="opt center" disabled={done} aria-pressed={done} onclick={() => nextStep(r.line_id)}>
						{#if done}<Icon name="check" weight={2.6} />{/if}{t(L, 'nextStep')}
					</button>
				</div>
			{/each}

			{#if !quote.lines.length && !quote.rejections.length && !quote.clarification}
				<p class="plain-text">{t(L, 'noLines')}</p>
			{/if}

			{#each sections as s, i (i)}
				{#if sections.length > 1 || s.kind !== 'other'}
					<div class="grp" class:sep={i > 0}>
						{#if s.imageUrl}
							<Thumb src={s.imageUrl} width={48} height={32} placeholder="none" radius={4} />
						{:else if s.kind === 'photo'}<Icon name="camera" stroke="var(--petrol)" />{/if}
						<span class="grow">
							{#if s.kind === 'photo'}
								{s.draftId && draftPortions[s.draftId]
									? t(L, 'fromPhotoGroupPortions', { group: s.group ?? '', n: draftPortions[s.draftId] })
									: t(L, 'fromPhotoGroup', { group: s.group ?? '' })}
							{:else if s.kind === 'group'}
								{t(L, 'forRecipe', { group: s.group ?? '' })}
							{:else}
								{t(L, 'otherLines')}
							{/if}
						</span>
						<span>{money(s.subtotalCents)}</span>
					</div>
				{/if}
				{#each s.lines as line (line.line_id)}
					<div class="line" data-testid="quote-line" data-line-id={line.line_id}>
						<span class="asked">{t(L, 'youAsked', { asked: askedLabel(line, L) })}</span>
						<div class="line-main">
							<Thumb src={line.image_url} width={44} height={44} fit="contain" placeholder="box" radius={6} />
							<div class="what">
								<b class="product"
									>{productLabel(line, L)}
									{#each lineFlagCodes(quote, line.line_id) as code (code)}<span class="a2-tag">{codeTitle(code, L)}</span>{/each}</b
								>
								<span class="a2-cap">{line.reason_text[L]}</span>
							</div>
							<b class="price">{money(line.line_total_cents)}</b>
						</div>
					</div>
				{/each}
			{/each}

			{#if quote.not_ordered.length}
				<p class="not-ordered" data-testid="quote-not-ordered">
					<Icon name="none" stroke="var(--muted)" weight={2} />
					<span
						>{t(L, 'notOrdered', { items: quote.not_ordered.map((n) => n.name).join(', ') })}.{#each notOrderedReasons as reason (reason)}{' '}{reason}{/each}</span
					>
				</p>
			{/if}

			{#if quote.flags.length}
				<button type="button" class="flags-toggle" aria-expanded={flagsOpen} aria-controls="{uid}-flags" onclick={() => (flagsOpen = !flagsOpen)}>
					<Icon name="warn" stroke="#6b5400" weight={2} />
					{quote.flags.length === 1 ? t(L, 'oneThing') : t(L, 'nThings', { n: quote.flags.length })}
					<span class="chev" class:open={flagsOpen}><Icon name="chevron" size={12} stroke="#6b5400" weight={2.5} /></span>
				</button>
				{#if flagsOpen}
					<div class="flags" id="{uid}-flags" data-testid="quote-flags">
						<ul>
							{#each quote.flags as flag (flag.flag_key)}
								<li>{flag.text[L]}</li>
							{/each}
						</ul>
						<span class="a2-cap">{t(L, 'checkOnPhone')}</span>
					</div>
				{/if}
			{/if}

			{#if quote.status === 'pending_confirmation'}
				<p class="a2-done"><Icon name="phone" size={18} stroke="#3f5a00" />{t(L, 'pendingConfirmation')}</p>
			{:else if quote.status === 'confirmed'}
				<p class="a2-done"><Icon name="check" size={18} stroke="#3f5a00" weight={2.6} />{t(L, 'quoteConfirmed')}</p>
			{:else if quote.status === 'cancelled'}
				<p class="plain-text muted">{t(L, 'quoteCancelled')}</p>
			{:else if quote.status === 'expired'}
				<p class="plain-text muted">{t(L, 'quoteExpired')}</p>
			{:else if canSend}
				<button type="button" class="a2-dark send" disabled={sendAsked} onclick={send} data-testid="send-to-phone">
					<Icon name="phone" size={18} stroke="#fff" />{sendAsked ? t(L, 'sendAsked') : t(L, 'sendToPhone')}
				</button>
			{/if}
		{/if}
	{/if}
</CardShell>

<style>
	.total {
		font-size: 18px;
		white-space: nowrap;
	}
	.sub {
		margin-top: -8px;
	}
	.plain-text {
		margin: 0;
		font-size: 14px;
	}
	.muted {
		color: var(--muted);
	}
	.link {
		align-self: flex-start;
		padding: 0;
		border: 0;
		background: none;
		color: var(--petrol);
		font-size: 14px;
		font-weight: 700;
		text-decoration: underline;
		cursor: pointer;
		min-height: 44px;
	}
	.block {
		display: flex;
		flex-direction: column;
		gap: 8px;
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 12px;
	}
	.block.alert {
		border-color: #e8b3ad;
	}
	.eyebrow {
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 13px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		color: var(--muted);
	}
	.question {
		font-size: 16px;
		line-height: 1.35;
	}
	.opt {
		min-height: 48px;
		padding: 6px 14px;
		border-radius: 8px;
		border: 2px solid var(--petrol);
		background: var(--card);
		color: var(--ink);
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		font-size: 15px;
		text-align: left;
		cursor: pointer;
	}
	.opt.center {
		justify-content: center;
		font-weight: 700;
		color: var(--petrol);
	}
	.opt.chosen {
		background: var(--petrol);
		color: #fff;
	}
	.opt:disabled {
		cursor: default;
	}
	.opt:disabled:not(.chosen):not([aria-pressed='true']) {
		opacity: 0.5;
	}
	.opt-label {
		display: flex;
		gap: 8px;
		align-items: center;
	}
	.rej-head {
		display: flex;
		gap: 8px;
		align-items: center;
		font-size: 15px;
		font-weight: 700;
		color: var(--red);
	}
	.grp {
		display: flex;
		gap: 8px;
		align-items: center;
		font-size: 14px;
		font-weight: 700;
		padding-top: 6px;
	}
	.grp.sep {
		border-top: 1px solid var(--divider);
		padding-top: 10px;
	}
	.grow {
		flex-grow: 1;
		min-width: 0;
	}
	.line {
		display: flex;
		flex-direction: column;
		gap: 3px;
		padding: 9px 0;
		border-top: 1px solid var(--divider);
	}
	.asked {
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.5px;
		text-transform: uppercase;
		color: var(--muted);
		overflow-wrap: anywhere;
	}
	.line-main {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		margin-top: 3px;
	}
	.what {
		flex-grow: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.product {
		font-size: 15px;
		overflow-wrap: anywhere;
	}
	.price {
		white-space: nowrap;
	}
	.not-ordered {
		margin: 0;
		display: flex;
		gap: 8px;
		align-items: flex-start;
		font-size: 14px;
		color: var(--muted);
	}
	.not-ordered :global(svg) {
		margin-top: 2px;
	}
	.flags-toggle {
		align-self: flex-start;
		display: flex;
		gap: 8px;
		align-items: center;
		min-height: 44px;
		padding: 0;
		border: 0;
		background: none;
		color: #6b5400;
		font-size: 14px;
		font-weight: 600;
		text-align: left;
		cursor: pointer;
	}
	.chev {
		display: inline-flex;
		transition: transform 0.15s;
	}
	.chev.open {
		transform: rotate(180deg);
	}
	.flags {
		display: flex;
		flex-direction: column;
		gap: 8px;
		background: #fffbea;
		border: 1px solid #f1e3a0;
		border-radius: 10px;
		padding: 12px 14px;
		font-size: 14px;
	}
	.flags ul {
		margin: 0;
		padding-left: 18px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.send {
		margin-top: 4px;
	}
</style>
