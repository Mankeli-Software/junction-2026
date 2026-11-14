/**
 * Keeps the A2UI surfaces of one chat: applies the envelopes the agent streams
 * and turns component events into client actions (docs/specs/a2ui.md §2, §3).
 */
import type { A2uiClientAction, A2uiComponent, A2uiServerEnvelope } from './protocol';
import { SIMO_CATALOG_ID } from './protocol';

export interface Surface {
	id: string;
	catalogId: string;
	components: Record<string, A2uiComponent>;
	data: unknown;
	/** False for a surface on another catalog: it is not rendered. */
	supported: boolean;
}

export type ActionHandler = (action: A2uiClientAction) => void;

/** Most components one surface keeps; the rest of an oversized update is dropped. */
const MAX_COMPONENTS = 200;

function unescapeToken(token: string): string {
	return token.replace(/~1/g, '/').replace(/~0/g, '~');
}

function pointerTokens(path: string): string[] {
	if (path === '' || path === '/') return [];
	return path.replace(/^\//, '').split('/').map(unescapeToken);
}

const UNSAFE_KEYS = new Set(['__proto__', 'prototype', 'constructor']);

function isObject(value: unknown): value is Record<string, unknown> {
	return value !== null && typeof value === 'object';
}

/** Reads a JSON Pointer from a data model. Undefined when any step is missing. */
export function getPath(data: unknown, path: string): unknown {
	let at: unknown = data;
	for (const token of pointerTokens(path)) {
		if (!isObject(at) || UNSAFE_KEYS.has(token) || !Object.hasOwn(at, token)) return undefined;
		at = at[token];
	}
	return at;
}

/** Returns a copy of `data` with `value` at `path`, making objects along the way. */
export function setPath(data: unknown, path: string, value: unknown): unknown {
	const tokens = pointerTokens(path);
	if (tokens.length === 0) return value;
	if (tokens.some((t) => UNSAFE_KEYS.has(t))) return data;
	const root: Record<string, unknown> = isObject(data) ? structuredClone($state.snapshot(data) as Record<string, unknown>) : {};
	let at: Record<string, unknown> = root;
	tokens.slice(0, -1).forEach((token) => {
		const next = at[token];
		at[token] = isObject(next) ? next : {};
		at = at[token] as Record<string, unknown>;
	});
	at[tokens[tokens.length - 1]] = value;
	return root;
}

export class SurfaceStore {
	surfaces = $state<Record<string, Surface>>({});
	/** Surface ids in the order they were created, for the message list. */
	order = $state<string[]>([]);
	/**
	 * What the buyer already did on a card, by `surfaceId/componentId`, so a card that
	 * is drawn again stays read-only after its action (an answered question, a sent quote).
	 */
	acted = $state<Record<string, string>>({});
	#onAction: ActionHandler;

	constructor(onAction: ActionHandler) {
		this.#onAction = onAction;
	}

	process(envelopes: A2uiServerEnvelope[]): void {
		if (!Array.isArray(envelopes)) return;
		for (const envelope of envelopes as unknown[]) {
			if (!isObject(envelope)) continue;
			if ('createSurface' in envelope) {
				const body = envelope.createSurface;
				if (!isObject(body) || typeof body.surfaceId !== 'string') continue;
				const surfaceId = body.surfaceId;
				const catalogId = typeof body.catalogId === 'string' ? body.catalogId : '';
				if (!this.surfaces[surfaceId]) this.order.push(surfaceId);
				this.surfaces[surfaceId] = {
					id: surfaceId,
					catalogId,
					components: {},
					data: {},
					supported: catalogId === SIMO_CATALOG_ID
				};
			} else if ('updateComponents' in envelope) {
				const body = envelope.updateComponents;
				if (!isObject(body) || typeof body.surfaceId !== 'string' || !Array.isArray(body.components)) continue;
				const surface = this.surfaces[body.surfaceId];
				if (!surface) continue;
				for (const component of body.components as unknown[]) {
					if (!isObject(component)) continue;
					const { id, component: name } = component;
					if (typeof id !== 'string' || typeof name !== 'string' || UNSAFE_KEYS.has(id)) continue;
					if (!surface.components[id] && Object.keys(surface.components).length >= MAX_COMPONENTS) continue;
					surface.components[id] = component as A2uiComponent;
				}
			} else if ('updateDataModel' in envelope) {
				const body = envelope.updateDataModel;
				if (!isObject(body) || typeof body.surfaceId !== 'string') continue;
				const surface = this.surfaces[body.surfaceId];
				if (!surface) continue;
				const path = typeof body.path === 'string' ? body.path : '';
				surface.data = setPath(surface.data, path, body.value);
			} else if ('deleteSurface' in envelope) {
				const body = envelope.deleteSurface;
				if (!isObject(body) || typeof body.surfaceId !== 'string') continue;
				const surfaceId = body.surfaceId;
				delete this.surfaces[surfaceId];
				this.order = this.order.filter((id) => id !== surfaceId);
			}
		}
	}

	setData(surfaceId: string, path: string, value: unknown): void {
		const surface = this.surfaces[surfaceId];
		if (surface) surface.data = setPath(surface.data, path, value);
	}

	/** Remembers what the buyer did on a card (see `acted`). */
	markActed(surfaceId: string, componentId: string, value: string): void {
		this.acted[`${surfaceId}/${componentId}`] = value;
	}

	actedOn(surfaceId: string, componentId: string): string | undefined {
		return this.acted[`${surfaceId}/${componentId}`];
	}

	/**
	 * Sends an action to the agent. `contextPaths` are data-model paths whose
	 * current values go into the context (A2UI forms), next to fixed `context`.
	 */
	emit(
		surfaceId: string,
		sourceComponentId: string,
		name: string,
		context: Record<string, unknown> = {},
		contextPaths: Record<string, string> = {}
	): void {
		const surface = this.surfaces[surfaceId];
		const bound = Object.fromEntries(
			Object.entries(contextPaths).map(([key, path]) => [key, $state.snapshot(getPath(surface?.data, path))])
		);
		this.#onAction({
			name,
			surfaceId,
			sourceComponentId,
			timestamp: new Date().toISOString(),
			context: { ...bound, ...context }
		});
	}
}
