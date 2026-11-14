<script lang="ts" module>
	export type IconName =
		| 'phone'
		| 'hangup'
		| 'monitor'
		| 'chart'
		| 'chat'
		| 'plug'
		| 'copy'
		| 'search'
		| 'star'
		| 'clock'
		| 'person'
		| 'keypad'
		| 'mic'
		| 'mic-off'
		| 'speaker'
		| 'speaker-off'
		| 'captions'
		| 'check'
		| 'chevron-down'
		| 'chevron-right'
		| 'chevron-left'
		| 'arrow-out'
		| 'alert'
		| 'cart'
		| 'package';
</script>

<script lang="ts">
	/** Inline stroke icons from the design export (docs/design/html). Decorative: always aria-hidden. */
	let {
		name,
		size = 22,
		stroke = 'currentColor',
		weight = 2.2
	}: { name: IconName; size?: number; stroke?: string; weight?: number } = $props();
</script>

{#if name === 'keypad'}
	<svg width={size} height={size} viewBox="0 0 24 24" fill={stroke} aria-hidden="true">
		{#each [5, 11, 17] as y (y)}
			{#each [6, 12, 18] as x (x)}
				<circle cx={x} cy={y} r="1.8" />
			{/each}
		{/each}
	</svg>
{:else}
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
		{#if name === 'phone'}
			<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2" />
		{:else if name === 'hangup'}
			<path d="M3 14c5-4.5 13-4.5 18 0l-2 3-3.5-1.2V13a12 12 0 0 0-7 0v2.8L5 17z" />
		{:else if name === 'monitor'}
			<rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4" />
		{:else if name === 'chart'}
			<rect x="3" y="4" width="18" height="12" rx="2" /><path d="M8 20h8M12 16v4M7 12l3-3 2 2 4-4" />
		{:else if name === 'chat'}
			<path d="M4 5h16v11H8l-4 4z" />
		{:else if name === 'plug'}
			<path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5" />
		{:else if name === 'copy'}
			<rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" />
		{:else if name === 'search'}
			<circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" />
		{:else if name === 'star'}
			<path d="M12 3l2.6 5.6 6 .7-4.5 4 1.2 6L12 16.4 6.7 19.3l1.2-6-4.5-4 6-.7z" />
		{:else if name === 'clock'}
			<circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" />
		{:else if name === 'person'}
			<circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" />
		{:else if name === 'mic'}
			<rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
		{:else if name === 'mic-off'}
			<rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3M4 4l16 16" />
		{:else if name === 'speaker'}
			<path d="M4 9h4l5-4v14l-5-4H4z" /><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a7.5 7.5 0 0 1 0 11" />
		{:else if name === 'speaker-off'}
			<path d="M4 9h4l5-4v14l-5-4H4z" /><path d="M16 9l5 6M21 9l-5 6" />
		{:else if name === 'captions'}
			<rect x="3" y="5" width="18" height="14" rx="2" /><path d="M7 11h4M13 11h4M7 15h7" />
		{:else if name === 'check'}
			<path d="M5 12l5 5 9-10" />
		{:else if name === 'chevron-down'}
			<path d="M6 9l6 6 6-6" />
		{:else if name === 'chevron-right'}
			<path d="M9 6l6 6-6 6" />
		{:else if name === 'chevron-left'}
			<path d="M15 6l-6 6 6 6" />
		{:else if name === 'arrow-out'}
			<path d="M7 17L17 7M9 7h8v8" />
		{:else if name === 'alert'}
			<circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.5" />
		{:else if name === 'cart'}
			<path d="M3 4h2l2.5 11h11L21 7H7" /><circle cx="9" cy="19" r="1.5" /><circle cx="18" cy="19" r="1.5" />
		{:else if name === 'package'}
			<path d="M4 7.5L12 3l8 4.5v9L12 21l-8-4.5z" /><path d="M4 7.5l8 4.5 8-4.5M12 12v9" />
		{/if}
	</svg>
{/if}
