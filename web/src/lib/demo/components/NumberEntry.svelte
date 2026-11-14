<script lang="ts" module>
	import type { IconName } from './Icon.svelte';

	export type { SetupValues } from '../types';

	export interface EntryNotice {
		icon: IconName;
		text: string;
	}
</script>

<script lang="ts">
	/**
	 * The number entry shared by the demo phone (design 10) and the webshop (#56): the
	 * visitor's number, the kitchen exclusions as chips, the notices and the submit
	 * button. The number becomes the demo account (`POST /api/v1/demo/accounts`).
	 */
	import Icon from './Icon.svelte';
	import { exclusionLabel, t } from '../i18n';
	import { COUNTRY_CODES, toE164 } from '../phone';
	import { EXCLUSIONS, type Exclusion, type Lang, type SetupValues } from '../types';

	let {
		lang,
		initial,
		notices,
		submitLabel,
		busyLabel,
		busy = false,
		error = null,
		onsubmit
	}: {
		lang: Lang;
		initial: SetupValues;
		notices: EntryNotice[];
		submitLabel: string;
		busyLabel: string;
		busy?: boolean;
		error?: 'limit' | 'failed' | null;
		onsubmit: (values: SetupValues, e164: string) => void;
	} = $props();

	// The form starts from the last values and is then the visitor's own.
	// svelte-ignore state_referenced_locally
	let countryCode = $state(initial.countryCode);
	// svelte-ignore state_referenced_locally
	let number = $state(initial.number);
	// svelte-ignore state_referenced_locally
	let exclusions = $state<Exclusion[]>([...initial.exclusions]);
	let invalid = $state(false);

	function toggle(exclusion: Exclusion) {
		exclusions = exclusions.includes(exclusion)
			? exclusions.filter((e) => e !== exclusion)
			: EXCLUSIONS.filter((e) => e === exclusion || exclusions.includes(e));
	}

	function submit(event: SubmitEvent) {
		event.preventDefault();
		const e164 = toE164(countryCode, number);
		invalid = e164 === null;
		if (e164) onsubmit({ countryCode, number, exclusions: [...exclusions] }, e164);
	}
</script>

<form class="body" onsubmit={submit} novalidate>
	<div class="card">
		<label for="phone" class="label">{t(lang, 'phoneLabel')}</label>
		<div class="number-row">
			<div class="cc">
				<select aria-label={t(lang, 'countryCode')} bind:value={countryCode}>
					{#each COUNTRY_CODES as code (code)}
						<option value={code}>{code}</option>
					{/each}
				</select>
				<Icon name="chevron-down" size={14} stroke="var(--petrol)" weight={2.5} />
			</div>
			<input
				id="phone"
				type="tel"
				inputmode="tel"
				autocomplete="tel-national"
				placeholder="40 123 4512"
				bind:value={number}
				oninput={() => (invalid = false)}
				aria-invalid={invalid}
				aria-describedby={invalid ? 'phone-error' : 'phone-hint'}
			/>
		</div>
		{#if invalid}
			<span id="phone-error" class="field-error" role="alert">
				<Icon name="alert" size={16} stroke="var(--red)" />{t(lang, 'phoneInvalid')}
			</span>
		{:else}
			<span id="phone-hint" class="hint">{t(lang, 'phoneHint')}</span>
		{/if}
	</div>

	<fieldset class="card">
		<legend class="label">{t(lang, 'kitchenAvoids')}</legend>
		<div class="chips">
			<button
				type="button"
				class="chip"
				class:on={exclusions.length === 0}
				aria-pressed={exclusions.length === 0}
				onclick={() => (exclusions = [])}
			>
				{#if exclusions.length === 0}<Icon name="check" size={14} stroke="#fff" weight={3} />{/if}
				{t(lang, 'nothing')}
			</button>
			{#each EXCLUSIONS as exclusion (exclusion)}
				{@const on = exclusions.includes(exclusion)}
				<button
					type="button"
					class="chip"
					class:on
					aria-pressed={on}
					data-exclusion={exclusion}
					onclick={() => toggle(exclusion)}
				>
					{#if on}<Icon name="check" size={14} stroke="#fff" weight={3} />{/if}
					{exclusionLabel(lang, exclusion)}
				</button>
			{/each}
		</div>
	</fieldset>

	<div class="notices">
		{#each notices as notice (notice.text)}
			<p class="notice">
				<Icon name={notice.icon} size={20} stroke="var(--petrol)" weight={2} />
				<span>{notice.text}</span>
			</p>
		{/each}
	</div>

	{#if error}
		<p class="form-error" role="alert">
			<Icon name="alert" size={18} stroke="var(--red)" />
			{t(lang, error === 'limit' ? 'limitReached' : 'setupFailed')}
		</p>
	{/if}

	<div class="grow"></div>
	<button type="submit" class="btn-main" disabled={busy}>
		{busy ? busyLabel : submitLabel}
	</button>
</form>

<style>
	.body {
		padding: 18px 20px 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		flex-grow: 1;
	}
	.card {
		background: #fff;
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin: 0;
		min-width: 0;
	}
	fieldset.card {
		display: block;
	}
	.label {
		font-weight: 700;
		font-size: 15px;
		padding: 0;
	}
	legend.label {
		float: left;
		width: 100%;
		margin-bottom: 10px;
	}
	.number-row {
		display: flex;
		gap: 8px;
	}
	.cc {
		position: relative;
		display: flex;
		align-items: center;
	}
	.cc select {
		appearance: none;
		height: 50px;
		padding: 0 30px 0 12px;
		border: 1px solid var(--border-strong);
		border-radius: 6px;
		background: #fff;
		font: inherit;
		font-size: 17px;
		font-weight: 600;
		color: var(--ink);
	}
	.cc :global(svg) {
		position: absolute;
		right: 10px;
		pointer-events: none;
	}
	input {
		flex-grow: 1;
		min-width: 0;
		height: 50px;
		padding: 0 14px;
		border: 2px solid var(--petrol);
		border-radius: 6px;
		font: inherit;
		font-size: 19px;
		color: var(--ink);
		background: #fff;
	}
	input[aria-invalid='true'] {
		border-color: var(--red);
	}
	.hint {
		font-size: 14px;
		color: var(--muted);
	}
	.field-error {
		display: flex;
		gap: 6px;
		align-items: flex-start;
		font-size: 14px;
		color: var(--red);
		font-weight: 600;
	}
	.chips {
		clear: both;
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.chip {
		height: 38px;
		padding: 0 13px;
		border-radius: 19px;
		border: 1px solid var(--border-strong);
		background: #fff;
		color: var(--ink);
		font-size: 15px;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: 6px;
		cursor: pointer;
	}
	.chip.on {
		background: var(--petrol);
		border-color: var(--petrol);
		color: #fff;
	}
	.notices {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.notice {
		margin: 0;
		display: flex;
		gap: 10px;
		align-items: flex-start;
		font-size: 14px;
		line-height: 1.4;
		color: var(--muted-2);
	}
	.notice :global(svg) {
		flex-shrink: 0;
	}
	.form-error {
		margin: 0;
		display: flex;
		gap: 8px;
		align-items: flex-start;
		background: #fdecea;
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 15px;
		font-weight: 600;
		color: var(--red);
	}
	.form-error :global(svg) {
		flex-shrink: 0;
	}
	.grow {
		flex-grow: 1;
	}
	.btn-main {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 56px;
		border: 0;
		border-radius: 8px;
		background: var(--lime);
		color: var(--ink);
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 21px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		width: 100%;
		cursor: pointer;
		flex-shrink: 0;
	}
	.btn-main:disabled {
		opacity: 0.7;
		cursor: wait;
	}
</style>
