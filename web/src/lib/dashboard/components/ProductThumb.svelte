<script lang="ts">
	import Icon from './Icon.svelte';

	/** Product image with a placeholder when it is missing or fails to load (`technical-plan.md` §5.5). */
	let { src, alt }: { src: string | null; alt: string } = $props();
	let failed = $state(false);
</script>

<div class="thumb">
	{#if src && !failed}
		<img {src} {alt} loading="lazy" referrerpolicy="no-referrer" onerror={() => (failed = true)} />
	{:else}
		<Icon name="box" size={28} color="var(--d-faint)" stroke={1.8} />
	{/if}
</div>

<style>
	.thumb {
		width: 64px;
		height: 64px;
		flex-shrink: 0;
		border-radius: 8px;
		background: var(--d-page);
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	img {
		width: 100%;
		height: 100%;
		object-fit: contain;
	}
</style>
