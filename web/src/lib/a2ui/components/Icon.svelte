<script lang="ts" module>
	/** Inline stroke icons for the chat cards, from the design (UI-01). Decorative: always aria-hidden. */
	export type IconName =
		| 'check'
		| 'alert'
		| 'info'
		| 'pencil'
		| 'trash'
		| 'minus'
		| 'plus'
		| 'camera'
		| 'phone'
		| 'warn'
		| 'chevron'
		| 'none'
		| 'plate';
</script>

<script lang="ts">
	let {
		name,
		size = 16,
		stroke = 'currentColor',
		weight = 2.2
	}: { name: IconName; size?: number; stroke?: string; weight?: number } = $props();
</script>

<svg
	class="icon"
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
	{:else if name === 'alert'}
		<circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.5" />
	{:else if name === 'info'}
		<circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" />
	{:else if name === 'pencil'}
		<path d="M4 20h4L19 9l-4-4L4 16z" />
	{:else if name === 'trash'}
		<path d="M4 7h16M10 7V4h4v3M6 7l1 13h10l1-13" />
	{:else if name === 'minus'}
		<path d="M6 12h12" />
	{:else if name === 'plus'}
		<path d="M12 6v12M6 12h12" />
	{:else if name === 'camera'}
		<path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" />
	{:else if name === 'phone'}
		<rect x="7" y="3" width="10" height="18" rx="2" /><path d="M11 18h2" />
	{:else if name === 'warn'}
		<path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17v.5" />
	{:else if name === 'chevron'}
		<path d="M6 9l6 6 6-6" />
	{:else if name === 'none'}
		<circle cx="12" cy="12" r="9" /><path d="M8 12h8" />
	{:else if name === 'plate'}
		<circle cx="12" cy="13" r="8" /><path d="M4 13h16" />
	{/if}
</svg>

<style>
	.icon {
		flex-shrink: 0;
	}
</style>
