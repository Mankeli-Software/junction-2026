<script lang="ts">
	/** One A2UI surface, rendered from its `root` component with our catalog. */
	import { chatContext } from './context';
	import { t } from './i18n';
	import Node from './Node.svelte';
	import { LAYOUT_COMPONENTS } from './protocol';

	let { surfaceId }: { surfaceId: string } = $props();
	const { store, lang, domainCards } = chatContext();
	const surface = $derived(store.surfaces[surfaceId]);
	/** With domain cards off (the confirmation page), a card surface is left out entirely. */
	const hidden = $derived(
		domainCards === false && Boolean(surface?.components.root) && !LAYOUT_COMPONENTS.includes(surface.components.root.component)
	);
</script>

{#if surface && !hidden}
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
