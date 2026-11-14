<script lang="ts">
	/**
	 * One recipe from our data, scaled to the buyer's portions (design UI-04). Loads
	 * `GET /api/v1/recipes/{id}?portions=`. Names stay in Finnish (the recipe data has
	 * no English). "We order" only for ingredients with a product link.
	 */
	import { untrack } from 'svelte';
	import '../cards.css';
	import { chatContext } from '../context';
	import { measure } from '../format';
	import { t } from '../i18n';
	import { Loaded } from '../load.svelte';
	import type { Recipe } from '../types';
	import CardShell from './CardShell.svelte';
	import Icon from './Icon.svelte';
	import RecipeImage from './RecipeImage.svelte';

	const SUMMARY_NAMES = 4;

	let {
		recipeId,
		portions,
		surfaceId,
		componentId
	}: { recipeId: string; portions: number; surfaceId: string; componentId: string } = $props();
	const { store, data, lang } = chatContext();
	const L = $derived(lang());
	const uid = $props.id();

	const loaded = new Loaded<Recipe>(() => data.getRecipe(recipeId, portions));
	let open = $state(false);

	$effect(() => {
		void recipeId;
		void portions;
		untrack(() => loaded.load());
	});

	const recipe = $derived(loaded.value);
	const acted = $derived(store.actedOn(surfaceId, componentId));
	const linked = $derived(recipe ? recipe.ingredients.filter((i) => i.product_id).length : 0);
	/** Diet tags are not in `Recipe` today (only in `RecipeHit`); shown when the API sends them. */
	const dietTags = $derived.by(() => {
		const tags = (recipe as (Recipe & { diet_tags?: unknown }) | null)?.diet_tags;
		return Array.isArray(tags) ? tags.filter((x): x is string => typeof x === 'string').slice(0, 6) : [];
	});
	const summary = $derived.by(() => {
		if (!recipe) return '';
		const names = recipe.ingredients.map((i) => i.name);
		const head = names.slice(0, SUMMARY_NAMES).join(', ');
		return names.length > SUMMARY_NAMES ? t(L, 'andMore', { names: head, n: names.length - SUMMARY_NAMES }) : head;
	});

	function use() {
		if (!recipe || acted) return;
		store.markActed(surfaceId, componentId, 'selected');
		store.emit(surfaceId, componentId, 'recipe_selected', { recipeId: recipe.recipe_id, portions: recipe.portions });
	}

	function swap() {
		if (!recipe || acted) return;
		store.markActed(surfaceId, componentId, 'swap');
		store.emit(surfaceId, componentId, 'recipe_swap', { recipeId: recipe.recipe_id });
	}
</script>

<CardShell testid="recipe-card" status={loaded.status} variant={acted === 'selected' ? 'done' : acted === 'swap' ? 'faded' : 'plain'} onretry={() => loaded.load()}>
	{#if recipe}
		<div class="head">
			<RecipeImage url={recipe.image_url} />
			<div class="who">
				<b class="name">{recipe.name}</b>
				{#if acted === 'selected'}
					<span class="chosen"><Icon name="check" size={15} stroke="#3f5a00" weight={2.6} />{t(L, 'usingThis', { n: recipe.portions })}</span>
				{:else}
					<span class="a2-cap">{t(L, 'portionsLinked', { n: recipe.portions, linked, total: recipe.ingredients.length })}</span>
					{#if dietTags.length}
						<span class="tags">{#each dietTags as tag (tag)}<span class="a2-tag soft">{tag}</span>{/each}</span>
					{/if}
				{/if}
			</div>
		</div>

		{#if !acted}
			{#if open}
				<ul class="a2-list" id="{uid}-ingredients" data-testid="recipe-ingredients">
					{#each recipe.ingredients as i (i.index)}
						<li>
							<span>{i.name}</span>
							<b>{measure(i.quantity, i.unit)}</b>
							{#if i.product_id}<span class="a2-tag can">{t(L, 'weOrder')}</span>
							{:else}<span class="a2-tag soft">{t(L, 'notOrderedTag')}</span>{/if}
						</li>
					{/each}
				</ul>
			{:else if summary}
				<span class="summary">{summary}</span>
			{/if}
			<span class="a2-cap">{t(L, 'dietHint')}</span>
			<div class="a2-actions">
				<button type="button" class="a2-pill lime" onclick={use}><Icon name="check" size={15} weight={2.6} />{t(L, 'useThis')}</button>
				<button type="button" class="a2-pill" onclick={swap}>{t(L, 'swap')}</button>
				<button type="button" class="a2-pill" aria-expanded={open} aria-controls="{uid}-ingredients" onclick={() => (open = !open)}
					>{open ? t(L, 'hideIngredients') : t(L, 'showIngredients')}</button
				>
			</div>
		{:else if acted === 'swap'}
			<span class="a2-cap">{t(L, 'swapAsked')}</span>
		{/if}
	{/if}
</CardShell>

<style>
	.head {
		display: flex;
		gap: 12px;
		align-items: center;
	}
	.who {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.name {
		font-size: 18px;
		overflow-wrap: anywhere;
	}
	.chosen {
		display: flex;
		gap: 6px;
		align-items: center;
		font-size: 14px;
		font-weight: 700;
		color: #3f5a00;
	}
	.tags {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.summary {
		font-size: 14px;
		color: var(--muted-2);
	}
</style>
