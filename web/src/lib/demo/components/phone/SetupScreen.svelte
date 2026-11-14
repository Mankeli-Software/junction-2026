<script lang="ts" module>
	export type { SetupValues } from '../../types';
</script>

<script lang="ts">
	/**
	 * Set up the demo phone (design 10, docs/specs/call-screen.md §2.1): the visitor's
	 * number, the kitchen exclusions as chips and the two notices.
	 */
	import Icon from '../Icon.svelte';
	import NumberEntry from '../NumberEntry.svelte';
	import TopBar from '../TopBar.svelte';
	import { t } from '../../i18n';
	import type { Lang, SetupValues } from '../../types';

	let {
		lang,
		langHref,
		initial,
		busy = false,
		error = null,
		onsubmit
	}: {
		lang: Lang;
		langHref: (lang: Lang) => string;
		initial: SetupValues;
		busy?: boolean;
		error?: 'limit' | 'failed' | null;
		onsubmit: (values: SetupValues, e164: string) => void;
	} = $props();
</script>

<div class="screen">
	<TopBar {lang} {langHref} />
	<div class="intro">
		<div class="phone-icon"><Icon name="phone" size={26} stroke="var(--petrol)" /></div>
		<div class="intro-text">
			<h1 class="hd">{t(lang, 'setupTitle')}</h1>
			<p>{t(lang, 'setupText')}</p>
		</div>
	</div>

	<NumberEntry
		{lang}
		{initial}
		{busy}
		{error}
		{onsubmit}
		notices={[
			{ icon: 'monitor', text: t(lang, 'noticeDashboard') },
			{ icon: 'chat', text: t(lang, 'noticeInbox') }
		]}
		submitLabel={t(lang, 'openDemoPhone')}
		busyLabel={t(lang, 'opening')}
	/>
</div>

<style>
	.screen {
		min-height: 100%;
		display: flex;
		flex-direction: column;
		background: var(--page);
	}
	.intro {
		background: var(--lavender);
		padding: 24px 20px 20px;
		display: flex;
		gap: 14px;
		align-items: center;
	}
	.phone-icon {
		width: 58px;
		height: 92px;
		flex-shrink: 0;
		border-radius: 12px;
		border: 3px solid var(--petrol);
		background: #fff;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.intro-text {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	h1 {
		font-size: 34px;
		line-height: 1;
		color: var(--petrol);
	}
	.intro p {
		margin: 0;
		font-size: 16px;
		line-height: 1.35;
		color: var(--muted-2);
	}
</style>
