/**
 * What the demo phone keeps in this tab's sessionStorage: the number entry, the demo
 * account and the inbox messages already seen. The webshop (#56) writes the same
 * entry after its number entry, so /phone opens on Contacts with the same account.
 * The session cookie stays the login; this only remembers what the screens show.
 */
import type { DemoAccount, SetupValues } from './types';

const STORAGE_KEY = 'simo.phone';

export interface StoredPhone {
	values?: SetupValues;
	account?: DemoAccount | null;
	seen?: string[];
}

export function readPhone(): StoredPhone {
	try {
		const stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? 'null');
		return typeof stored === 'object' && stored !== null ? stored : {};
	} catch {
		return {};
	}
}

export function writePhone(state: StoredPhone): void {
	try {
		sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
	} catch {
		// Private mode: the phone just won't survive a reload.
	}
}
