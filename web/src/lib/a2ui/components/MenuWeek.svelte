<script lang="ts">
	/**
	 * A weekly menu `show_menu` stored (docs/design 40 and 41, UI-06; docs/specs/a2ui.md
	 * U5). Loads `GET /api/v1/chat/menus/{menuId}`. Mon to Fri, one dish a day, each
	 * with its own swap button, then one order from the whole menu.
	 */
	import { untrack } from 'svelte';
	import '../cards.css';
	import { chatContext } from '../context';
	import { dayName, t } from '../i18n';
	import { Loaded } from '../load.svelte';
	import type { ChatMenu, MenuDay } from '../types';
	import CardShell from './CardShell.svelte';
	import Icon from './Icon.svelte';

	const ORDER = ['mon', 'tue', 'wed', 'thu', 'fri'] as const;

	let { menuId, surfaceId, componentId }: { menuId: string; surfaceId: string; componentId: string } = $props();
	const { store, data, lang, revision } = chatContext();
	const L = $derived(lang());

	const loaded = new Loaded<ChatMenu>(() =>
		data.getMenu ? data.getMenu(menuId) : Promise.reject(new Error('This page cannot load menus'))
	);

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
	/** "80 portions each" when every day has the same count; otherwise each row says its own. */
	const samePortions = $derived(days.length > 0 && days.every((d) => d.portions === days[0].portions) ? days[0].portions : null);
	const built = $derived(store.actedOn(surfaceId, `${componentId}#build`) === 'yes');

	function swapKey(d: MenuDay): string {
		return `${componentId}#swap:${d.day}:${d.recipe_id}`;
	}

	function swap(d: MenuDay) {
		if (built || store.actedOn(surfaceId, swapKey(d))) return;
		store.markActed(surfaceId, swapKey(d), 'yes');
		store.emit(surfaceId, componentId, 'menu_swap_day', { menuId: loaded.value?.menu_id ?? menuId, day: d.day });
	}

	function build() {
		if (built || !days.length) return;
		store.markActed(surfaceId, `${componentId}#build`, 'yes');
		store.emit(surfaceId, componentId, 'menu_build', { menuId: loaded.value?.menu_id ?? menuId });
	}

	function detail(d: MenuDay): string {
		const parts: string[] = [];
		if (samePortions === null) parts.push(t(L, 'portionsCount', { n: d.portions }));
		if (typeof d.linked_count === 'number' && typeof d.ingredient_count === 'number') {
			parts.push(t(L, 'linkedShort', { linked: d.linked_count, total: d.ingredient_count }));
		}
		return parts.join(', ');
	}
</script>

{#snippet each()}
	{#if samePortions !== null}<span class="a2-cap each">{t(L, 'portionsEach', { n: samePortions })}</span>{/if}
{/snippet}

<CardShell testid="menu-week" title={t(L, 'menuTitle')} status={loaded.status} onretry={() => loaded.load()} aside={each}>
	{#if loaded.value}
		{#if !days.length}
			<p class="a2-cap">{t(L, 'noDays')}</p>
		{:else}
			<ul class="days" aria-label={t(L, 'weeklyMenu')}>
				{#each days as d (d.day)}
					{@const asked = Boolean(store.actedOn(surfaceId, swapKey(d)))}
					<li class="day" class:asked data-testid="menu-day">
						<b class="dname">{dayName(d.day, L)}</b>
						<span class="dish">
							<span class="name">{d.name}</span>
							{#if asked}
								<span class="a2-cap">{t(L, 'swapping')}</span>
							{:else if detail(d)}
								<span class="a2-cap">{detail(d)}</span>
							{/if}
						</span>
						{#if !built}
							<button
								type="button"
								class="swap"
								aria-label={t(L, 'swapDay', { day: dayName(d.day, L, 'long') })}
								title={t(L, 'swapDay', { day: dayName(d.day, L, 'long') })}
								disabled={asked}
								onclick={() => swap(d)}><Icon name="swap" stroke="var(--petrol)" /></button
							>
						{/if}
					</li>
				{/each}
			</ul>
			<span class="a2-cap">{t(L, 'dietHint')}</span>
			{#if built}
				<p class="a2-done" data-testid="menu-built"><Icon name="check" size={18} stroke="#3f5a00" weight={2.6} />{t(L, 'menuBuilt')}</p>
			{:else}
				<button type="button" class="a2-main" onclick={build} data-testid="menu-build">{t(L, 'buildMenu')}</button>
			{/if}
		{/if}
	{/if}
</CardShell>

<style>
	.each {
		white-space: nowrap;
	}
	.days {
		list-style: none;
		margin: -4px 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
	}
	.day {
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: 52px;
		padding: 4px 0;
		border-top: 1px solid var(--divider);
	}
	.day:first-child {
		border-top: 0;
	}
	.day.asked {
		background: var(--ok-bg);
		margin: 0 -8px;
		padding: 4px 8px;
		border-radius: 6px;
	}
	.dname {
		width: 40px;
		flex-shrink: 0;
		font-size: 15px;
	}
	.dish {
		flex-grow: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.name {
		font-size: 15px;
		overflow-wrap: anywhere;
	}
	.swap {
		width: 44px;
		height: 44px;
		flex-shrink: 0;
		margin-right: -6px;
		border: 0;
		border-radius: 22px;
		background: transparent;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.swap :global(svg) {
		width: 30px;
		height: 30px;
		padding: 7px;
		border-radius: 15px;
		background: var(--chip);
	}
	.swap:disabled {
		opacity: 0.5;
		cursor: default;
	}
</style>
