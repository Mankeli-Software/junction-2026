<script lang="ts">
	/**
	 * Shown after `request_confirmation` (design UI-05, Chat-A4; webshop-chat.md §4.4).
	 * Tells the buyer to open the demo phone in this browser and links to the phone page
	 * (`/phone`, in the shop's language, as the shop's own pointer does; Juho 2026-11-14),
	 * where the inbox has the message. The confirmation link itself (`/c/...`) never
	 * shows here. The masked number shows only when the API says a real SMS went.
	 * Once the buyer confirmed (or cancelled) on the phone, it says so instead, without
	 * the link to the phone; it reads the state again on every panel refresh (`revision`).
	 */
	import { untrack } from 'svelte';
	import '../cards.css';
	import { chatContext } from '../context';
	import { t } from '../i18n';
	import type { SentLatest } from '../types';
	import Icon from './Icon.svelte';

	const { data, lang, revision } = chatContext();
	const L = $derived(lang());
	const phoneHref = $derived(`/phone${L === 'fi' ? '?lang=fi' : ''}`);
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

	const status = $derived(sent?.status ?? 'waiting');

	/** Only a masked number (stars) is ever shown. */
	const sms = $derived(
		sent?.delivery_status === 'sent' && sent.sent_to_masked && sent.sent_to_masked.includes('*') ? sent.sent_to_masked : null
	);
</script>

<div class="sent" data-testid="sent-notice" data-status={status} role="status">
	<span class="badge"><Icon name="phone" size={20} stroke="var(--ink)" /></span>
	<div class="words">
		{#if status === 'confirmed'}
			<b>{t(L, 'sentConfirmedTitle')}</b>
			{#if sent?.order_number}
				<span class="a2-cap" data-testid="sent-order">{t(L, 'sentConfirmedOrder', { number: sent.order_number })}</span>
			{/if}
		{:else if status === 'cancelled'}
			<b>{t(L, 'sentCancelledTitle')}</b>
			<span class="a2-cap">{t(L, 'sentCancelledText')}</span>
		{:else}
			<b>{t(L, 'sentTitle')}</b>
			<span class="a2-cap">{t(L, 'sentText')}</span>
			{#if sms}<span class="a2-cap" data-testid="sent-sms">{t(L, 'alsoSms', { number: sms })}</span>{/if}
			<a class="a2-pill lime open" href={phoneHref} data-testid="open-phone"
				><Icon name="phone" size={16} stroke="var(--ink)" />{t(L, 'openPhone')}</a
			>
		{/if}
	</div>
</div>

<style>
	.sent {
		display: flex;
		align-items: flex-start;
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
	.open {
		align-self: flex-start;
		margin-top: 8px;
		text-decoration: none;
	}
	.words b {
		font-size: 16px;
	}
</style>
