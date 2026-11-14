/** Runs the in-browser chain check for a page, again whenever the steps change. */
import type { Step } from './types';
import { verifyChain, type VerifyResult } from './verify';

export interface ChainCheck {
	readonly result: VerifyResult | null;
	readonly checking: boolean;
	again(): void;
}

/** Call during component init. The check runs only in the browser (effects don't run on the server). */
export function chainCheck(getSteps: () => readonly Step[]): ChainCheck {
	const state = $state({ result: null as VerifyResult | null, checking: false });
	let run = 0;

	async function check(steps: readonly Step[]): Promise<void> {
		const mine = ++run;
		state.checking = true;
		const result = await verifyChain(steps);
		if (mine !== run) return;
		state.result = result;
		state.checking = false;
	}

	$effect(() => {
		void check(getSteps());
	});

	return {
		get result() {
			return state.result;
		},
		get checking() {
			return state.checking;
		},
		again() {
			state.result = null;
			void check(getSteps());
		}
	};
}
