<script lang="ts">
	/**
	 * The frame of the connector login pages (#48): the S.I.MO bar, a lavender intro and
	 * a narrow column, in the style of the call setup screen (docs/design 10). Centred on
	 * a computer, full width on a phone.
	 */
	import type { Snippet } from 'svelte';
	import { page } from '$app/state';
	import Icon from '../../demo/components/Icon.svelte';
	import TopBar from '../../demo/components/TopBar.svelte';
	import type { Lang } from '../../demo/types';
	import { at } from '../i18n';

	let { lang, title, text, children }: { lang: Lang; title: string; text: string; children: Snippet } = $props();

	function langHref(option: Lang): string {
		const target = new URL(page.url.href);
		if (option === 'fi') target.searchParams.set('lang', 'fi');
		else target.searchParams.delete('lang');
		return target.pathname + target.search;
	}
</script>

<div class="page">
	<div class="column">
		<TopBar {lang} {langHref} />
		<div class="intro">
			<div class="plug"><Icon name="plug" size={26} stroke="var(--petrol)" /></div>
			<div class="intro-text">
				<h1 class="hd">{title}</h1>
				<p>{text}</p>
			</div>
		</div>
		<div class="body">
			{@render children()}
			<p class="notice">{at(lang, 'noRealOrder')}</p>
		</div>
	</div>
</div>

<style>
	.page {
		min-height: 100vh;
		min-height: 100dvh;
		background: var(--page);
		display: flex;
		justify-content: center;
	}
	.column {
		width: 100%;
		max-width: 460px;
		display: flex;
		flex-direction: column;
		background: var(--page);
	}
	@media (min-width: 600px) {
		.page {
			padding: 40px 16px;
			align-items: flex-start;
		}
		.column {
			border: 1px solid var(--border);
			border-radius: 12px;
			overflow: hidden;
			box-shadow: 0 8px 30px rgb(16 48 63 / 8%);
		}
	}
	.intro {
		background: var(--lavender);
		padding: 24px 20px 20px;
		display: flex;
		gap: 14px;
		align-items: center;
	}
	.plug {
		width: 58px;
		height: 58px;
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
		margin: 0;
	}
	.intro p {
		margin: 0;
		font-size: 16px;
		line-height: 1.35;
		color: var(--muted-2);
	}
	.body {
		padding: 18px 20px 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.notice {
		margin: 0;
		font-size: 13px;
		color: var(--muted);
		text-align: center;
	}
	/* Shared by the pages' forms. */
	.body :global(.card) {
		background: #fff;
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.body :global(.label) {
		font-weight: 700;
		font-size: 15px;
	}
	.body :global(.text-input) {
		height: 50px;
		padding: 0 14px;
		border: 2px solid var(--petrol);
		border-radius: 6px;
		font: inherit;
		font-size: 18px;
		color: var(--ink);
		background: #fff;
		min-width: 0;
	}
	.body :global(.text-input[aria-invalid='true']) {
		border-color: var(--red);
	}
	.body :global(.hint) {
		font-size: 14px;
		color: var(--muted);
	}
	.body :global(.field-error) {
		display: flex;
		gap: 6px;
		align-items: flex-start;
		font-size: 14px;
		color: var(--red);
		font-weight: 600;
	}
	.body :global(.form-error) {
		margin: 0;
		display: flex;
		gap: 8px;
		align-items: flex-start;
		background: #fdecea;
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 15px;
		font-weight: 600;
		color: var(--red);
	}
	.body :global(.btn-main) {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 56px;
		border: 0;
		border-radius: 8px;
		background: var(--lime);
		color: var(--ink);
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 21px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		width: 100%;
		cursor: pointer;
	}
	.body :global(.btn-main:disabled) {
		opacity: 0.7;
		cursor: wait;
	}
	.body :global(.btn-plain) {
		height: 50px;
		border: 1px solid var(--border-strong);
		border-radius: 8px;
		background: #fff;
		color: var(--ink);
		font: inherit;
		font-weight: 700;
		font-size: 16px;
		width: 100%;
		cursor: pointer;
	}
	.body :global(.switch) {
		margin: 0;
		text-align: center;
		font-size: 15px;
		color: var(--muted-2);
	}
	.body :global(.switch a) {
		color: var(--petrol);
		font-weight: 700;
	}
</style>
