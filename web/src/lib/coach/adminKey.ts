// Where the admin page keeps the Admin Key: sessionStorage, which the
// browser forgets when the tab closes. It is never put in a URL (URLs end up
// in history and server logs) or in a cookie (a cookie would ride along on
// every request, including from the public page).
//
// Storage can be blocked (a private window, strict privacy settings), so
// every access is wrapped: without storage the key lasts until a reload.

const STORAGE_KEY = 'boostertutor.adminKey';

export function loadAdminKey(): string | null {
	try {
		return sessionStorage.getItem(STORAGE_KEY);
	} catch {
		return null;
	}
}

export function saveAdminKey(key: string): void {
	try {
		sessionStorage.setItem(STORAGE_KEY, key);
	} catch {
		// Not remembered; the page still holds it in memory.
	}
}

export function forgetAdminKey(): void {
	try {
		sessionStorage.removeItem(STORAGE_KEY);
	} catch {
		// Nothing was stored.
	}
}
