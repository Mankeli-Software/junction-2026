/**
 * Reads component props the model wrote. A prop is either a literal or a
 * data binding `{ "path": "/x" }` (A2UI v0.9). Anything of the wrong type is
 * dropped, so a mistaken model can only leave a component empty.
 */
import { getPath, type Surface } from './surfaces.svelte';

function bound(surface: Surface, value: unknown): unknown {
	if (value !== null && typeof value === 'object' && 'path' in value) {
		const path = (value as { path: unknown }).path;
		return typeof path === 'string' ? getPath(surface.data, path) : undefined;
	}
	return value;
}

export function str(surface: Surface, value: unknown, max = 400): string | undefined {
	const v = bound(surface, value);
	if (typeof v === 'number') return String(v);
	return typeof v === 'string' && v.trim() ? v.slice(0, max) : undefined;
}

export function int(surface: Surface, value: unknown, min: number, max: number): number | undefined {
	const v = bound(surface, value);
	const n = typeof v === 'string' ? Number(v) : v;
	return typeof n === 'number' && Number.isInteger(n) && n >= min && n <= max ? n : undefined;
}

/** Child ids: a plain id array (the only children form our catalog allows). */
export function ids(value: unknown): string[] {
	return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string').slice(0, 30) : [];
}

export function record(value: unknown): Record<string, unknown> {
	return value !== null && typeof value === 'object' && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}
