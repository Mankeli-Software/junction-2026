/**
 * Reads the `action` prop of a `Button` the model wrote. Both shapes are accepted:
 * A2UI v0.9's `{event: {name, context}}` (what Genkit's prompt teaches) and the short
 * `{name, context}`. Context values are literals (string, number, boolean) or data
 * bindings `{path: "/x"}`, read from the surface's data model when the button is
 * pressed. Anything else is dropped.
 */
import { record } from './resolve';

export interface ButtonAction {
	name: string;
	/** Literal context values. */
	context: Record<string, string | number | boolean>;
	/** Context keys bound to data-model paths. */
	paths: Record<string, string>;
}

const NAME = /^[A-Za-z][A-Za-z0-9_.-]{0,59}$/;
const MAX_KEYS = 20;
const MAX_TEXT = 400;

export function buttonAction(value: unknown): ButtonAction | null {
	const outer = record(value);
	const inner = 'event' in outer ? record(outer.event) : outer;
	const name = inner.name;
	if (typeof name !== 'string' || !NAME.test(name)) return null;
	const context: ButtonAction['context'] = {};
	const paths: ButtonAction['paths'] = {};
	for (const [key, raw] of Object.entries(record(inner.context)).slice(0, MAX_KEYS)) {
		if (key === '__proto__' || key === 'constructor' || key === 'prototype') continue;
		if (typeof raw === 'string') context[key] = raw.slice(0, MAX_TEXT);
		else if ((typeof raw === 'number' && Number.isFinite(raw)) || typeof raw === 'boolean') context[key] = raw;
		else {
			const path = record(raw).path;
			if (typeof path === 'string') paths[key] = path;
		}
	}
	return { name, context, paths };
}
