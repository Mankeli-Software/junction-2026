<script lang="ts">
	/**
	 * Call ended (design 13, docs/specs/call-screen.md §2.4 and §3): the notification
	 * that opens the message in the demo phone, "Nothing is ordered yet" in three
	 * steps, the SMS line only when an SMS was sent (or failed), and Call again.
	 */
	import Icon from '../Icon.svelte';
	import Notification from './Notification.svelte';
	import { duration, money, t } from '../../i18n';
	import type { InboxMessage, Lang } from '../../types';
	import type { VoiceCall } from '#lib/voice/call.svelte.js';

	let {
		lang,
		call,
		companyName,
		phoneMasked,
		message,
		onopen,
		oncallagain,
		oncontacts
	}: {
		lang: Lang;
		call: VoiceCall;
		companyName: string;
		phoneMasked: string;
		/** The confirmation message that arrived for this call, if any. */
		message: InboxMessage | null;
		onopen: () => void;
		oncallagain: () => void;
		oncontacts: () => void;
	} = $props();

	const ended = $derived(call.ended);
	const length = $derived(duration(ended?.duration_s ?? call.elapsed(Date.now())));
	const expectQuote = $derived(message !== null || ended?.inbox === true);
	const title = $derived(
		ended?.total_cents != null ? t(lang, 'notifTitle', { total: money(ended.total_cents) }) : t(lang, 'notifTitlePlain')
	);
</script>

<div class="screen" data-testid="call-ended">
	<div class="status">
		<button type="button" class="back" onclick={oncontacts}>
			<Icon name="chevron-left" size={16} stroke="var(--petrol)" weight={2.5} />{t(lang, 'contacts')}
		</button>
		<span>{companyName}</span>
	</div>

	{#if message}
		<div class="banner">
			<Notification {lang} {title} {onopen} />
		</div>
	{/if}

	<div class="who">
		<div class="av">S</div>
		<h1 class="hd">S.I.MO</h1>
		<span class="length" data-testid="ended-text">
			{call.dropped ? t(lang, 'callDropped', { time: length }) : t(lang, 'callEnded', { time: length })}
		</span>
	</div>

	{#if expectQuote}
		<div class="steps">
			<h2 class="hd">{t(lang, 'nothingOrderedYet')}</h2>
			<div class="step"><span class="num">1</span>{t(lang, 'endStep1')}</div>
			<div class="step"><span class="num">2</span>{t(lang, 'endStep2')}</div>
			<div class="step"><span class="num">3</span>{t(lang, 'endStep3')}</div>
		</div>
		{#if !message}
			<p class="line" aria-live="polite">{t(lang, 'waitingForLink')}</p>
		{/if}
	{:else}
		<p class="no-order" data-testid="no-order">{t(lang, 'noOrder')}</p>
	{/if}

	{#if ended?.sms_status === 'sent'}
		<p class="line" data-testid="sms-line">
			<Icon name="chat" size={18} stroke="var(--muted)" weight={2} />{t(lang, 'smsSent', { number: phoneMasked })}
		</p>
	{:else if ended?.sms_status === 'failed'}
		<p class="line warn" data-testid="sms-line">
			<Icon name="alert" size={18} stroke="var(--red)" weight={2} />{t(lang, 'smsFailed')}
		</p>
	{/if}

	<div class="grow"></div>
	<div class="again">
		<button type="button" class="call" aria-label={t(lang, 'callAgainAria')} onclick={oncallagain}>
			<Icon name="phone" size={28} stroke="#fff" />
		</button>
		<span aria-hidden="true">{t(lang, 'callAgain')}</span>
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
		justify-content: space-between;
		align-items: center;
		font-size: 13px;
		color: var(--faint);
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
	.banner {
		padding: 12px 12px 0;
		flex-shrink: 0;
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
	.length {
		font-size: 16px;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.steps {
		margin: 26px 20px 0;
		background: var(--page);
		border-radius: 12px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.steps h2 {
		font-size: 22px;
	}
	.step {
		display: flex;
		gap: 12px;
		align-items: center;
		font-size: 16px;
	}
	.num {
		width: 30px;
		height: 30px;
		flex-shrink: 0;
		border-radius: 15px;
		background: var(--petrol);
		color: #fff;
		font-weight: 700;
		font-size: 15px;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.no-order {
		margin: 26px 20px 0;
		background: var(--page);
		border-radius: 12px;
		padding: 18px;
		font-size: 16px;
		text-align: center;
	}
	.line {
		margin: 14px 20px 0;
		display: flex;
		gap: 10px;
		align-items: center;
		font-size: 14px;
		color: var(--muted);
	}
	.line :global(svg) {
		flex-shrink: 0;
	}
	.line.warn {
		color: var(--red);
		font-weight: 600;
	}
	.grow {
		flex-grow: 1;
		min-height: 24px;
	}
	.again {
		padding: 0 0 34px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		font-size: 14px;
		color: var(--muted);
	}
	.call {
		width: 68px;
		height: 68px;
		border-radius: 34px;
		border: 0;
		background: #1f8a3b;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.call:hover {
		background: #1a7733;
	}
</style>
