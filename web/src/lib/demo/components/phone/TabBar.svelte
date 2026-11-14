<script lang="ts">
	/**
	 * The phone app's tab bar (design 11). Messages opens the simulated inbox; it takes
	 * the place of the design's Favourites, since the inbox needs a way in. Recents and
	 * Keypad are part of the phone look only.
	 */
	import Icon from '../Icon.svelte';
	import { t } from '../../i18n';
	import type { Lang } from '../../types';

	let {
		lang,
		active,
		unread,
		onmessages,
		oncontacts = () => {}
	}: {
		lang: Lang;
		active: 'contacts' | 'messages';
		unread: number;
		onmessages: () => void;
		oncontacts?: () => void;
	} = $props();
</script>

<nav class="tabs">
	<button
		type="button"
		class="tab"
		class:active={active === 'messages'}
		aria-current={active === 'messages' ? 'page' : undefined}
		onclick={onmessages}
	>
		<span class="icon">
			<Icon name="chat" size={24} stroke={active === 'messages' ? 'var(--petrol)' : '#7D919C'} weight={2} />
			{#if unread > 0}<span class="badge" aria-label={t(lang, 'unread', { n: unread })}>{unread}</span>{/if}
		</span>
		{t(lang, 'tabMessages')}
	</button>
	<span class="tab inert" aria-hidden="true"><Icon name="clock" size={24} stroke="#7D919C" weight={2} />{t(lang, 'tabRecents')}</span>
	<button
		type="button"
		class="tab"
		class:active={active === 'contacts'}
		aria-current={active === 'contacts' ? 'page' : undefined}
		onclick={oncontacts}
	>
		<Icon name="person" size={24} stroke={active === 'contacts' ? 'var(--petrol)' : '#7D919C'} weight={2.2} />
		{t(lang, 'tabContacts')}
	</button>
	<span class="tab inert" aria-hidden="true"><Icon name="keypad" size={24} stroke="#7D919C" />{t(lang, 'tabKeypad')}</span>
</nav>

<style>
	.tabs {
		border-top: 1px solid #e3eaef;
		padding: 10px 8px 22px;
		display: flex;
		flex-shrink: 0;
		background: #fff;
	}
	.tab {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 3px;
		font-size: 12px;
		font-weight: 600;
		color: var(--faint);
		border: 0;
		background: none;
		padding: 0;
		cursor: pointer;
	}
	.tab.inert {
		cursor: default;
	}
	.tab.active {
		color: var(--petrol);
	}
	.icon {
		position: relative;
		display: flex;
	}
	.badge {
		position: absolute;
		top: -6px;
		right: -10px;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		border-radius: 9px;
		background: #d9433a;
		color: #fff;
		font-size: 11px;
		font-weight: 700;
		display: flex;
		align-items: center;
		justify-content: center;
	}
</style>
