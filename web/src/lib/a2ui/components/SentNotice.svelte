<script lang="ts">
	/**
	 * Shown after `request_confirmation` (design UI-05, Chat-A4; webshop-chat.md §4.4).
	 * Tells the buyer to open the demo phone in this browser. There is deliberately no
	 * link: neither to the confirmation page nor to the phone, so a browser agent has
	 * nothing to follow. The masked number shows only when the API says a real SMS went.
	 */
	import { untrack } from 'svelte';
	import '../cards.css';
	import { chatContext } from '../context';
	import { t } from '../i18n';
	import type { SentLatest } from '../types';
	import Icon from './Icon.svelte';

	const { data, lang, revision } = chatContext();
	const L = $derived(lang());
	let sent = $state.raw<SentLatest | null>(null);

	function load() {
		data.getSentLatest?.().then(
			(value) => (sent = value),
			() => {}
		);
	}

	$effect(() => {
		void revision?.();
		untrack(load);
	});

	/** Only a masked number (stars) is ever shown. */
	const sms = $derived(
		sent?.delivery_status === 'sent' && sent.sent_to_masked && sent.sent_to_masked.includes('*') ? sent.sent_to_masked : null
	);
</script>

<div class="sent" data-testid="sent-notice" role="status">
	<span class="badge"><Icon name="phone" size={20} stroke="var(--ink)" /></span>
	<div class="words">
		<b>{t(L, 'sentTitle')}</b>
		<span class="a2-cap">{t(L, 'sentText')}</span>
		{#if sms}<span class="a2-cap" data-testid="sent-sms">{t(L, 'alsoSms', { number: sms })}</span>{/if}
	</div>
</div>

<style>
	.sent {
		display: flex;
		align-items: center;
		gap: 12px;
		background: var(--ok-bg);
		border: 1px solid var(--ok-border);
		border-radius: 12px;
		padding: 12px 14px;
		color: var(--ink);
	}
	.badge {
		width: 40px;
		height: 40px;
		flex-shrink: 0;
		border-radius: 20px;
		background: var(--lime);
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.words {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.words b {
		font-size: 16px;
	}
</style>
