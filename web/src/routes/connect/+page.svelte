<script lang="ts">
	/**
	 * The connector consent step (#48): "Allow <client> to order for <company>?"
	 *
	 * `/oauth/authorize` (FastAPI) sends the browser here with `?request=<id>`. Not logged
	 * in: on to `/login?next=<this page>`, which comes back. A hand-out account without a
	 * number gets the phone step here. Allow or Cancel sends the browser back to the
	 * assistant (the client's redirect URI) with a code or an error.
	 */
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { AuthError, decideConnectRequest, getConnectRequest, type ConnectRequest } from '#lib/auth/api.js';
	import AuthScreen from '#lib/auth/components/AuthScreen.svelte';
	import PhoneStep from '#lib/auth/components/PhoneStep.svelte';
	import { at } from '#lib/auth/i18n.js';
	import { withNext } from '#lib/auth/next.js';
	import Icon from '#lib/demo/components/Icon.svelte';
	import { langParam } from '#lib/demo/i18n.js';

	const lang = $derived(langParam(page.url.searchParams.get('lang')));
	const requestId = $derived(page.url.searchParams.get('request') ?? '');

	let view = $state<'loading' | 'phone' | 'ask' | 'gone' | 'failed'>('loading');
	let request = $state<ConnectRequest | null>(null);
	let busy = $state(false);

	async function load() {
		view = 'loading';
		try {
			request = await getConnectRequest(requestId);
			view = 'ask';
		} catch (error) {
			const status = error instanceof AuthError ? error.status : 0;
			if (status === 401) {
				window.location.replace(withNext('/login', page.url.pathname + page.url.search, lang));
				return;
			}
			view = status === 409 ? 'phone' : status === 404 ? 'gone' : 'failed';
		}
	}

	async function decide(allow: boolean) {
		busy = true;
		try {
			const { redirect_to } = await decideConnectRequest(requestId, allow);
			window.location.assign(redirect_to);
		} catch (error) {
			view = error instanceof AuthError && error.status === 404 ? 'gone' : 'failed';
			busy = false;
		}
	}

	onMount(() => {
		if (requestId) void load();
		else view = 'gone';
	});
</script>

<svelte:head><title>S.I.MO | {at(lang, 'connectTitle')}</title></svelte:head>

<AuthScreen {lang} title={at(lang, 'connectTitle')} text={at(lang, 'signupText')}>
	{#if view === 'loading'}
		<p class="status" aria-live="polite">{at(lang, 'connectLoading')}</p>
	{:else if view === 'phone'}
		<PhoneStep {lang} ondone={load} />
	{:else if view === 'ask' && request}
		<div class="card ask" data-testid="consent">
			<h2 class="hd">
				{at(lang, 'connectQuestion', { client: request.client_name, company: request.company_name })}
			</h2>
			<p>{at(lang, 'connectText', { client: request.client_name, phone: request.phone_masked })}</p>
			<p class="host">{at(lang, 'connectRedirect', { host: request.redirect_host })}</p>
		</div>
		<button type="button" class="btn-main" disabled={busy} onclick={() => decide(true)}>{at(lang, 'allow')}</button>
		<button type="button" class="btn-plain" disabled={busy} onclick={() => decide(false)}>{at(lang, 'cancel')}</button>
	{:else}
		<p class="form-error" role="alert">
			<Icon name="alert" size={18} stroke="var(--red)" />{at(lang, view === 'gone' ? 'connectGone' : 'failed')}
		</p>
	{/if}
</AuthScreen>

<style>
	.status {
		margin: 0;
		color: var(--muted-2);
	}
	.ask h2 {
		margin: 0;
		font-size: 26px;
		line-height: 1.1;
		color: var(--petrol);
	}
	.ask p {
		margin: 0;
		font-size: 15px;
		line-height: 1.4;
		color: var(--muted-2);
	}
	.ask .host {
		font-size: 14px;
		color: var(--muted);
	}
</style>
