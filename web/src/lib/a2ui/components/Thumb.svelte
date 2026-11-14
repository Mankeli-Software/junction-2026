<script lang="ts" module>
	export type ThumbPlaceholder = 'plate' | 'box' | 'none';
</script>

<script lang="ts">
	/**
	 * One product or recipe image, as technical-plan.md §5.5 says: only the API's own
	 * `image_url`, lazy, no Referer, fixed width and height, and a placeholder when the
	 * URL is null or the image fails to load. `placeholder: 'none'` draws nothing instead
	 * (a group header without an image). No context needed, so any page can use it.
	 */
	import { safeImage } from '../format';
	import Icon from './Icon.svelte';

	let {
		src,
		width,
		height,
		alt = '',
		label,
		fit = 'cover',
		placeholder = 'box',
		radius = 8
	}: {
		src: string | null | undefined;
		width: number;
		height: number;
		/** The image's own alt text; empty when the name is already next to it. */
		alt?: string;
		/** An accessible name for the frame (placeholder included), when the image stands alone. */
		label?: string;
		/** `cover` for recipe photos, `contain` for product packshots. */
		fit?: 'cover' | 'contain';
		placeholder?: ThumbPlaceholder;
		radius?: number;
	} = $props();

	const url = $derived(safeImage(src));
	let failed = $state(false);
	let failedFor = $state<string | null>(null);
	// A new URL gets a new try.
	const broken = $derived(failed && failedFor === url);
	const show = $derived(Boolean(url) && !broken);
</script>

{#if show || placeholder !== 'none'}
	<span
		class="thumb"
		class:contain={fit === 'contain'}
		style="width: {width}px; height: {height}px; border-radius: {radius}px"
		role={label ? 'img' : undefined}
		aria-label={label}
		data-testid="thumb"
		data-empty={!show}
	>
		{#if show && url}
			<img
				src={url}
				{width}
				{height}
				alt={label ? '' : alt}
				loading="lazy"
				decoding="async"
				referrerpolicy="no-referrer"
				onerror={() => {
					failed = true;
					failedFor = url;
				}}
			/>
		{:else}
			<Icon
				name={placeholder === 'plate' ? 'plate' : 'box'}
				size={Math.max(14, Math.round(Math.min(width, height) * 0.42))}
				stroke="var(--faint)"
				weight={1.8}
			/>
		{/if}
	</span>
{/if}

<style>
	.thumb {
		flex-shrink: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
		background: var(--page);
	}
	.thumb.contain {
		background: #fff;
		border: 1px solid var(--divider);
	}
	img {
		display: block;
		width: 100%;
		height: 100%;
		object-fit: cover;
	}
	.contain img {
		object-fit: contain;
	}
</style>
