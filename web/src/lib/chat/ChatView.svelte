<script lang="ts">
	/**
	 * The chat itself (#57, design UI-02 and Chat-A1): the message list with S.I.MO's
	 * text, its A2UI surfaces and the "working" line, and the input with the camera
	 * button. Used by the webshop panel and the confirmation page's "Ask for changes".
	 * Every text is rendered as text (Svelte escaping, never {@html}) and never as a link.
	 * Needs `setChatContext` above it (the panel sets it).
	 */
	import { tick, type Snippet } from 'svelte';
	import Surface from '#lib/a2ui/Surface.svelte';
	import type { Lang } from '#lib/demo/types.js';
	import { t } from './i18n';
	import { withoutLinks, workingKey } from './messages';
	import type { ChatSession } from './session.svelte';

	let {
		session,
		lang,
		photos = false,
		empty,
		inputId = 'chat-input',
		input = $bindable(null)
	}: {
		session: ChatSession;
		lang: Lang;
		/** The camera button, the photo hint and the upload. */
		photos?: boolean;
		/** Shown before the first message: gets `ask(text)` and `pickPhoto()`. */
		empty?: Snippet<[(text: string) => void, () => void]>;
		inputId?: string;
		/** The text field, for the panel to move focus into. */
		input?: HTMLInputElement | null;
	} = $props();

	let text = $state('');
	let list = $state<HTMLElement | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);
	/** The photo hint shows until the first photo has been read (UI-02: "once"). */
	let photoHintDone = $state(false);

	const lastText = $derived(session.messages.at(-1)?.kind === 'agent' ? (session.messages.at(-1) as { text: string }).text : '');

	// Keep the newest message in view as the stream grows.
	$effect(() => {
		void session.messages.length;
		void lastText;
		void session.working;
		void tick().then(() => list?.scrollTo({ top: list.scrollHeight }));
	});

	function submit(event: SubmitEvent) {
		event.preventDefault();
		const message = text.trim();
		if (!message || session.busy) return;
		text = '';
		void session.send(message);
	}

	function ask(prompt: string) {
		if (session.busy) return;
		void session.send(prompt);
	}

	async function pickPhoto(event: Event) {
		const target = event.currentTarget as HTMLInputElement;
		const file = target.files?.[0];
		target.value = '';
		if (!file || session.busy) return;
		const words = text;
		text = '';
		await session.sendPhoto(file, words);
		photoHintDone = true;
	}
</script>

<div class="chat">
	<div class="list" bind:this={list} data-testid="chat-messages" aria-live="polite" aria-relevant="additions">
		{#if !session.started && empty}
			{@render empty(ask, () => fileInput?.click())}
		{/if}
		{#each session.messages as message (message.id)}
			{#if message.kind === 'buyer'}
				<p class="me" data-testid="chat-buyer"><span class="sr">{t(lang, 'you')}: </span>{message.text}</p>
			{:else if message.kind === 'action'}
				<p class="me echo" data-testid="chat-action"><span class="sr">{t(lang, 'you')}: </span>{message.text}</p>
			{:else if message.kind === 'photo'}
				<div class="photo" data-testid="chat-photo">
					<img src={message.url} alt={t(lang, 'photoAlt')} />
					{#if message.text}<p class="me">{message.text}</p>{/if}
				</div>
			{:else if message.kind === 'agent'}
				<p class="bot" data-testid="chat-agent"><span class="sr">S.I.MO: </span>{withoutLinks(lang, message.text)}</p>
			{:else if message.kind === 'surface'}
				<div class="surface"><Surface surfaceId={message.surfaceId} /></div>
			{:else if message.kind === 'error'}
				<p class="bot error" role="alert" data-testid="chat-error">{t(lang, message.key)}</p>
			{/if}
		{/each}
		{#if session.working}
			<p class="bot working" data-testid="chat-working">
				<svg width="34" height="10" viewBox="0 0 34 10" aria-hidden="true">
					<circle cx="5" cy="5" r="4" /><circle cx="17" cy="5" r="4" opacity="0.55" /><circle cx="29" cy="5" r="4" opacity="0.25" />
				</svg>
				<span>{t(lang, workingKey(session.working))}</span>
			</p>
		{/if}
	</div>

	{#if photos && !photoHintDone}
		<p class="hint" data-testid="photo-hint">
			<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
				<circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" />
			</svg>
			{t(lang, 'photoHint')}
		</p>
	{/if}
	<form class="bar" onsubmit={submit}>
		{#if photos}
			<button
				type="button"
				class="round camera"
				aria-label={t(lang, 'addPhoto')}
				disabled={session.busy}
				onclick={() => fileInput?.click()}
			>
				<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
					<path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
				</svg>
			</button>
			<input
				bind:this={fileInput}
				class="file"
				type="file"
				accept="image/*"
				capture="environment"
				tabindex="-1"
				aria-hidden="true"
				data-testid="photo-input"
				onchange={pickPhoto}
			/>
		{/if}
		<label for={inputId} class="sr">{t(lang, 'messageLabel')}</label>
		<input
			id={inputId}
			bind:this={input}
			bind:value={text}
			class="text"
			type="text"
			autocomplete="off"
			maxlength="2000"
			placeholder={t(lang, 'placeholder')}
		/>
		<button type="submit" class="round send" aria-label={t(lang, 'send')} disabled={session.busy || !text.trim()}>
			<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
				<path d="M4 12l16-8-6 16-2-6z" />
			</svg>
		</button>
	</form>
</div>

<style>
	.chat {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		background: var(--card);
	}
	.list {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		padding: 14px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.list > :global(:first-child) {
		margin-top: auto;
	}
	.sr {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
	.me,
	.bot {
		margin: 0;
		padding: 10px 13px;
		font-size: 15px;
		line-height: 1.4;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}
	.me {
		align-self: flex-end;
		max-width: min(270px, 85%);
		background: var(--petrol);
		color: #fff;
		border-radius: 14px 4px 14px 14px;
	}
	.me.echo {
		background: var(--card);
		color: var(--petrol);
		border: 2px solid var(--petrol);
	}
	.bot {
		align-self: flex-start;
		max-width: min(290px, 90%);
		background: var(--page);
		color: var(--ink);
		border-radius: 4px 14px 14px 14px;
	}
	.bot.error {
		border: 1px solid #e8b3ad;
		background: #fdf1ef;
	}
	.working {
		display: flex;
		gap: 10px;
		align-items: center;
	}
	.working svg {
		flex-shrink: 0;
		fill: var(--petrol);
	}
	.photo {
		align-self: flex-end;
		width: min(200px, 65%);
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.photo img {
		display: block;
		width: 100%;
		max-height: 160px;
		object-fit: cover;
		border-radius: 14px 4px 14px 14px;
		border: 1px solid #e6dfc9;
		background: #fbf7ec;
	}
	.photo .me {
		align-self: stretch;
		max-width: none;
	}
	.surface {
		align-self: stretch;
		min-width: 0;
	}
	.surface:empty {
		display: none;
	}
	.hint {
		margin: 0;
		padding: 8px 14px 0;
		display: flex;
		gap: 8px;
		align-items: center;
		font-size: 13px;
		color: var(--muted);
	}
	.hint svg {
		flex-shrink: 0;
	}
	.bar {
		padding: 10px 14px 18px;
		display: flex;
		gap: 8px;
		flex-shrink: 0;
	}
	.round {
		width: 46px;
		height: 46px;
		flex-shrink: 0;
		border-radius: 23px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.round:disabled {
		cursor: default;
		opacity: 0.5;
	}
	.camera {
		border: 2px solid var(--petrol);
		background: var(--card);
		color: var(--petrol);
	}
	.send {
		border: 0;
		background: var(--petrol);
		color: #fff;
	}
	.file {
		display: none;
	}
	.text {
		flex-grow: 1;
		min-width: 0;
		height: 46px;
		box-sizing: border-box;
		border: 1px solid var(--border-strong);
		border-radius: 23px;
		padding: 0 16px;
		font: inherit;
		font-size: 15px;
		color: var(--ink);
		background: var(--card);
	}
	.text:focus-visible {
		outline: none;
		border: 2px solid var(--petrol);
		padding: 0 15px;
	}
</style>
