<script lang="ts">
	/**
	 * In call with S.I.MO (design 12, docs/specs/call-screen.md §2.3): timer, speaking
	 * indicator, live captions for both sides marked as automatic, Mute, Speaker,
	 * Captions and the red hang-up button. The phone is on speaker, not at the ear.
	 */
	import { tick } from 'svelte';
	import Icon from '../Icon.svelte';
	import { duration, t } from '../../i18n';
	import type { Lang } from '../../types';
	import type { VoiceCall } from '#lib/voice/call.svelte.js';

	let { lang, call, now }: { lang: Lang; call: VoiceCall; now: number } = $props();

	let showCaptions = $state(true);
	let list: HTMLDivElement | undefined = $state();

	const live = $derived(call.phase === 'live');
	const indicator = $derived(!live ? 'connecting' : call.agentSpeaking ? 'speaking' : 'listening');

	// Keep the newest caption in view as captions arrive and grow.
	$effect(() => {
		const last = call.captions.at(-1);
		void call.captions.length;
		void last?.text;
		void last?.pending;
		if (!list || !showCaptions) return;
		void tick().then(() => list?.scrollTo({ top: list.scrollHeight, behavior: 'smooth' }));
	});
</script>

<div class="screen" data-testid="in-call" data-wake-lock={call.wakeLock ? 'held' : 'none'}>
	<div class="status"><span></span><span>{call.speaker ? t(lang, 'onSpeaker') : t(lang, 'speakerOff')}</span></div>
	<div class="head">
		<div class="av">S</div>
		<div class="who">
			<h1 class="hd">S.I.MO</h1>
			<span class="timer" data-testid="timer" role="timer">
				{live ? duration(call.elapsed(now)) : t(lang, 'connecting')}
			</span>
		</div>
		<div class="state" data-testid="indicator" data-state={indicator} aria-live="polite">
			{#if indicator === 'speaking'}
				<svg class="bars" width="20" height="14" viewBox="0 0 22 14" aria-hidden="true">
					<rect x="0" y="5" width="3" height="4" rx="1.5" /><rect x="5" y="2" width="3" height="10" rx="1.5" />
					<rect x="10" y="0" width="3" height="14" rx="1.5" /><rect x="15" y="3" width="3" height="8" rx="1.5" />
					<rect x="19" y="5" width="3" height="4" rx="1.5" />
				</svg>
				{t(lang, 'speaking')}
			{:else if indicator === 'listening'}
				<span class="dot" class:talking={call.callerTalking}></span>
				{t(lang, 'listening')}
			{:else}
				<span class="dot pulse"></span>
				{t(lang, 'connecting')}
			{/if}
		</div>
	</div>

	<section class="captions" aria-label={t(lang, 'liveCaptions')}>
		<h2 class="cap-label">{t(lang, 'liveCaptions')}</h2>
		{#if showCaptions}
			<div class="cap-list" bind:this={list} aria-live="polite" data-testid="captions">
				{#each call.captions as caption (caption.id)}
					<div class="cap-row {caption.who}" data-testid="caption-{caption.who}">
						<span class="who-label">{caption.who === 'agent' ? 'S.I.MO' : t(lang, 'you')}</span>
						<div class="bubble" class:open={!caption.final} class:pending={caption.pending}>
							{#if caption.pending}
								{t(lang, 'youListening')}
							{:else}
								{caption.text}{#if !caption.final && caption.who === 'agent'}<span class="cursor">▍</span>{/if}
							{/if}
						</div>
					</div>
				{/each}
			</div>
		{:else}
			<p class="off">{t(lang, 'captionsOff')}</p>
		{/if}
	</section>

	<div class="controls">
		<div class="ctl">
			<button
				type="button"
				class="rnd"
				class:on={call.muted}
				aria-label={t(lang, 'mute')}
				aria-pressed={call.muted}
				disabled={!live}
				onclick={() => call.toggleMute()}
			>
				<Icon name={call.muted ? 'mic-off' : 'mic'} size={24} stroke={call.muted ? '#163F54' : '#fff'} weight={2} />
			</button>
			<span aria-hidden="true">{call.muted ? t(lang, 'muted') : t(lang, 'mute')}</span>
		</div>
		<div class="ctl">
			<button
				type="button"
				class="rnd"
				class:on={call.speaker}
				aria-label={t(lang, 'speaker')}
				aria-pressed={call.speaker}
				onclick={() => call.toggleSpeaker()}
			>
				<Icon name={call.speaker ? 'speaker' : 'speaker-off'} size={24} stroke={call.speaker ? '#163F54' : '#fff'} weight={2} />
			</button>
			<span aria-hidden="true">{t(lang, 'speaker')}</span>
		</div>
		<div class="ctl">
			<button
				type="button"
				class="rnd"
				class:on={showCaptions}
				aria-label={t(lang, 'captions')}
				aria-pressed={showCaptions}
				onclick={() => (showCaptions = !showCaptions)}
			>
				<Icon name="captions" size={24} stroke={showCaptions ? '#163F54' : '#fff'} weight={2} />
			</button>
			<span aria-hidden="true">{t(lang, 'captions')}</span>
		</div>
	</div>
	<div class="hang">
		<button type="button" class="hangup" aria-label={t(lang, 'hangUp')} onclick={() => call.hangup()}>
			<Icon name="hangup" size={32} stroke="#fff" />
		</button>
	</div>
</div>

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
		background: #163f54;
		color: #fff;
	}
	.status {
		padding: 18px 20px 0;
		display: flex;
		justify-content: space-between;
		font-size: 13px;
		color: #8fb2c2;
		flex-shrink: 0;
	}
	.head {
		padding: 14px 20px 12px;
		display: flex;
		align-items: center;
		gap: 14px;
		flex-shrink: 0;
	}
	.av {
		width: 60px;
		height: 60px;
		border-radius: 30px;
		background: #2a6582;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 32px;
		flex-shrink: 0;
	}
	.who {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex-grow: 1;
		min-width: 0;
	}
	h1 {
		font-size: 32px;
		color: #fff;
	}
	.timer {
		font-size: 16px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		color: #cfe0e8;
	}
	.state {
		display: flex;
		align-items: center;
		gap: 6px;
		background: #22556f;
		border-radius: 16px;
		padding: 6px 12px;
		font-size: 13px;
		font-weight: 600;
		flex-shrink: 0;
	}
	.bars rect {
		fill: var(--lime);
		transform-origin: center;
		animation: bar 0.9s ease-in-out infinite;
	}
	.bars rect:nth-child(2) {
		animation-delay: 0.15s;
	}
	.bars rect:nth-child(3) {
		animation-delay: 0.3s;
	}
	.bars rect:nth-child(4) {
		animation-delay: 0.45s;
	}
	@keyframes bar {
		50% {
			transform: scaleY(0.5);
		}
	}
	.dot {
		width: 10px;
		height: 10px;
		border-radius: 5px;
		background: #8fb2c2;
	}
	.dot.talking {
		background: var(--lime);
	}
	.dot.pulse {
		animation: pulse 1s ease-in-out infinite;
	}
	@keyframes pulse {
		50% {
			opacity: 0.3;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.bars rect,
		.dot.pulse {
			animation: none;
		}
	}
	.captions {
		flex-grow: 1;
		min-height: 0;
		margin: 0 12px;
		background: #0f3446;
		border-radius: 16px;
		padding: 14px 12px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.cap-label {
		margin: 0;
		color: #8fb2c2;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		flex-shrink: 0;
	}
	.cap-list {
		flex-grow: 1;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 12px;
		scrollbar-width: thin;
	}
	.cap-list > :first-child {
		margin-top: auto;
	}
	.cap-row {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.cap-row.buyer {
		align-items: flex-end;
	}
	.who-label {
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.8px;
		text-transform: uppercase;
		color: #8fb2c2;
	}
	.bubble {
		max-width: 290px;
		padding: 10px 13px;
		font-size: 17px;
		line-height: 1.35;
		overflow-wrap: anywhere;
	}
	.agent .bubble {
		align-self: flex-start;
		background: #2a6582;
		color: #fff;
		border-radius: 4px 14px 14px 14px;
	}
	.agent .bubble.open {
		background: #22556f;
		color: #dceaf1;
	}
	.buyer .bubble {
		background: #fff;
		color: var(--ink);
		border-radius: 14px 4px 14px 14px;
	}
	.buyer .bubble.pending {
		background: #dceaf1;
		color: var(--muted);
		font-style: italic;
	}
	.cursor {
		color: var(--lime);
	}
	.off {
		margin: auto 0;
		text-align: center;
		color: #8fb2c2;
	}
	.controls {
		padding: 20px 28px 12px;
		display: flex;
		justify-content: space-around;
		flex-shrink: 0;
	}
	.ctl {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		font-size: 13px;
		color: #cfe0e8;
	}
	.rnd {
		width: 60px;
		height: 60px;
		border-radius: 30px;
		border: 0;
		background: #2a6582;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.rnd.on {
		background: #fff;
	}
	.rnd:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.hang {
		padding: 6px 0 30px;
		display: flex;
		justify-content: center;
		flex-shrink: 0;
	}
	.hangup {
		width: 72px;
		height: 72px;
		border-radius: 36px;
		border: 0;
		background: #d9433a;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
	}
	.hangup:hover {
		background: #c23a32;
	}
	@media (max-height: 640px) {
		.controls {
			padding-top: 12px;
		}
		.hang {
			padding-bottom: 16px;
		}
		.rnd {
			width: 52px;
			height: 52px;
		}
		.hangup {
			width: 64px;
			height: 64px;
		}
	}
</style>
