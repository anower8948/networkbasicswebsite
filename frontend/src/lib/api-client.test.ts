import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiClient, getAccessToken, setAccessToken } from './api-client';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiError', () => {
  it('exposes field errors from the envelope', () => {
    const error = new ApiError(422, 'validation_error', 'Invalid', {
      fields: { email: 'Enter a valid email address.' },
    });

    expect(error.fieldErrors).toEqual({ email: 'Enter a valid email address.' });
    expect(error.isAuthError).toBe(false);
  });

  it('returns an empty object when there are no field errors', () => {
    expect(new ApiError(500, 'internal_server_error', 'Boom').fieldErrors).toEqual({});
  });

  it('flags 401 responses as auth errors', () => {
    expect(new ApiError(401, 'invalid_token', 'Expired').isAuthError).toBe(true);
  });
});

describe('apiClient', () => {
  beforeEach(() => {
    setAccessToken(null);
    vi.restoreAllMocks();
  });

  it('attaches the bearer token when one is set', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('token-abc');

    await apiClient.get('/health');

    const headers = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer token-abc');
  });

  it('omits the Authorization header when signed out', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);

    await apiClient.get('/health');

    const headers = (fetchMock.mock.calls[0]?.[1] as RequestInit).headers as Headers;
    expect(headers.get('Authorization')).toBeNull();
  });

  it('throws an ApiError carrying the server envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          { error: { code: 'invalid_credentials', message: 'Incorrect email or password.' } },
          401,
        ),
      ),
    );

    await expect(apiClient.post('/auth/login', {}, { skipAuthRetry: true })).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
      message: 'Incorrect email or password.',
    });
  });

  it('refreshes once and replays the request after a 401', async () => {
    const fetchMock = vi
      .fn()
      // 1. original request is unauthorised
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'invalid_token' } }, 401))
      // 2. refresh succeeds
      .mockResolvedValueOnce(jsonResponse({ accessToken: 'renewed-token' }))
      // 3. replay succeeds
      .mockResolvedValueOnce(jsonResponse({ username: 'learner' }));
    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('stale-token');

    const result = await apiClient.get<{ username: string }>('/auth/me');

    expect(result.username).toBe('learner');
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(getAccessToken()).toBe('renewed-token');
  });

  it('clears the token when refresh cannot recover the session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'invalid_token' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: { code: 'invalid_token' } }, 401));
    vi.stubGlobal('fetch', fetchMock);
    setAccessToken('stale-token');

    await expect(apiClient.get('/auth/me')).rejects.toBeInstanceOf(ApiError);
    expect(getAccessToken()).toBeNull();
  });

  it('does not retry when skipAuthRetry is set', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ error: { code: 'invalid_credentials' } }, 401));
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      apiClient.post('/auth/login', {}, { skipAuthRetry: true }),
    ).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
