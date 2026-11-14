<script lang="ts">
	/** A recipe image (UI-04), or the placeholder plate when there is none or it fails (technical-plan.md §5.5). */
	import { chatContext } from '../context';
	import { t } from '../i18n';
	import Thumb from './Thumb.svelte';

	let { url, size = 76, height }: { url: string | null | undefined; size?: number; height?: number } = $props();
	const { lang } = chatContext();
</script>

<Thumb
	src={url}
	width={size}
	height={height ?? size}
	label={url ? t(lang(), 'recipeImage') : t(lang(), 'noImage')}
	placeholder="plate"
/>
