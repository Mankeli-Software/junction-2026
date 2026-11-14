<script lang="ts">
	/**
	 * The "Recipe I read" card (design UI-03, Chat-A2, Chat-A3; docs/plans/80-recipe-photo.md
	 * §2.1, §6.2). Loads the draft by id, lets the buyer fix the portions and every
	 * ingredient row, then confirms the draft through the API itself and tells S.I.MO
	 * (`recipe_confirmed`). Nothing is quoted or ordered here.
	 *
	 * A dish photo that matched one of our recipes starts from that recipe (read-only,
	 * `ingredients`), with a switch to the AI's own reading (`ai_reading`, editable).
	 */
	import { tick, untrack } from 'svelte';
	import '../cards.css';
	import { chatContext } from '../context';
	import { measure, parseAmount, scaled, amount as formatAmount } from '../format';
	import { t } from '../i18n';
	import { Loaded } from '../load.svelte';
	import type { ConfirmDraft, DraftIngredient, DraftIngredientInput, RecipeDraft } from '../types';
	import CardShell from './CardShell.svelte';
	import Icon from './Icon.svelte';
	import RecipeImage from './RecipeImage.svelte';

	interface Row {
		key: number;
		/** The ingredient's index in the draft; new rows get the next free one. */
		index: number;
		text: string;
		amountText: string;
		unit: string;
		order: boolean;
		low: boolean;
		note: string | null;
		product_id: string | null;
		edited: boolean;
	}

	const UNITS = ['g', 'kg', 'dl', 'l', 'rkl', 'tl', 'kpl'];
	const MAX_ROWS = 60;
	const MAX_INDEX = 999;

	let { draftId, surfaceId, componentId }: { draftId: string; surfaceId: string; componentId: string } = $props();
	const { store, data, lang } = chatContext();
	const L = $derived(lang());
	const uid = $props.id();

	let currentId = $state('');
	let portions = $state(10);
	let rows = $state<Row[]>([]);
	let original = $state.raw<DraftIngredient[]>([]);
	let mode = $state<'ours' | 'ai'>('ai');
	let busy = $state(false);
	let failed = $state(false);
	let saved = $state(false);
	let nextKey = 0;

	const loaded = new Loaded<RecipeDraft>(async () => {
		const value = await data.getDraft(currentId);
		init(value);
		return value;
	});

	$effect(() => {
		const id = draftId;
		untrack(() => {
			// After "Edit as new draft" the card shows the copy, also when drawn again.
			const remembered = store.actedOn(surfaceId, componentId);
			currentId = remembered?.startsWith('copy:') ? remembered.slice(5) : id;
			loaded.load();
		});
	});

	function toRow(i: DraftIngredient): Row {
		return {
			key: nextKey++,
			index: i.index,
			text: i.text,
			amountText: formatAmount(i.amount),
			unit: i.unit ?? '',
			order: i.order ?? true,
			low: i.confidence === 'low',
			note: i.note ?? null,
			product_id: i.product_id ?? null,
			edited: false
		};
	}

	function init(value: RecipeDraft) {
		const hasChoice = Boolean(value.matched_recipe && value.ai_reading);
		mode = hasChoice ? 'ours' : 'ai';
		original = hasChoice ? (value.ai_reading ?? []) : value.ingredients;
		rows = original.map(toRow);
		portions = value.portions;
		failed = false;
	}

	const draft = $derived(loaded.value);
	const editable = $derived(draft?.status === 'draft' && !busy);
	const hasChoice = $derived(Boolean(draft?.matched_recipe && draft?.ai_reading));
	/** The servings the amounts are written for. The AI's own reading has none in the API. */
	const servings = $derived(mode === 'ours' || !hasChoice ? (draft?.servings_on_source ?? null) : null);
	const lowLeft = $derived(rows.filter((r) => r.low && !r.edited).length);
	const invalid = $derived(mode === 'ai' && rows.some((r) => parseAmount(r.amountText) === undefined));
	const nothingTicked = $derived(mode === 'ai' && !rows.some((r) => r.order && r.text.trim()));
	const ours = $derived(draft?.ingredients ?? []);
	const linked = $derived(ours.filter((i) => i.product_id).length);

	function setPortions(n: number) {
		if (Number.isInteger(n) && n >= 1 && n <= 1000) portions = n;
	}

	async function addRow() {
		if (rows.length >= MAX_ROWS) return;
		const index = Math.min(MAX_INDEX, Math.max(-1, ...rows.map((r) => r.index), ...original.map((i) => i.index)) + 1);
		const row: Row = {
			key: nextKey++,
			index,
			text: '',
			amountText: '',
			unit: '',
			order: true,
			low: false,
			note: null,
			product_id: null,
			edited: true
		};
		rows.push(row);
		await tick();
		document.getElementById(`${uid}-text-${row.key}`)?.focus();
	}

	function removeRow(key: number) {
		rows = rows.filter((r) => r.key !== key);
	}

	function ingredients(): DraftIngredientInput[] {
		return rows
			.filter((r) => r.text.trim())
			.map((r) => ({
				index: r.index,
				text: r.text.trim().slice(0, 200),
				amount: parseAmount(r.amountText) ?? null,
				unit: r.unit.trim().slice(0, 20) || null,
				confidence: r.low && !r.edited ? 'low' : 'high',
				note: r.edited ? null : r.note,
				order: r.order,
				product_id: r.product_id
			}));
	}

	function rowsChanged(): boolean {
		if (rows.length !== original.length) return true;
		return rows.some((r, i) => {
			const o = original[i];
			return (
				r.edited ||
				r.index !== o.index ||
				r.order !== (o.order ?? true) ||
				r.text !== o.text ||
				r.unit !== (o.unit ?? '') ||
				parseAmount(r.amountText) !== (o.amount ?? null)
			);
		});
	}

	async function run(action: () => Promise<void>) {
		busy = true;
		failed = false;
		try {
			await action();
		} catch {
			failed = true;
		} finally {
			busy = false;
		}
	}

	function confirm() {
		if (!draft || !editable || invalid || nothingTicked) return;
		const body: ConfirmDraft = { portions, use_ai_reading: false };
		if (mode === 'ai') {
			if (hasChoice) body.use_ai_reading = true;
			if (hasChoice || rowsChanged()) body.ingredients = ingredients();
		}
		return run(async () => {
			const value = await data.confirmDraft(draft.draft_id, body);
			loaded.set(value);
			store.emit(surfaceId, componentId, 'recipe_confirmed', { draftId: value.draft_id, portions: value.portions });
		});
	}

	function startOver() {
		if (!draft || !editable) return;
		return run(async () => {
			const value = await data.discardDraft(draft.draft_id);
			loaded.set(value);
			store.emit(surfaceId, componentId, 'recipe_discarded', { draftId: value.draft_id });
		});
	}

	function editAsNew() {
		const copy = data.copyDraft;
		if (!draft || busy || !copy) return;
		const from = draft.draft_id;
		return run(async () => {
			const value = await copy(from);
			init(value);
			currentId = value.draft_id;
			loaded.set(value);
			saved = false;
			store.markActed(surfaceId, componentId, `copy:${value.draft_id}`);
			store.emit(surfaceId, componentId, 'recipe_edit_as_new', { draftId: value.draft_id, copiedFrom: from });
		});
	}
</script>

{#snippet stepper()}
	<div class="stepper" role="group" aria-labelledby="{uid}-portions">
		<button
			type="button"
			class="a2-round"
			aria-label={t(L, 'fewerPortions')}
			disabled={!editable || portions <= 1}
			onclick={() => setPortions(portions - 1)}><Icon name="minus" weight={2.4} /></button
		>
		<input
			class="a2-in num portions"
			inputmode="numeric"
			value={portions}
			disabled={!editable}
			aria-labelledby="{uid}-portions"
			onchange={(e) => {
				setPortions(Number(e.currentTarget.value.trim()));
				e.currentTarget.value = String(portions);
			}}
		/>
		<button
			type="button"
			class="a2-round"
			aria-label={t(L, 'morePortions')}
			disabled={!editable || portions >= 1000}
			onclick={() => setPortions(portions + 1)}><Icon name="plus" weight={2.4} /></button
		>
	</div>
{/snippet}

{#snippet actions(mainLabel: string)}
	{#if nothingTicked}<p class="a2-cap warn">{t(L, 'nothingToOrder')}</p>{/if}
	{#if invalid}<p class="a2-cap warn">{t(L, 'fixAmounts')}</p>{/if}
	{#if failed}<p class="a2-cap warn" role="alert">{t(L, 'actionFailed')}</p>{/if}
	<div class="a2-actions">
		<button type="button" class="a2-main" disabled={!editable || invalid || nothingTicked} onclick={confirm} data-testid="confirm-recipe">
			<Icon name="check" size={18} weight={2.6} />{mainLabel}
		</button>
		<button type="button" class="a2-sec" disabled={!editable} onclick={startOver}>{t(L, 'startOver')}</button>
	</div>
{/snippet}

<CardShell
	testid="recipe-draft-card"
	eyebrow={draft?.status === 'confirmed'
		? t(L, 'recipeIRead')
		: draft?.source === 'dish_photo'
			? t(L, 'fromDish')
			: t(L, 'fromNotebook')}
	title={draft?.status === 'confirmed' ? undefined : t(L, 'recipeIRead')}
	status={loaded.status}
	onretry={() => loaded.load()}
>
	{#if draft}
		{#if draft.status === 'draft'}
			{#if draft.is_guess}
				<p class="a2-banner" data-testid="guess-banner"><Icon name="alert" size={18} stroke="#6b5400" />{t(L, 'guessBanner')}</p>
			{/if}

			{#if hasChoice}
				<div class="switch" role="radiogroup" aria-label={t(L, 'whichRecipe')}>
					<button type="button" role="radio" aria-checked={mode === 'ours'} class:on={mode === 'ours'} disabled={!editable} onclick={() => (mode = 'ours')}
						>{t(L, 'ourRecipe')}</button
					>
					<button type="button" role="radio" aria-checked={mode === 'ai'} class:on={mode === 'ai'} disabled={!editable} onclick={() => (mode = 'ai')}
						>{t(L, 'aiSaw')}</button
					>
				</div>
			{/if}

			{#if mode === 'ours' && draft.matched_recipe}
				{@const hit = draft.matched_recipe}
				<div class="recipe-head" data-testid="matched-recipe">
					<RecipeImage url={hit.image_url} />
					<div class="recipe-name">
						<b>{hit.name}</b>
						{#if hit.diet_tags.length}
							<span class="tags">{#each hit.diet_tags as tag (tag)}<span class="a2-tag soft">{tag}</span>{/each}</span>
						{/if}
					</div>
				</div>
				<span class="a2-cap">{t(L, 'dietHintLong')}</span>
				<div class="inline-field">
					<span class="a2-lbl grow" id="{uid}-portions">{t(L, 'portions')}</span>
					{@render stepper()}
				</div>
				<div class="list-head">
					<span class="a2-lbl">{t(L, 'ingredientsFor', { n: portions })}</span>
					<span class="a2-cap">{t(L, 'linkedOf', { n: linked, total: ours.length })}</span>
				</div>
				<ul class="a2-list tight">
					{#each ours as i (i.index)}
						<li class:muted={!i.order}>
							<span>{i.text}</span>
							<b>{measure(scaled(i.amount ?? null, servings, portions), i.unit)}</b>
							{#if !i.order}<span class="a2-tag soft">{t(L, 'notOrderedTag')}</span>
							{:else if i.product_id}<span class="a2-tag can">{t(L, 'weOrder')}</span>
							{:else}<span class="a2-tag soft">{t(L, 'weSearch')}</span>{/if}
						</li>
					{/each}
				</ul>
				<span class="a2-cap">{t(L, 'ourRecipeNote')}</span>
				{@render actions(t(L, 'useThisRecipe'))}
			{:else}
				<label class="field">
					<span class="a2-lbl">{t(L, 'dish')}</span>
					<input class="a2-in" value={draft.dish} readonly />
				</label>

				<div class="field">
					<span class="a2-lbl" id="{uid}-portions">{t(L, 'portions')}</span>
					{@render stepper()}
					<span class="a2-cap">{servings ? t(L, 'sourceMakes', { n: servings, portions }) : t(L, 'sourceUnknown')}</span>
				</div>

				<div class="list-head">
					<span class="a2-lbl">{t(L, 'ingredients')}</span>
					{#if lowLeft > 0}<span class="a2-tag">{t(L, 'toCheck', { n: lowLeft })}</span>{/if}
				</div>
				<ul class="rows">
					{#each rows as row (row.key)}
						{@const parsed = parseAmount(row.amountText)}
						{@const bad = parsed === undefined}
						{@const unsure = row.low && !row.edited}
						{@const preview = scaled(parsed ?? null, servings, portions)}
						{@const name = row.text.trim() || t(L, 'newIngredient')}
						<li class="row" class:low={unsure} data-testid="ingredient-row" data-low={unsure}>
							<input
								type="checkbox"
								class="tick"
								bind:checked={row.order}
								disabled={!editable}
								aria-label={t(L, 'orderRow', { name })}
								onchange={() => (row.edited = true)}
							/>
							<div class="cells">
								<input
									id="{uid}-text-{row.key}"
									class="a2-in"
									class:off={!row.order}
									aria-label={t(L, 'ingredient')}
									placeholder={t(L, 'newIngredient')}
									bind:value={row.text}
									maxlength="200"
									disabled={!editable}
									oninput={() => (row.edited = true)}
								/>
								<div class="amt">
									<input
										class="a2-in num"
										class:bad
										class:unsure={unsure && !bad}
										aria-label={t(L, 'amount')}
										aria-invalid={bad}
										placeholder={t(L, 'amount')}
										inputmode="decimal"
										bind:value={row.amountText}
										disabled={!editable}
										oninput={() => (row.edited = true)}
									/>
									<input
										class="a2-in"
										aria-label={t(L, 'unit')}
										placeholder={t(L, 'unit')}
										list="{uid}-units"
										bind:value={row.unit}
										maxlength="20"
										disabled={!editable}
										oninput={() => (row.edited = true)}
									/>
								</div>
								{#if bad}
									<span class="a2-cap warn">{t(L, 'amountInvalid')}</span>
								{:else if unsure}
									<span class="note"><span class="a2-tag">{t(L, 'checkThis')}</span>{row.note ?? ''}</span>
								{:else if !row.order}
									<span class="note"><span class="a2-tag soft">{t(L, 'notOrderedTag')}</span></span>
								{:else if servings && preview !== null && servings !== portions}
									<span class="a2-cap">{t(L, 'forPortions', { amount: measure(preview, row.unit), n: portions })}</span>
								{/if}
							</div>
							<button
								type="button"
								class="del"
								aria-label={t(L, 'removeRow', { name })}
								disabled={!editable}
								onclick={() => removeRow(row.key)}><Icon name="trash" stroke="var(--muted)" /></button
							>
						</li>
					{/each}
				</ul>
				<datalist id="{uid}-units">
					{#each UNITS as u (u)}<option value={u}></option>{/each}
				</datalist>
				<button type="button" class="add" disabled={!editable || rows.length >= MAX_ROWS} onclick={addRow}>
					<Icon name="plus" weight={2.4} />{t(L, 'addRow')}
				</button>
				<span class="a2-cap">{t(L, 'nothingYet')}</span>
				{@render actions(t(L, 'confirmRecipe'))}
			{/if}
		{:else if draft.status === 'confirmed'}
			<p class="a2-done" data-testid="draft-confirmed">
				<Icon name="check" size={18} stroke="#3f5a00" weight={2.6} />{t(L, 'confirmedAs', { dish: draft.dish, n: draft.portions })}
			</p>
			<ul class="a2-list tight">
				{#each draft.scaled as i (i.index)}
					<li class:muted={!i.order}>
						<span>{i.text}</span>
						<b>{measure(i.amount, i.unit)}</b>
						{#if !i.order}<span class="a2-tag soft">{t(L, 'notOrderedTag')}</span>{/if}
					</li>
				{/each}
			</ul>
			{#if failed}<p class="a2-cap warn" role="alert">{t(L, 'actionFailed')}</p>{/if}
			<div class="a2-actions">
				{#if data.copyDraft}
					<button type="button" class="a2-ghost" disabled={busy} onclick={editAsNew}><Icon name="pencil" size={15} />{t(L, 'editAsNew')}</button>
				{/if}
				<!-- Mock (docs/plans/80-recipe-photo.md decision 16): shows saved, stores nothing. -->
				<button type="button" class="a2-ghost" class:saved disabled={saved} onclick={() => (saved = true)} data-testid="save-to-aimo">
					{#if saved}<Icon name="check" size={15} weight={2.6} />{t(L, 'savedToAimo')}{:else}{t(L, 'saveToAimo')}{/if}
				</button>
			</div>
		{:else}
			<p class="a2-cap discarded" data-testid="draft-discarded">{t(L, 'discarded')}</p>
		{/if}
	{/if}
</CardShell>

<style>
	.field {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.inline-field {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.grow {
		flex-grow: 1;
	}
	.stepper {
		display: flex;
		gap: 6px;
		align-items: center;
	}
	.portions {
		width: 90px;
		font-weight: 700;
	}
	.switch {
		display: flex;
		background: var(--chip);
		border-radius: 8px;
		padding: 3px;
		gap: 3px;
	}
	.switch button {
		flex: 1;
		min-height: 42px;
		border: 0;
		border-radius: 6px;
		background: transparent;
		font-size: 14px;
		font-weight: 700;
		color: var(--petrol);
		cursor: pointer;
	}
	.switch button.on {
		background: var(--card);
		box-shadow: 0 1px 2px rgb(16 48 63 / 15%);
	}
	.recipe-head {
		display: flex;
		gap: 12px;
		align-items: center;
	}
	.recipe-name {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-width: 0;
	}
	.recipe-name b {
		font-size: 18px;
	}
	.tags {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
	}
	.list-head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 8px;
	}
	.tight {
		margin-top: -6px;
	}
	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.row {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		padding: 10px 12px;
		border: 1px solid var(--divider);
		border-radius: 8px;
		background: var(--card);
	}
	.row.low {
		background: var(--yellow-note);
		border-color: #f1e3a0;
	}
	.tick {
		width: 20px;
		height: 20px;
		margin: 11px 0 0;
		flex-shrink: 0;
		accent-color: var(--petrol);
	}
	.cells {
		flex-grow: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.cells .off {
		color: var(--muted);
		text-decoration: line-through;
	}
	.amt {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 74px;
		gap: 6px;
		max-width: 200px;
	}
	.note {
		display: flex;
		gap: 6px;
		align-items: center;
		font-size: 13px;
	}
	.del {
		width: 36px;
		height: 36px;
		margin-top: 3px;
		flex-shrink: 0;
		border-radius: 18px;
		border: 0;
		background: transparent;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.del:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.add {
		align-self: flex-start;
		display: flex;
		gap: 6px;
		align-items: center;
		min-height: 44px;
		padding: 0 16px;
		border-radius: 22px;
		border: 1px dashed var(--petrol);
		background: var(--card);
		color: var(--petrol);
		font-weight: 700;
		cursor: pointer;
	}
	.add:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.discarded {
		margin: 0;
		font-size: 14px;
	}
</style>
