<script lang="ts">
	/**
	 * A call that could not start (docs/specs/call-screen.md §3). Never a dead end:
	 * each case says what happened and what to do.
	 */
	import Icon from '../Icon.svelte';
	import { t } from '../../i18n';
	import type { Lang } from '../../types';
	import type { CallError } from '#lib/voice/call.svelte.js';

	let {
		lang,
		error,
		onretry,
		onsetup,
		oncontacts
	}: {
		lang: Lang;
		error: CallError;
		onretry: () => void;
		onsetup: () => void;
		oncontacts: () => void;
	} = $props();
</script>

<div class="screen" data-testid="call-failed" data-error={error}>
	<div class="status">
		<button type="button" class="back" onclick={oncontacts}>
			<Icon name="chevron-left" size={16} stroke="var(--petrol)" weight={2.5} />{t(lang, 'contacts')}
		</button>
	</div>
	<div class="who">
		<div class="av">S</div>
		<h1 class="hd">S.I.MO</h1>
	</div>
	<div class="box" role="alert">
		<Icon name="alert" size={24} stroke="var(--red)" />
		<div class="text">
			{#if error === 'mic_denied'}
				<b>{t(lang, 'micDenied')}</b>
				<span>{t(lang, 'micDeniedHelp')}</span>
			{:else if error === 'unsupported'}
				<b>{t(lang, 'unsupported')}</b>
			{:else if error === 'limit'}
				<b>{t(lang, 'limitReached')}</b>
			{:else if error === 'no_session'}
				<b>{t(lang, 'sessionLost')}</b>
			{:else}
				<b>{t(lang, 'cannotConnect')}</b>
			{/if}
		</div>
	</div>
	<div class="grow"></div>
	<div class="actions">
		{#if error === 'no_session'}
			<button type="button" class="btn-main" onclick={onsetup}>{t(lang, 'setUpAgain')}</button>
		{:else if error === 'mic_denied' || error === 'cannot_connect'}
			<button type="button" class="btn-main" onclick={onretry}>{t(lang, 'tryAgain')}</button>
		{/if}
	</div>
</div>

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
		background: #fff;
		overflow-y: auto;
	}
	.status {
		padding: 14px 20px 0;
		display: flex;
		flex-shrink: 0;
	}
	.back {
		display: flex;
		align-items: center;
		gap: 2px;
		border: 0;
		background: none;
		padding: 4px 0;
		font-size: 14px;
		font-weight: 600;
		color: var(--petrol);
		cursor: pointer;
	}
	.who {
		padding: 34px 20px 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
	}
	.av {
		width: 84px;
		height: 84px;
		border-radius: 42px;
		background: #e3edf2;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 44px;
		color: var(--petrol);
	}
	h1 {
		font-size: 32px;
	}
	.box {
		margin: 26px 20px 0;
		background: #fdecea;
		border-radius: 12px;
		padding: 18px;
		display: flex;
		gap: 12px;
		align-items: flex-start;
	}
	.box :global(svg) {
		flex-shrink: 0;
	}
	.text {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 16px;
		line-height: 1.4;
	}
	.text span {
		font-size: 15px;
		color: var(--muted-2);
	}
	.grow {
		flex-grow: 1;
	}
	.actions {
		padding: 20px 20px 34px;
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
	}
</style>
