<script lang="ts">
	/**
	 * Demo start (docs/design screens 00 on a computer, 01 on a phone): the ways to try
	 * the demo. On a phone, calling S.I.MO comes first and the dashboard last.
	 */
	import Icon from '#lib/demo/components/Icon.svelte';
	import TopBar from '#lib/demo/components/TopBar.svelte';
	import { t, type StringKey } from '#lib/demo/i18n.js';
	import type { Lang } from '#lib/demo/types.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
	const lang = $derived(data.lang);
	const q = $derived(lang === 'fi' ? '?lang=fi' : '');
	const langHref = (option: Lang) => (option === 'fi' ? '?lang=fi' : '/');

	let copied = $state(false);
	async function copyAddress() {
		try {
			await navigator.clipboard.writeText(data.mcpUrl);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// Clipboard not allowed: the address is selectable in the field.
		}
	}

	const steps: StringKey[] = ['step1', 'step2', 'step3', 'step4'];
</script>

<svelte:head>
	<title>S.I.MO, Junction 2026</title>
	<meta name="description" content={t(lang, 'heroText')} />
</svelte:head>

<div class="page">
	<TopBar {lang} {langHref} wide />

	<section class="hero">
		<div class="wrap">
			<h1 class="hd">
				<span class="computer">{t(lang, 'heroTitle')}</span><span class="phone">{t(lang, 'heroTitlePhone')}</span>
			</h1>
			<p>
				<span class="computer">{t(lang, 'heroText')}</span><span class="phone">{t(lang, 'heroTextPhone')}</span>
			</p>
		</div>
	</section>

	<main class="wrap body">
		<!-- On a phone (01): a short list, the call first and the dashboard last. -->
		<div class="phone list">
			<a class="call-card" href="/phone{q}">
				<span class="row-head">
					<span class="oico lime"><Icon name="phone" stroke="#10303F" /></span>
					<span class="col">
						<span class="hd call-title">{t(lang, 'callSimo')}</span>
						<span class="call-sub">{t(lang, 'callSimoShort')}</span>
					</span>
				</span>
				<span class="start">{t(lang, 'start')}</span>
			</a>
			<a class="row" href="/shop{q}">
				<span class="oico small lavender"><Icon name="chat" size={20} stroke="#6E559A" /></span>
				<span class="col grow"><b>{t(lang, 'webshopShort')}</b><span class="sub">{t(lang, 'webshopShortText')}</span></span>
				<Icon name="chevron-right" size={16} stroke="var(--petrol)" weight={2.5} />
			</a>
			<a class="row" href="#own-agent">
				<span class="oico small green"><Icon name="plug" size={20} stroke="#3F5A00" /></span>
				<span class="col grow"><b>{t(lang, 'ownAgentShort')}</b><span class="sub">{t(lang, 'ownAgentShortText')}</span></span>
				<Icon name="chevron-right" size={16} stroke="var(--petrol)" weight={2.5} />
			</a>
			<a class="row dashed" href="/dashboard{q}">
				<span class="oico small blue"><Icon name="monitor" size={20} stroke="var(--petrol)" /></span>
				<span class="col grow"><b>{t(lang, 'dashboardShort')}</b><span class="sub">{t(lang, 'dashboardShortText')}</span></span>
				<Icon name="arrow-out" size={16} stroke="var(--petrol)" weight={2.5} />
			</a>
		</div>

		<!-- On a computer (00): three options side by side. -->
		<h2 class="hd section computer">{t(lang, 'tryIt')}</h2>
		<div class="computer options">
			<div class="opt main">
				<div class="opt-head">
					<span class="oico petrol"><Icon name="phone" stroke="#C6E02A" /></span>
					<h3 class="hd">{t(lang, 'callSimo')}</h3>
				</div>
				<p>{t(lang, 'callSimoText')}</p>
				<div class="qr-row">
					<div class="qr" role="img" aria-label={t(lang, 'qrAlt')}>{@html data.qr}</div>
					<span>{t(lang, 'scanQr')}</span>
				</div>
				<div class="grow"></div>
				<a class="btn-main" href="/phone{q}">{t(lang, 'callFromComputer')}</a>
			</div>
			<div class="opt">
				<div class="opt-head">
					<span class="oico blue"><Icon name="chart" stroke="var(--petrol)" /></span>
					<h3 class="hd">{t(lang, 'dashboardTitle')}</h3>
				</div>
				<p>{t(lang, 'dashboardText')}</p>
				<div class="grow"></div>
				<a class="btn-sec" href="/dashboard{q}">{t(lang, 'openDashboard')}</a>
			</div>
			<div class="opt">
				<div class="opt-head">
					<span class="oico lavender"><Icon name="chat" stroke="#6E559A" /></span>
					<h3 class="hd">{t(lang, 'webshopTitle')}</h3>
				</div>
				<p>{t(lang, 'webshopText')}</p>
				<div class="grow"></div>
				<a class="btn-sec" href="/shop{q}">{t(lang, 'openWebshop')}</a>
			</div>
		</div>

		<section class="agent" id="own-agent">
			<div class="agent-intro">
				<div class="opt-head">
					<span class="oico green"><Icon name="plug" stroke="#3F5A00" /></span>
					<h3 class="hd">{t(lang, 'ownAgentTitle')}</h3>
				</div>
				<p>{t(lang, 'ownAgentText')}</p>
				<label for="mcpurl">{t(lang, 'mcpAddress')}</label>
				<div class="copy-row">
					<input id="mcpurl" class="mono" value={data.mcpUrl} readonly onfocus={(e) => e.currentTarget.select()} />
					<button type="button" class="copy" aria-label={t(lang, 'copyAddress')} onclick={copyAddress}>
						<Icon name={copied ? 'check' : 'copy'} size={18} stroke="#fff" />
					</button>
				</div>
				<span class="visually-hidden" aria-live="polite">{copied ? t(lang, 'copied') : ''}</span>
			</div>
			<div class="ways">
				<div class="way"><b>Claude</b><span>{t(lang, 'wayClaude')}</span></div>
				<div class="way"><b>{t(lang, 'wayOpenAiLabel')}</b><span>{t(lang, 'wayOpenAi')}</span></div>
				<div class="way"><b>{t(lang, 'wayAnyLabel')}</b><span>{t(lang, 'wayAny')}</span></div>
				<div class="way last">
					<b>{t(lang, 'wayDevelopers')}</b><span><a href="/api/v1/docs" data-sveltekit-reload>{t(lang, 'wayDocs')}</a></span>
				</div>
			</div>
		</section>

		<section class="computer how">
			<h2 class="hd section">{t(lang, 'howItWorks')}</h2>
			<ol class="steps">
				{#each steps as key, i (key)}
					<li class="step"><span class="num">{i + 1}</span><span>{@html t(lang, key)}</span></li>
				{/each}
			</ol>
		</section>

		<p class="note computer"><b>{t(lang, 'footLead')}</b> {t(lang, 'footText')}</p>
		<p class="note phone"><b>{t(lang, 'footLeadPhone')}</b> {t(lang, 'footTextPhone')}</p>
	</main>
</div>

<style>
	.page {
		min-height: 100dvh;
		display: flex;
		flex-direction: column;
		background: var(--page);
	}
	.wrap {
		width: 100%;
		max-width: 1200px;
		margin: 0 auto;
		padding: 0 16px;
	}
	.hero {
		background: var(--lavender);
	}
	.hero .wrap {
		padding-top: 26px;
		padding-bottom: 22px;
		padding-left: 20px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.hero h1 {
		font-size: 40px;
		line-height: 1;
		color: var(--petrol);
		max-width: 760px;
	}
	.hero p {
		margin: 0;
		font-size: 16px;
		line-height: 1.4;
		color: var(--muted-2);
		max-width: 680px;
	}
	.body {
		padding-top: 18px;
		padding-bottom: 22px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		flex-grow: 1;
	}
	.computer {
		display: none;
	}
	.col {
		display: flex;
		flex-direction: column;
	}
	.grow {
		flex-grow: 1;
	}

	/* Phone list (01) */
	.list {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.call-card {
		display: flex;
		flex-direction: column;
		gap: 12px;
		background: var(--petrol);
		color: #fff;
		border-radius: 14px;
		padding: 18px;
		text-decoration: none;
	}
	.call-card:hover {
		color: #fff;
	}
	.row-head {
		display: flex;
		gap: 14px;
		align-items: center;
	}
	.call-title {
		font-size: 28px;
		color: #fff;
	}
	.call-sub {
		font-size: 14px;
		color: #cfe0e8;
	}
	.start {
		height: 48px;
		border-radius: 8px;
		background: var(--lime);
		color: var(--ink);
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 19px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
	}
	.row {
		display: flex;
		gap: 14px;
		align-items: center;
		background: #fff;
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 14px;
		text-decoration: none;
		color: var(--ink);
	}
	.row b {
		font-size: 17px;
	}
	.row .sub {
		font-size: 14px;
		color: var(--muted);
	}
	.row.dashed {
		background: #f8fafb;
		border-style: dashed;
	}
	.oico {
		width: 48px;
		height: 48px;
		border-radius: 24px;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.oico.small {
		width: 44px;
		height: 44px;
	}
	.lime {
		background: var(--lime);
	}
	.petrol {
		background: var(--petrol);
	}
	.blue {
		background: #e3edf2;
	}
	.lavender {
		background: #f4f0f9;
	}
	.green {
		background: #e6f2c2;
	}

	/* Computer (00) */
	.section {
		font-size: 34px;
	}
	.options {
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 18px;
	}
	.opt {
		background: #fff;
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 22px;
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
	}
	.opt.main {
		border: 2px solid var(--petrol);
	}
	.opt-head {
		display: flex;
		gap: 14px;
		align-items: center;
	}
	.opt h3,
	.agent h3 {
		font-size: 28px;
	}
	.opt p,
	.agent p {
		margin: 0;
		font-size: 16px;
		line-height: 1.4;
		color: var(--muted-2);
	}
	.qr-row {
		display: flex;
		gap: 14px;
		align-items: center;
		font-size: 15px;
		line-height: 1.4;
	}
	.qr {
		width: 104px;
		height: 104px;
		flex-shrink: 0;
		border: 2px solid var(--ink);
		border-radius: 8px;
		padding: 4px;
		background: #fff;
	}
	.qr :global(svg) {
		display: block;
		width: 100%;
		height: 100%;
	}
	.btn-main,
	.btn-sec {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 50px;
		border-radius: 8px;
		font-family: var(--font-head);
		font-weight: 700;
		font-size: 19px;
		letter-spacing: 0.6px;
		text-transform: uppercase;
		text-decoration: none;
	}
	.btn-main {
		background: var(--lime);
		color: var(--ink);
	}
	.btn-main:hover {
		color: var(--ink);
	}
	.btn-sec {
		border: 2px solid var(--petrol);
		color: var(--petrol);
		background: #fff;
	}

	.agent {
		background: #fff;
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 20px;
		display: flex;
		flex-wrap: wrap;
		gap: 20px 28px;
		scroll-margin-top: 16px;
	}
	.agent-intro {
		flex: 1 1 300px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.agent label {
		font-size: 14px;
		font-weight: 700;
		margin-top: 6px;
	}
	.copy-row {
		display: flex;
		gap: 8px;
	}
	.mono {
		font-family: 'JetBrains Mono', ui-monospace, monospace;
		font-size: 14px;
	}
	.copy-row input {
		flex-grow: 1;
		min-width: 0;
		height: 46px;
		border: 1px solid var(--border-strong);
		border-radius: 6px;
		padding: 0 12px;
		background: #f8fafb;
		color: var(--ink);
	}
	.copy {
		width: 46px;
		height: 46px;
		border-radius: 6px;
		border: 0;
		background: var(--petrol);
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		flex-shrink: 0;
	}
	.ways {
		flex: 1.4 1 380px;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	.way {
		display: grid;
		grid-template-columns: 150px minmax(0, 1fr);
		gap: 12px;
		align-items: baseline;
		padding: 10px 0;
		border-bottom: 1px solid var(--divider);
		font-size: 15px;
	}
	.way.last {
		border-bottom: 0;
	}
	.how {
		flex-direction: column;
		gap: 14px;
	}
	.steps {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 16px;
	}
	.step {
		display: flex;
		gap: 12px;
		align-items: center;
		font-size: 16px;
	}
	.num {
		width: 34px;
		height: 34px;
		flex-shrink: 0;
		border-radius: 17px;
		background: var(--petrol);
		color: #fff;
		font-weight: 700;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.note {
		margin: 0;
		background: var(--yellow-note);
		border-radius: 8px;
		padding: 10px 14px;
		font-size: 14px;
	}
	.note.phone {
		margin-top: auto;
	}

	@media (max-width: 759px) {
		.way {
			grid-template-columns: 1fr;
			gap: 2px;
		}
		.agent {
			padding: 16px;
		}
		.agent h3 {
			font-size: 24px;
		}
	}

	@media (min-width: 760px) {
		.computer {
			display: revert;
		}
		.options {
			display: grid;
		}
		.how {
			display: flex;
		}
		.phone,
		.list,
		.note.phone {
			display: none;
		}
		.wrap {
			padding: 0 32px;
		}
		.hero .wrap {
			padding: 48px 32px 40px;
			gap: 14px;
		}
		.hero h1 {
			font-size: 64px;
			line-height: 0.95;
		}
		.hero p {
			font-size: 20px;
		}
		.body {
			padding-top: 32px;
			padding-bottom: 48px;
			gap: 28px;
		}
		.agent {
			padding: 24px;
		}
		.note {
			padding: 12px 16px;
			font-size: 15px;
		}
	}
</style>
