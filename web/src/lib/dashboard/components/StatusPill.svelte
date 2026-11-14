<script lang="ts">
	import { isActive, statusText, stateTone } from '../states';
	import type { Channel, SessionState } from '../types';
	import { useUi } from '../ui.svelte';

	interface Props {
		state: SessionState;
		since: string;
		channel: Channel;
		big?: boolean;
	}

	let { state, since, channel, big = false }: Props = $props();
	const ui = useUi();
</script>

<span class="st tone-{stateTone(state)}" class:big>
	{#if isActive(state)}<span class="dot"></span>{/if}
	{statusText({ state, state_since: since, channel }, ui.lang, ui.now)}
</span>

<style>
	.st {
		align-self: flex-start;
		font-size: 14px;
		font-weight: 700;
		padding: 4px 10px;
		border-radius: 12px;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
		/* Next to a long channel badge on a card, the badge shrinks, not the status. */
		flex-shrink: 0;
	}
	.st.big {
		font-size: 15px;
		padding: 5px 12px;
		border-radius: 14px;
	}
	.dot {
		width: 8px;
		height: 8px;
		border-radius: 4px;
		background: currentColor;
	}
</style>
