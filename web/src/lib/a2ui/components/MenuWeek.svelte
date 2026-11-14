<script lang="ts">
	/**
	 * A weekly menu `show_menu` stored (design UI-06 sketch; docs/specs/a2ui.md U5).
	 * Loads `GET /api/v1/chat/menus/{menuId}`. Mon to Fri, one dish a day: tap a day
	 * to see it and swap it, then build one order from the whole menu.
	 */
	import { untrack } from 'svelte';
	import '../cards.css';
	import { chatContext } from '../context';
	import { dayName, t } from '../i18n';
	import { Loaded } from '../load.svelte';
	import type { ChatMenu, MenuDay } from '../types';
	import CardShell from './CardShell.svelte';
	import RecipeImage from './RecipeImage.svelte';

	const ORDER = ['mon', 'tue', 'wed', 'thu', 'fri'] as const;

	let { menuId, surfaceId, componentId }: { menuId: string; surfaceId: string; componentId: string } = $props();
	const { store, data, lang, revision } = chatContext();
	const L = $derived(lang());

	const loaded = new Loaded<ChatMenu>(() =>
		data.getMenu ? data.getMenu(menuId) : Promise.reject(new Error('This page cannot load menus'))
	);
	let selected = $state<string | null>(null);

	$effect(() => {
		void menuId;
		untrack(() => loaded.load());
	});

	$effect(() => {
		const r = revision?.();
		if (r === undefined) return;
		untrack(() => loaded.refresh());
	});

	const days = $derived.by((): MenuDay[] => {
		const list = loaded.value?.days ?? [];
		return ORDER.map((d) => list.find((x) => x.day === d)).filter((x): x is MenuDay => Boolean(x));
	});
	const day = $derived(days.find((d) => d.day === selected) ?? days[0] ?? null);
	const built = $derived(store.actedOn(surfaceId, `${componentId}#build`) === 'yes');
	const swapped = $derived(day ? store.actedOn(surfaceId, `${componentId}#swap:${day.day}:${day.recipe_id}`) === 'yes' : false);

	function swap(d: MenuDay) {
		if (built || swapped) return;
		store.markActed(surfaceId, `${componentId}#swap:${d.day}:${d.recipe_id}`, 'yes');
		store.emit(surfaceId, componentId, 'menu_swap_day', { menuId: loaded.value?.menu_id ?? menuId, day: d.day });
	}

	function build() {
		if (built || !days.length) return;
		store.markActed(surfaceId, `${componentId}#build`, 'yes');
		store.emit(surfaceId, componentId, 'menu_build', { menuId: loaded.value?.menu_id ?? menuId });
	}

	function short(name: string): string {
		const first = name.split(/[\s,-]+/)[0] ?? name;
		return first.length > 12 ? `${first.slice(0, 11)}…` : first;
	}
</script>

<CardShell testid="menu-week" eyebrow={t(L, 'weeklyMenu')} title={t(L, 'menuTitle')} status={loaded.status} onretry={() => loaded.load()}>
	{#if loaded.value}
		{#if !days.length}
			<p class="a2-cap">{t(L, 'noDays')}</p>
		{:else}
			<div class="days" role="group" aria-label={t(L, 'weeklyMenu')}>
				{#each days as d (d.day)}
					<button
						type="button"
						class="day"
						class:on={day?.day === d.day}
						aria-pressed={day?.day === d.day}
						aria-label={t(L, 'dayDish', { day: dayName(d.day, L, 'long'), name: d.name })}
						onclick={() => (selected = d.day)}
					>
						<b>{dayName(d.day, L)}</b><span class="dish">{short(d.name)}</span>
					</button>
				{/each}
			</div>
			{#if day}
				<div class="mini" data-testid="menu-day">
					<div class="mini-head">
						<RecipeImage url={day.image_url} size={52} />
						<div class="mini-who">
							<b>{t(L, 'dayDish', { day: dayName(day.day, L), name: day.name })}</b>
							<span class="a2-cap">
								{typeof day.linked_count === 'number' && typeof day.ingredient_count === 'number'
									? t(L, 'portionsLinked', { n: day.portions, linked: day.linked_count, total: day.ingredient_count })
									: t(L, 'portionsCount', { n: day.portions })}
							</span>
						</div>
					</div>
					{#if swapped}
						<span class="a2-cap">{t(L, 'swapDayAsked', { day: dayName(day.day, L, 'long') })}</span>
					{:else if !built}
						<div class="a2-actions">
							<button type="button" class="a2-pill" onclick={() => swap(day)}>{t(L, 'swapDay', { day: dayName(day.day, L, 'long') })}</button>
						</div>
					{/if}
				</div>
			{/if}
			<span class="a2-cap">{t(L, 'dietHint')}</span>
			{#if built}
				<p class="a2-done" data-testid="menu-built">{t(L, 'menuBuilt')}</p>
			{:else}
				<button type="button" class="a2-main" onclick={build} data-testid="menu-build">{t(L, 'buildMenu')}</button>
			{/if}
		{/if}
	{/if}
</CardShell>

<style>
	.days {
		display: flex;
		gap: 6px;
	}
	.day {
		flex: 1 1 0;
		min-width: 0;
		min-height: 48px;
		padding: 4px 2px;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--card);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		color: var(--muted);
		cursor: pointer;
	}
	.day b {
		font-size: 14px;
		color: var(--ink);
	}
	.day.on {
		border: 2px solid var(--petrol);
	}
	.dish {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.mini {
		background: var(--page);
		border-radius: 10px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.mini-head {
		display: flex;
		gap: 10px;
		align-items: center;
	}
	.mini-who {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.mini-who b {
		font-size: 15px;
		overflow-wrap: anywhere;
	}
</style>
