<script lang="ts">
	/**
	 * "Ask for changes" on the confirmation page (docs/specs/webshop-chat.md §5): the
	 * same chat as the webshop, collapsible, against
	 * `POST /api/v1/confirmations/{token}/chat`, where S.I.MO can only update the quote.
	 * After a turn that changed the quote, the page reloads its view exactly as after an
	 * edit made with the page controls. Confirm stays the page's button; the chat can't
	 * confirm or cancel.
	 */
	import { onDestroy, tick } from 'svelte';
	import { refreshAll } from '$app/navigation';
	import { apiData } from '#lib/a2ui/api.js';
	import { setChatContext } from '#lib/a2ui/context.js';
	import type { ChatData } from '#lib/a2ui/types.js';
	import { ui } from '#lib/confirmation/forms.svelte.js';
	import type { Lang } from '#lib/demo/types.js';
	import ChatView from './ChatView.svelte';
	import { t } from './i18n';
	import { ChatSession, type TurnResult } from './session.svelte';

	let { token, lang, data = apiData }: { token: string; lang: Lang; data?: ChatData } = $props();

	// svelte-ignore state_referenced_locally
	const session = new ChatSession({
		endpoint: `/api/v1/confirmations/${encodeURIComponent(token)}/chat`,
		photoEndpoint: null,
		lang: () => lang,
		onDone: (result) => void reload(result)
	});
	// The data source is fixed for the panel's life.
	// svelte-ignore state_referenced_locally
	setChatContext({ store: session.store, data, lang: () => lang, revision: () => session.revision });
	onDestroy(() => session.dispose());

	let open = $state(false);
	let input = $state<HTMLInputElement | null>(null);

	/** As `submitWithPending` does after an edit: the "updating" line, then all data again. */
	async function reload(result: TurnResult) {
		if (result.quoteId === null && !result.quoteTouched) return;
		ui.pending = true;
		try {
			await refreshAll();
		} finally {
			ui.pending = false;
		}
	}

	async function toggle() {
		open = !open;
		if (open) {
			await tick();
			input?.focus();
		}
	}
</script>

<section class="ask" data-testid="ask-for-changes">
	<button type="button" class="toggle" aria-expanded={open} aria-controls="ask-chat" onclick={toggle}>
		<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--petrol)" stroke-width="2.2" aria-hidden="true">
			<path d="M4 5h16v11H9l-5 4z" />
		</svg>
		<span class="hd">{t(lang, 'askChanges')}</span>
		<svg class="chev" class:up={open} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--petrol)" stroke-width="2.5" aria-hidden="true">
			<path d="M6 9l6 6 6-6" />
		</svg>
	</button>
	<div id="ask-chat" class="body" hidden={!open}>
		<ChatView {session} {lang} inputId="ask-chat-input" bind:input>
			{#snippet empty()}
				<p class="hint">{t(lang, 'askChangesHint')}</p>
			{/snippet}
		</ChatView>
	</div>
</section>

<style>
	.ask {
		margin: 20px 16px 0;
		border: 1px solid var(--border);
		border-radius: 10px;
		background: var(--card);
		overflow: hidden;
	}
	.toggle {
		width: 100%;
		min-height: 52px;
		padding: 0 14px;
		display: flex;
		align-items: center;
		gap: 10px;
		border: 0;
		background: var(--lavender);
		color: var(--petrol);
		font: inherit;
		text-align: left;
		cursor: pointer;
	}
	.toggle .hd {
		flex-grow: 1;
		font-size: 22px;
	}
	.chev {
		transition: transform 0.15s;
	}
	.chev.up {
		transform: rotate(180deg);
	}
	.body {
		height: 420px;
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--border);
	}
	.body[hidden] {
		display: none;
	}
	.hint {
		margin: 0;
		font-size: 14px;
		line-height: 1.4;
		color: var(--muted-2);
	}
</style>
