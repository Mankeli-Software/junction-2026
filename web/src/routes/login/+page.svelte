<script lang="ts">
	/**
	 * Connector login (#48): email and password, then `next` (usually the consent page,
	 * `/connect?request=...`) or the phone page with the inbox. A hand-out account without
	 * a number gets the phone step first.
	 */
	import { page } from '$app/state';
	import { AuthError, login } from '#lib/auth/api.js';
	import AuthScreen from '#lib/auth/components/AuthScreen.svelte';
	import PhoneStep from '#lib/auth/components/PhoneStep.svelte';
	import { at } from '#lib/auth/i18n.js';
	import { DEFAULT_NEXT, safeNext, withNext } from '#lib/auth/next.js';
	import Icon from '#lib/demo/components/Icon.svelte';
	import { langParam } from '#lib/demo/i18n.js';

	const lang = $derived(langParam(page.url.searchParams.get('lang')));
	const next = $derived(safeNext(page.url.searchParams.get('next')));

	let step = $state<'login' | 'phone'>('login');
	let email = $state('');
	let password = $state('');
	let busy = $state(false);
	let error = $state<'wrongLogin' | 'tooMany' | 'failed' | null>(null);

	function go() {
		window.location.assign(next ?? DEFAULT_NEXT);
	}

	async function submit(event: SubmitEvent) {
		event.preventDefault();
		busy = true;
		error = null;
		try {
			const result = await login(email, password);
			if (result.phone_required) step = 'phone';
			else go();
		} catch (failure) {
			const status = failure instanceof AuthError ? failure.status : 0;
			error = status === 401 ? 'wrongLogin' : status === 429 ? 'tooMany' : 'failed';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>S.I.MO | {at(lang, 'loginTitle')}</title></svelte:head>

<AuthScreen {lang} title={at(lang, 'loginTitle')} text={at(lang, 'loginText')}>
	{#if step === 'phone'}
		<PhoneStep {lang} ondone={go} />
	{:else}
		<form class="form" onsubmit={submit}>
			<div class="card">
				<label for="email" class="label">{at(lang, 'email')}</label>
				<input id="email" class="text-input" type="email" autocomplete="username" required bind:value={email} />
			</div>
			<div class="card">
				<label for="password" class="label">{at(lang, 'password')}</label>
				<input
					id="password"
					class="text-input"
					type="password"
					autocomplete="current-password"
					required
					bind:value={password}
				/>
			</div>
			{#if error}
				<p class="form-error" role="alert"><Icon name="alert" size={18} stroke="var(--red)" />{at(lang, error)}</p>
			{/if}
			<button type="submit" class="btn-main" disabled={busy}>
				{busy ? at(lang, 'loggingIn') : at(lang, 'logIn')}
			</button>
			<p class="switch">
				{at(lang, 'noAccount')} <a href={withNext('/signup', next, lang)}>{at(lang, 'signUpLink')}</a>
			</p>
		</form>
	{/if}
</AuthScreen>

<style>
	.form {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
</style>
