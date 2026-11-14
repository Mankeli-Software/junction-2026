<script lang="ts">
	/** Inline stroke icons from the design export. Decorative: always aria-hidden. */
	type Name =
		| 'check'
		| 'up'
		| 'alert'
		| 'info'
		| 'pencil'
		| 'close'
		| 'minus'
		| 'plus'
		| 'trash'
		| 'shield'
		| 'box';

	let {
		name,
		size = 16,
		stroke = 'currentColor',
		weight = 2.2
	}: { name: Name; size?: number; stroke?: string; weight?: number } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	{stroke}
	stroke-width={weight}
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	{#if name === 'check'}
		<path d="M5 12l5 5 9-10" />
	{:else if name === 'up'}
		<path d="M12 19V5M6 11l6-6 6 6" />
	{:else if name === 'alert'}
		<circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.5" />
	{:else if name === 'info'}
		<circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" />
	{:else if name === 'pencil'}
		<path d="M4 20h4L19 9l-4-4L4 16z" />
	{:else if name === 'close'}
		<path d="M6 6l12 12M18 6L6 18" />
	{:else if name === 'minus'}
		<path d="M6 12h12" />
	{:else if name === 'plus'}
		<path d="M12 6v12M6 12h12" />
	{:else if name === 'trash'}
		<path d="M4 7h16M10 7V4h4v3M6 7l1 13h10l1-13" />
	{:else if name === 'shield'}
		<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" />
	{:else if name === 'box'}
		<rect x="3" y="7" width="18" height="12" rx="2" /><path d="M7 7V5h10v2" />
	{/if}
</svg>
