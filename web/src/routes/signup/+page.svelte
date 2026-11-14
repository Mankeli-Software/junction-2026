<script lang="ts">
	/**
	 * Connector sign-up (#48): email, password and the phone number the order links go to.
	 * Open to anyone with the URL; nothing is verified. Then `next`, or the phone page with
	 * the inbox.
	 */
	import { page } from '$app/state';
	import { AuthError, signup } from '#lib/auth/api.js';
	import AuthScreen from '#lib/auth/components/AuthScreen.svelte';
	import PhoneField from '#lib/auth/components/PhoneField.svelte';
	import { at } from '#lib/auth/i18n.js';
	import { DEFAULT_NEXT, safeNext, withNext } from '#lib/auth/next.js';
	import Icon from '#lib/demo/components/Icon.svelte';
	import { langParam } from '#lib/demo/i18n.js';
	import { toE164 } from '#lib/demo/phone.js';

	const MIN_PASSWORD = 10;
	const lang = $derived(langParam(page.url.searchParams.get('lang')));
	const next = $derived(safeNext(page.url.searchParams.get('next')));

	let email = $state('');
	let password = $state('');
	let countryCode = $state('+358');
	let number = $state('');
	let emailInvalid = $state(false);
	let passwordShort = $state(false);
	let phoneInvalid = $state(false);
	let busy = $state(false);
	let error = $state<'emailTaken' | 'failed' | null>(null);

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		const e164 = toE164(countryCode, number);
		emailInvalid = !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
		passwordShort = password.length < MIN_PASSWORD;
		phoneInvalid = e164 === null;
		if (emailInvalid || passwordShort || !e164) return;
		busy = true;
		error = null;
		try {
			await signup(email.trim(), password, e164);
			window.location.assign(next ?? DEFAULT_NEXT);
		} catch (failure) {
			const status = failure instanceof AuthError ? failure.status : 0;
			error = status === 409 ? 'emailTaken' : 'failed';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>S.I.MO | {at(lang, 'signupTitle')}</title></svelte:head>

<AuthScreen {lang} title={at(lang, 'signupTitle')} text={at(lang, 'signupText')}>
	<form class="form" onsubmit={submit} novalidate>
		<div class="card">
			<label for="email" class="label">{at(lang, 'email')}</label>
			<input
				id="email"
				class="text-input"
				type="email"
				autocomplete="username"
				bind:value={email}
				oninput={() => (emailInvalid = false)}
				aria-invalid={emailInvalid}
			/>
			{#if emailInvalid}
				<span class="field-error" role="alert"><Icon name="alert" size={16} stroke="var(--red)" />{at(lang, 'emailInvalid')}</span>
			{/if}
		</div>
		<div class="card">
			<label for="password" class="label">{at(lang, 'password')}</label>
			<input
				id="password"
				class="text-input"
				type="password"
				autocomplete="new-password"
				bind:value={password}
				oninput={() => (passwordShort = false)}
				aria-invalid={passwordShort}
			/>
			{#if passwordShort}
				<span class="field-error" role="alert"><Icon name="alert" size={16} stroke="var(--red)" />{at(lang, 'passwordShort')}</span>
			{:else}
				<span class="hint">{at(lang, 'passwordHint')}</span>
			{/if}
		</div>
		<PhoneField {lang} bind:countryCode bind:number bind:invalid={phoneInvalid} />
		{#if error}
			<p class="form-error" role="alert"><Icon name="alert" size={18} stroke="var(--red)" />{at(lang, error)}</p>
		{/if}
		<button type="submit" class="btn-main" disabled={busy}>
			{busy ? at(lang, 'creating') : at(lang, 'createAccount')}
		</button>
		<p class="switch">
			{at(lang, 'haveAccount')} <a href={withNext('/login', next, lang)}>{at(lang, 'logInLink')}</a>
		</p>
	</form>
</AuthScreen>

<style>
	.form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
</style>
