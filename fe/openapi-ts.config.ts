import { defaultPlugins } from '@hey-api/openapi-ts';

export default {
	input: 'http://127.0.0.1:8001/openapi.json',
	output: './src/lib/client',
	plugins: [
		...defaultPlugins,
		'@hey-api/client-fetch',
		{
			asClass: true,
			name: '@hey-api/sdk'
		}
	]
};
