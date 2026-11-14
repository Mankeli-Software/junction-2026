<script lang="ts">
	/**
	 * Renders one component of a surface by id (catalog.json). Layout components
	 * show only the model's own words, as plain text. Domain cards get ids only and
	 * load the engine's data themselves (docs/specs/a2ui.md §3).
	 */
	import Self from './Node.svelte';
	import { buttonAction } from './actions';
	import { chatContext } from './context';
	import { t } from './i18n';
	import { LAYOUT_COMPONENTS, SIMO_COMPONENTS } from './protocol';
	import { ids, int, str } from './resolve';
	import type { Surface } from './surfaces.svelte';
	import './cards.css';
	import MenuWeek from './components/MenuWeek.svelte';
	import QuoteCard from './components/QuoteCard.svelte';
	import RecipeCard from './components/RecipeCard.svelte';
	import RecipeDraftCard from './components/RecipeDraftCard.svelte';
	import SentNotice from './components/SentNotice.svelte';

	const MAX_DEPTH = 8;
	const KNOWN = new Set<string>(SIMO_COMPONENTS);

	let { surface, id, depth }: { surface: Surface; id: string; depth: number } = $props();
	const { store, lang, domainCards } = chatContext();
	const c = $derived(surface.components[id]);
	const action = $derived(c?.component === 'Button' ? buttonAction(c.action) : null);
	/** The Button pressed on this surface: quick answers are one tap, then all go read-only. */
	const pressedId = $derived(store.actedOn(surface.id, '#button'));
	const pressed = $derived(pressedId === id);

	$effect(() => {
		if (c && !KNOWN.has(c.component)) console.warn(`A2UI: unknown component "${c.component}" on surface ${surface.id}`);
	});

	function press() {
		if (!action || pressedId) return;
		store.markActed(surface.id, '#button', id);
		store.emit(surface.id, id, action.name, action.context, action.paths);
	}
</script>

{#if c && depth <= MAX_DEPTH && (domainCards !== false || LAYOUT_COMPONENTS.includes(c.component))}
	{#if c.component === 'Column' || c.component === 'Row'}
		<div class={c.component === 'Row' ? 'row' : 'column'}>
			{#each ids(c.children) as child, i (`${child}-${i}`)}
				{#if child !== id}<Self {surface} id={child} depth={depth + 1} />{/if}
			{/each}
		</div>
	{:else if c.component === 'Text'}
		{@const text = str(surface, c.text, 600)}
		{#if text}
			{#if c.variant === 'heading'}<h3 class="heading">{text}</h3>
			{:else}<p class="text" class:caption={c.variant === 'caption'}>{text}</p>{/if}
		{/if}
	{:else if c.component === 'Notice'}
		{@const text = str(surface, c.text, 300)}
		{#if text}<p class="notice">{text}</p>{/if}
	{:else if c.component === 'Button'}
		{@const label = str(surface, c.label, 40)}
		{#if label && action}
			<button type="button" class="a2-pill" class:lime={c.primary === true} class:pressed disabled={Boolean(pressedId)} aria-pressed={pressed} onclick={press}
				>{label}</button
			>
		{/if}
	{:else if c.component === 'RecipeDraftCard'}
		{@const draftId = str(surface, c.draftId, 80)}
		{#if draftId}<RecipeDraftCard {draftId} surfaceId={surface.id} componentId={id} />{/if}
	{:else if c.component === 'RecipeCard'}
		{@const recipeId = str(surface, c.recipeId, 80)}
		{#if recipeId}
			<RecipeCard {recipeId} portions={int(surface, c.portions, 1, 1000) ?? 10} surfaceId={surface.id} componentId={id} />
		{/if}
	{:else if c.component === 'QuoteCard'}
		{@const quoteId = str(surface, c.quoteId, 80)}
		{#if quoteId}<QuoteCard {quoteId} surfaceId={surface.id} componentId={id} />{/if}
	{:else if c.component === 'MenuWeek'}
		{@const menuId = str(surface, c.menuId, 80)}
		{#if menuId}<MenuWeek {menuId} surfaceId={surface.id} componentId={id} />{/if}
	{:else if c.component === 'SentNotice'}
		<SentNotice />
	{:else}
		<p class="unknown" data-testid="a2ui-unknown">{t(lang(), 'unsupported')}</p>
	{/if}
{/if}

<style>
	.column {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		min-width: 0;
	}
	.heading {
		margin: 0;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 20px;
		letter-spacing: -0.2px;
		color: var(--petrol);
	}
	.text {
		margin: 0;
		font-size: 15px;
		line-height: 1.4;
		overflow-wrap: anywhere;
	}
	.caption {
		font-size: 13px;
		color: var(--muted);
	}
	.notice {
		margin: 0;
		background: var(--yellow-note);
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 14px;
		overflow-wrap: anywhere;
	}
	.a2-pill {
		font-size: 15px;
		padding: 0 16px;
	}
	.a2-pill.pressed:disabled {
		opacity: 1;
		background: var(--petrol);
		border-color: var(--petrol);
		color: #fff;
	}
	.unknown {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}
</style>
