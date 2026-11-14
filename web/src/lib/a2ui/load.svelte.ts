/** One thing a card loads by id, with the states every card shows (UI-02, "Card states"). */
import { isNotFound } from './api';

export type LoadStatus = 'loading' | 'ready' | 'error' | 'notfound';

export class Loaded<T> {
	status = $state<LoadStatus>('loading');
	value = $state.raw<T | null>(null);
	#fetch: () => Promise<T>;
	#seq = 0;

	constructor(fetch: () => Promise<T>) {
		this.#fetch = fetch;
	}

	/** Loads (again). A slower earlier answer never overwrites a newer one. */
	load(): void {
		const seq = ++this.#seq;
		this.status = 'loading';
		let promise: Promise<T>;
		try {
			promise = this.#fetch();
		} catch (error) {
			promise = Promise.reject(error);
		}
		promise.then(
			(value) => {
				if (seq !== this.#seq) return;
				this.value = value;
				this.status = 'ready';
			},
			(error: unknown) => {
				if (seq !== this.#seq) return;
				this.status = isNotFound(error) ? 'notfound' : 'error';
			}
		);
	}

	/** Loads again without the loading state; a failure keeps what is shown. */
	refresh(): void {
		if (this.status !== 'ready') return this.load();
		const seq = ++this.#seq;
		this.#fetch().then(
			(value) => {
				if (seq === this.#seq) this.value = value;
			},
			() => {}
		);
	}

	/** Shows a value the card got from an action (confirm, copy) without loading. */
	set(value: T): void {
		this.#seq++;
		this.value = value;
		this.status = 'ready';
	}
}
