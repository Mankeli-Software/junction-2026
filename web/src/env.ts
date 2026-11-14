import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	PUBLIC_DASHBOARD_MOCK: {
		public: true,
		description:
			'"1" serves the dashboard from the mock fixtures and replays fake live events, so it runs without the API (#50).',
		schema: (value) => value === '1'
	},
	SHOP_LANG: {
		description:
			'The webshop\'s default language (#56): "auto" picks Finnish when the browser\'s Accept-Language prefers fi, otherwise English; "fi" or "en" fixes it. The EN/FI toggle still works.',
		schema: (value): 'auto' | 'fi' | 'en' => {
			if (!value) return 'auto';
			if (value === 'auto' || value === 'fi' || value === 'en') return value;
			throw new Error(`SHOP_LANG must be "auto", "fi" or "en", not "${value}"`);
		}
	},
	API_INTERNAL_URL: {
		description:
			'FastAPI as the web server reaches it, for the dashboard\'s page loads and its local passthrough of /api/v1/public. Defaults to API_BASE_URL, then http://localhost:8000.',
		schema: (value) => {
			const fallback = typeof process === 'undefined' ? undefined : process.env.API_BASE_URL;
			return (value || fallback || 'http://localhost:8000').replace(/\/+$/, '');
		}
	}
});
