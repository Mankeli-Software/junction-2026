<script lang="ts">
	/**
	 * The demo phone's inbox (technical-plan.md §9.2): the messages with the link to
	 * the confirmation page. Shown on the phone page only, never in the shop. The
	 * link is the authorisation, so the inbox is private to this browser's user.
	 */
	import TabBar from './TabBar.svelte';
	import { t } from '../../i18n';
	import type { InboxMessage, Lang } from '../../types';

	let {
		lang,
		origin,
		messages,
		highlight = null,
		oncontacts
	}: {
		lang: Lang;
		origin: string;
		messages: InboxMessage[];
		highlight?: string | null;
		oncontacts: () => void;
	} = $props();

	const newestFirst = $derived([...messages].reverse());

	function when(iso: string): string {
		return new Intl.DateTimeFormat(lang === 'fi' ? 'fi-FI' : 'en-GB', {
			hour: '2-digit',
			minute: '2-digit',
			timeZone: 'Europe/Helsinki'
		}).format(new Date(iso));
	}
</script>

<div class="screen" data-testid="messages">
	<div class="status"><span></span></div>
	<div class="head">
		<h1 class="hd">{t(lang, 'messages')}</h1>
	</div>

	<div class="scroll">
		{#if messages.length === 0}
			<p class="empty">{t(lang, 'noMessages')}</p>
		{:else}
			<div class="thread-head">
				<span class="av">S</span>
				<b>S.I.MO</b>
			</div>
			<ul class="thread">
				{#each newestFirst as message (message.id)}
					<li class="msg" class:highlight={message.id === highlight} data-testid="inbox-message">
						<time datetime={message.at}>{when(message.at)}</time>
						<div class="bubble">
							<p>{message.text}</p>
							<a href={message.link} data-sveltekit-reload>{new URL(message.link, origin).href}</a>
						</div>
					</li>
				{/each}
			</ul>
		{/if}
		<p class="note">{t(lang, 'messagesNote')}</p>
	</div>

	<TabBar {lang} active="messages" unread={0} onmessages={() => {}} {oncontacts} />
</div>

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
		background: #fff;
	}
	.status {
		padding: 18px 20px 6px;
		flex-shrink: 0;
	}
	.head {
		padding: 0 20px 8px;
		border-bottom: 1px solid var(--divider);
		flex-shrink: 0;
	}
	h1 {
		font-size: 40px;
	}
	.scroll {
		flex-grow: 1;
		overflow-y: auto;
		padding: 16px 16px 12px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.empty {
		margin: 24px 4px 0;
		color: var(--muted);
		font-size: 16px;
		line-height: 1.4;
		text-align: center;
	}
	.thread-head {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		font-size: 15px;
	}
	.av {
		width: 52px;
		height: 52px;
		border-radius: 26px;
		background: var(--petrol);
		color: #fff;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 28px;
	}
	.thread {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.msg {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	time {
		align-self: center;
		font-size: 12px;
		color: var(--faint);
	}
	.bubble {
		align-self: flex-start;
		max-width: 300px;
		background: #e9eef2;
		border-radius: 4px 16px 16px 16px;
		padding: 10px 13px;
		font-size: 16px;
		line-height: 1.4;
	}
	.highlight .bubble {
		box-shadow: 0 0 0 2px var(--lime);
	}
	.bubble p {
		margin: 0 0 6px;
	}
	.bubble a {
		font-weight: 600;
		overflow-wrap: anywhere;
	}
	.note {
		margin: auto 0 0;
		font-size: 13px;
		color: var(--faint);
		text-align: center;
	}
</style>
