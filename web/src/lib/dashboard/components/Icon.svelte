<script lang="ts" module>
	/** Inline stroke icons from the design (docs/design/html/30 to 33), as path data only. */
	const circle = (cx: number, cy: number, r: number) =>
		`M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
	const rect = (x: number, y: number, w: number, h: number, r: number) =>
		`M${x + r} ${y}h${w - 2 * r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - 2 * r)}a${r} ${r} 0 0 1 ${r} ${-r}z`;

	const PATHS = {
		phone: ['M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2'],
		chat: ['M4 5h16v11H8l-4 4z'],
		webmcp: [rect(3, 4, 18, 14, 2), 'M3 8h18M8 13l-2 2 2 2M16 13l2 2-2 2'],
		plug: ['M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5'],
		user: [circle(12, 8, 4), 'M4 21c1-4 4-6 8-6s7 2 8 6'],
		bot: [rect(4, 7, 16, 12, 3), 'M12 3v4M9 13h.01M15 13h.01'],
		code: ['M8 6l-5 6 5 6M16 6l5 6-5 6'],
		search: [circle(11, 11, 6), 'M20 20l-4.5-4.5'],
		check: ['M5 12l5 5 9-10'],
		link: [
			'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1'
		],
		shield: ['M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z', 'M8.5 12l2.5 2.5 4.5-5'],
		shieldx: ['M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z', 'M9.5 9.5l5 5M14.5 9.5l-5 5'],
		list: ['M4 6h16M4 12h16M4 18h10'],
		arrow: ['M2 10h22M18 4l6 6-6 6'],
		down: ['M6 9l6 6 6-6'],
		up: ['M6 15l6-6 6 6'],
		refresh: ['M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5'],
		download: ['M12 4v11M7 10l5 5 5-5M5 20h14'],
		box: [rect(3, 7, 18, 12, 2), 'M7 7V5h10v2'],
		alert: [circle(12, 12, 9), 'M12 8v5M12 16.5v.5'],
		plus: ['M4 12h16M12 4v16'],
		arrowup: ['M12 19V5M6 11l6-6 6 6'],
		engine: [circle(12, 12, 3), 'M12 3v3M12 18v3M3 12h3M18 12h3'],
		x: ['M6 6l12 12M18 6L6 18']
	} as const satisfies Record<string, readonly string[]>;

	export type IconName = keyof typeof PATHS;
</script>

<script lang="ts">
	interface Props {
		name: IconName;
		size?: number;
		color?: string;
		stroke?: number;
	}

	let { name, size = 16, color = 'currentColor', stroke = 2.2 }: Props = $props();
	const wide = $derived(name === 'arrow');
</script>

<svg
	width={wide ? Math.round(size * 1.4) : size}
	height={size}
	viewBox={wide ? '0 0 28 20' : '0 0 24 24'}
	fill="none"
	stroke={color}
	stroke-width={stroke}
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
>
	{#each PATHS[name] as d, i (i)}<path {d} />{/each}
</svg>
