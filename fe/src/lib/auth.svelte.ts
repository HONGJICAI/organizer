import { client } from '$lib/client/client.gen';

const TOKEN_KEY = 'organizer-auth-token';

class AuthState {
	token = $state<string | null>(
		typeof localStorage !== 'undefined' ? localStorage.getItem(TOKEN_KEY) : null
	);
	required = $state(false);

	get isLoggedIn() {
		return !this.required || this.token !== null;
	}

	setToken(t: string) {
		this.token = t;
		localStorage.setItem(TOKEN_KEY, t);
		import('$app/navigation').then(({ invalidateAll }) => invalidateAll());
	}

	clearToken() {
		this.token = null;
		localStorage.removeItem(TOKEN_KEY);
	}
}

export const authState = new AuthState();

let _interceptorsRegistered = false;

export function setupAuthInterceptors() {
	if (_interceptorsRegistered) return;
	_interceptorsRegistered = true;

	client.interceptors.request.use((request) => {
		if (authState.token) {
			request.headers.set('Authorization', `Bearer ${authState.token}`);
		}
		return request;
	});

	client.interceptors.response.use((response) => {
		if (response.status === 401) {
			authState.required = true;
			authState.clearToken();
		}
		return response;
	});
}
