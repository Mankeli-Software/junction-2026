/**
 * Keeps the screen on during the call where the browser allows it (Screen Wake
 * Lock), so the call doesn't drop when the phone locks (docs/specs/call-screen.md
 * §2.3). The browser releases the lock when the page is hidden, so it is taken
 * again when the page comes back. Returns the function that releases it.
 */
export function keepScreenAwake(onChange: (held: boolean) => void = () => {}): () => void {
	let active = true;
	let sentinel: WakeLockSentinel | null = null;

	async function request() {
		if (!active || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
		try {
			const lock = await navigator.wakeLock.request('screen');
			if (!active) {
				await lock.release();
				return;
			}
			sentinel = lock;
			onChange(true);
			lock.addEventListener('release', () => {
				if (sentinel === lock) sentinel = null;
				onChange(false);
			});
		} catch {
			// Not allowed (battery saver, iframe, older browser): the call still works.
			onChange(false);
		}
	}

	const onVisibility = () => {
		if (!sentinel) void request();
	};
	document.addEventListener('visibilitychange', onVisibility);
	void request();

	return () => {
		active = false;
		document.removeEventListener('visibilitychange', onVisibility);
		void sentinel?.release().catch(() => {});
		sentinel = null;
	};
}
