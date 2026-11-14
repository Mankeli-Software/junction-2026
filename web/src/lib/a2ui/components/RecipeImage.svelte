<script lang="ts">
	/** A recipe image, or the placeholder plate when there is none or it fails (UI-04). Lazy, no referrer. */
	import { chatContext } from '../context';
	import { safeImage } from '../format';
	import { t } from '../i18n';
	import Icon from './Icon.svelte';

	let { url, size = 76 }: { url: string | null | undefined; size?: number } = $props();
	const { lang } = chatContext();
	const src = $derived(safeImage(url));
	let failed = $state(false);
</script>

<div class="a2-img" style="width: {size}px; height: {size}px" role="img" aria-label={src && !failed ? t(lang(), 'recipeImage') : t(lang(), 'noImage')}>
	{#if src && !failed}
		<img {src} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={() => (failed = true)} />
	{:else}
		<Icon name="plate" size={Math.round(size * 0.4)} stroke="var(--faint)" weight={1.8} />
	{/if}
</div>
