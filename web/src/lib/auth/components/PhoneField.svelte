<script lang="ts">
	/** The phone number card: country code and number, as on the call setup screen (design 10). */
	import Icon from '../../demo/components/Icon.svelte';
	import { COUNTRY_CODES } from '../../demo/phone';
	import type { Lang } from '../../demo/types';
	import { at } from '../i18n';

	let {
		lang,
		countryCode = $bindable('+358'),
		number = $bindable(''),
		invalid = $bindable(false)
	}: { lang: Lang; countryCode?: string; number?: string; invalid?: boolean } = $props();
</script>

<div class="card">
	<label for="phone" class="label">{at(lang, 'phoneLabel')}</label>
	<div class="number-row">
		<div class="cc">
			<select aria-label={at(lang, 'countryCode')} bind:value={countryCode}>
				{#each COUNTRY_CODES as code (code)}
					<option value={code}>{code}</option>
				{/each}
			</select>
			<Icon name="chevron-down" size={14} stroke="var(--petrol)" weight={2.5} />
		</div>
		<input
			id="phone"
			class="text-input"
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
			<Icon name="alert" size={16} stroke="var(--red)" />{at(lang, 'phoneInvalid')}
		</span>
	{:else}
		<span id="phone-hint" class="hint">{at(lang, 'phoneHint')}</span>
	{/if}
</div>

<style>
	.number-row {
		display: flex;
		gap: 8px;
	}
	.number-row input {
		flex-grow: 1;
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
</style>
