/** Per-page UI state shared by the dashboard components through context (safe under SSR). */
import { getContext, setContext } from 'svelte';
import type { Lang } from './types';

export interface Ui {
	lang: Lang;
	/** Wall clock in ms, ticking every second on the client, for time in state. */
	now: number;
}

const KEY = Symbol('dashboard-ui');

export function createUi(lang: Lang): Ui {
	const ui = $state<Ui>({ lang, now: Date.now() });
	setContext(KEY, ui);
	return ui;
}

export function useUi(): Ui {
	return getContext<Ui>(KEY);
}
