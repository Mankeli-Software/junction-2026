<script lang="ts">
	/**
	 * Contacts with S.I.MO (design 11, docs/specs/call-screen.md §2.2): the generated
	 * company, the Call button, "Try saying" examples (text only), the kitchen and the
	 * usual order, and a phone-style tab bar whose Messages tab opens the inbox.
	 */
	import Icon from '../Icon.svelte';
	import TabBar from './TabBar.svelte';
	import { avoidsText, t, type StringKey } from '../../i18n';
	import type { DemoAccount, Lang } from '../../types';

	let {
		lang,
		account,
		unread,
		oncall,
		onchange,
		onmessages
	}: {
		lang: Lang;
		account: DemoAccount;
		unread: number;
		oncall: () => void;
		onchange: () => void;
		onmessages: () => void;
	} = $props();

	const examples: StringKey[] = ['try1', 'try2', 'try3', 'try4'];
	const usual = $derived(account.usual_items.map((item) => item.name[lang]).join(', '));
</script>

<div class="screen">
	<div class="status"><span></span><span data-testid="company">{account.company_name}</span></div>
	<div class="head">
		<h1 class="hd">{t(lang, 'contacts')}</h1>
		<div class="search" aria-hidden="true"><Icon name="search" size={16} stroke="#7D919C" />{t(lang, 'search')}</div>
	</div>

	<div class="scroll">
		<section class="simo" aria-label="S.I.MO">
			<div class="av big">S</div>
			<div class="who">
				<h2 class="hd">S.I.MO</h2>
				<p>{t(lang, 'simoTagline')}</p>
			</div>
			<button type="button" class="call" aria-label={t(lang, 'callAria')} onclick={oncall}>
				<Icon name="phone" stroke="#fff" />{t(lang, 'call')}
			</button>
		</section>

		<section class="try">
			<h3>{t(lang, 'trySaying')}</h3>
			<ul class="says">
				{#each examples as key (key)}
					<li class="say">{t(lang, key)}</li>
				{/each}
			</ul>
		</section>

		<section class="rows">
			<div class="ct">
				<div class="av small kitchen">K</div>
				<div class="ct-text">
					<span class="ct-name">{t(lang, 'kitchen')}</span>
					<span class="ct-sub" data-testid="kitchen">{avoidsText(lang, account.exclusions)}</span>
				</div>
				<button type="button" class="link" aria-label={t(lang, 'changeKitchen')} onclick={onchange}>{t(lang, 'change')}</button>
			</div>
			<div class="ct last">
				<div class="av small usual">U</div>
				<div class="ct-text">
					<span class="ct-name">{t(lang, 'usualOrder')}</span>
					<span class="ct-sub">{usual || t(lang, 'noUsual')}</span>
				</div>
			</div>
		</section>
	</div>

	<TabBar {lang} active="contacts" {unread} {onmessages} />
</div>

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
		background: #fff;
	}
	.status {
		padding: 18px 20px 6px;
		display: flex;
		justify-content: space-between;
		font-size: 13px;
		color: var(--faint);
		flex-shrink: 0;
	}
	.head {
		padding: 0 20px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		flex-shrink: 0;
	}
	h1 {
		font-size: 40px;
	}
	.search {
		height: 40px;
		border-radius: 10px;
		background: var(--page);
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0 12px;
		color: var(--faint);
		font-size: 15px;
	}
	.scroll {
		flex-grow: 1;
		overflow-y: auto;
		padding-bottom: 12px;
	}
	.simo {
		margin: 18px 16px 0;
		border-radius: 16px;
		background: var(--lavender);
		padding: 18px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
	}
	.av {
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		color: #fff;
		flex-shrink: 0;
	}
	.av.big {
		width: 84px;
		height: 84px;
		background: var(--petrol);
		font-size: 44px;
	}
	.av.small {
		width: 40px;
		height: 40px;
		font-size: 20px;
	}
	.kitchen {
		background: #b9a4d6;
	}
	.usual {
		background: #f0c46a;
		color: var(--ink) !important;
	}
	.who {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
	}
	.who h2 {
		font-size: 32px;
		color: var(--ink);
	}
	.who p {
		margin: 0;
		font-size: 16px;
		color: var(--muted-2);
		text-align: center;
	}
	.call {
		margin-top: 4px;
		height: 52px;
		padding: 0 28px;
		border-radius: 26px;
		border: 0;
		background: #1f8a3b;
		color: #fff;
		display: flex;
		align-items: center;
		gap: 10px;
		font-weight: 700;
		font-size: 18px;
		cursor: pointer;
	}
	.call:hover {
		background: #1a7733;
	}
	.try {
		padding: 18px 20px 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.try h3 {
		margin: 0;
		font-size: 13px;
		font-weight: 700;
		letter-spacing: 0.6px;
		color: var(--muted);
		text-transform: uppercase;
	}
	.says {
		list-style: none;
		margin: 0 -20px;
		padding: 0 20px 4px;
		display: flex;
		gap: 8px;
		overflow-x: auto;
		scrollbar-width: none;
	}
	.say {
		flex-shrink: 0;
		background: var(--page);
		border-radius: 10px;
		padding: 10px 12px;
		font-size: 14px;
		font-weight: 600;
		color: var(--petrol);
		max-width: 170px;
		line-height: 1.3;
	}
	.rows {
		padding: 10px 20px 0;
		display: flex;
		flex-direction: column;
	}
	.ct {
		display: flex;
		align-items: center;
		gap: 14px;
		padding: 10px 0;
		border-bottom: 1px solid var(--divider);
	}
	.ct.last {
		border-bottom: 0;
	}
	.ct-text {
		display: flex;
		flex-direction: column;
		flex-grow: 1;
		min-width: 0;
	}
	.ct-name {
		font-weight: 600;
		font-size: 16px;
	}
	.ct-sub {
		font-size: 13px;
		color: var(--faint);
	}
	.link {
		border: 0;
		background: none;
		padding: 8px 0 8px 8px;
		font-size: 14px;
		font-weight: 700;
		color: var(--petrol);
		text-decoration: underline;
		cursor: pointer;
	}
</style>
