<script lang="ts">
	/**
	 * First login of a hand-out account (#48): ask for the number once
	 * (`POST /api/v1/me/phone`), then carry on.
	 */
	import Icon from '../../demo/components/Icon.svelte';
	import { toE164 } from '../../demo/phone';
	import type { Lang } from '../../demo/types';
	import { AuthError, setPhone } from '../api';
	import { at } from '../i18n';
	import PhoneField from './PhoneField.svelte';

	let { lang, ondone }: { lang: Lang; ondone: () => void } = $props();

	let countryCode = $state('+358');
	let number = $state('');
	let invalid = $state(false);
	let busy = $state(false);
	let failed = $state(false);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		const e164 = toE164(countryCode, number);
		invalid = e164 === null;
		if (!e164) return;
		busy = true;
		failed = false;
		try {
			await setPhone(e164);
			ondone();
		} catch (error) {
			// 409: the number was set meanwhile (another tab), so just carry on.
			if (error instanceof AuthError && error.status === 409) ondone();
			else if (error instanceof AuthError && error.status === 422) invalid = true;
			else failed = true;
		} finally {
			busy = false;
		}
	}
</script>

<form class="step" onsubmit={submit} novalidate data-testid="phone-step">
	<div>
		<h2 class="hd">{at(lang, 'phoneStepTitle')}</h2>
		<p>{at(lang, 'phoneStepText')}</p>
	</div>
	<PhoneField {lang} bind:countryCode bind:number bind:invalid />
	{#if failed}
		<p class="form-error" role="alert"><Icon name="alert" size={18} stroke="var(--red)" />{at(lang, 'failed')}</p>
	{/if}
	<button type="submit" class="btn-main" disabled={busy}>
		{busy ? at(lang, 'saving') : at(lang, 'phoneStepSave')}
	</button>
</form>

<style>
	.step {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	h2 {
		margin: 0 0 4px;
		font-size: 26px;
		color: var(--petrol);
	}
	p {
		margin: 0;
		font-size: 15px;
		line-height: 1.4;
		color: var(--muted-2);
	}
</style>
