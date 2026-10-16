import { describe, expect, it } from 'vitest';
import { ApiError, toApiError } from './client';

// `$env/static/public` is a SvelteKit virtual module; vitest resolves it via the plugin.

function response(status: number, body: unknown, headers: Record<string, string> = {}) {
	return new Response(JSON.stringify(body), { status, headers });
}

describe('toApiError', () => {
	it('reads kind and message from the API error body', async () => {
		const err = await toApiError(
			response(404, { detail: { kind: 'draft_not_found', message: 'nope', detail: null } })
		);
		expect(err).toBeInstanceOf(ApiError);
		expect(err.kind).toBe('draft_not_found');
		expect(err.message).toBe('nope');
	});

	it('reads Retry-After on a rate limit', async () => {
		const err = await toApiError(
			response(429, { detail: { kind: 'rate_limited', message: 'slow' } }, { 'Retry-After': '42' })
		);
		expect(err.kind).toBe('rate_limited');
		expect(err.retryAfter).toBe(42);
	});

	it('treats FastAPI validation errors as invalid input', async () => {
		const err = await toApiError(response(422, { detail: [{ msg: 'field required' }] }));
		expect(err.kind).toBe('invalid_input');
	});

	it('falls back to unknown when the body is not JSON', async () => {
		const err = await toApiError(new Response('<html>Bad gateway</html>', { status: 502 }));
		expect(err.kind).toBe('unknown');
	});
});
