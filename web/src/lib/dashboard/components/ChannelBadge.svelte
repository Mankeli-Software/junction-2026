<script lang="ts">
	import { channelBadge } from '../states';
	import type { Channel } from '../types';
	import { useUi } from '../ui.svelte';

	let { channel, client }: { channel: Channel; client: string } = $props();
	const ui = useUi();
</script>

<span class="ch ch-{channel}" title={channelBadge(channel, client, ui.lang)}>{channelBadge(channel, client, ui.lang)}</span>

<style>
	.ch {
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.5px;
		text-transform: uppercase;
		border-radius: 4px;
		padding: 4px 8px;
		white-space: nowrap;
		/* A long client name ("MCP Inspector connector") shrinks with an ellipsis instead of
		   pushing out of the card; the full name is in the title. */
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>
