<script lang="ts">
	/** One A2UI surface, rendered from its `root` component with our catalog. */
	import { chatContext } from './context';
	import { t } from './i18n';
	import Node from './Node.svelte';

	let { surfaceId }: { surfaceId: string } = $props();
	const { store, lang } = chatContext();
	const surface = $derived(store.surfaces[surfaceId]);
</script>

{#if surface}
	<div class="surface" data-testid="a2ui-surface" data-surface-id={surfaceId}>
		{#if !surface.supported}
			<p class="unsupported">{t(lang(), 'unsupported')}</p>
		{:else if surface.components.root}
			<Node {surface} id="root" depth={0} />
		{/if}
	</div>
{/if}

<style>
	.surface {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.unsupported {
		margin: 0;
		font-size: 14px;
		color: var(--muted);
	}
</style>
