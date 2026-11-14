import { getContext, setContext } from 'svelte';
import type { SurfaceStore } from './surfaces.svelte';
import type { ChatData, Lang } from './types';

export interface ChatContext {
	store: SurfaceStore;
	data: ChatData;
	lang: () => Lang;
	/**
	 * Optional: a number the chat panel bumps after each turn (`done`). Cards whose
	 * data can change on the server (the quote, the sent notice) load it again quietly.
	 */
	revision?: () => number;
}

const KEY = Symbol('a2ui-chat');

export function setChatContext(value: ChatContext): void {
	setContext(KEY, value);
}

export function chatContext(): ChatContext {
	const value = getContext<ChatContext | undefined>(KEY);
	if (!value) throw new Error('A2UI components need setChatContext() above them');
	return value;
}
