import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	PUBLIC_DASHBOARD_MOCK: {
		public: true,
		description:
			'"1" serves the dashboard from the mock fixtures and replays fake live events, so it runs without the API (#50).',
		schema: (value) => value === '1'
	},
	API_INTERNAL_URL: {
		description:
			'FastAPI as the web server reaches it for the first page load. "http://api:8000" inside Compose.',
		schema: (value) => (value ? value.replace(/\/+$/, '') : 'http://localhost:8000')
	}
});
