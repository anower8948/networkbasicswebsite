/**
 * Typed HTTP client for the platform API.
 *
 * Session model
 * -------------
 * The access token is held **in memory only** — never in `localStorage`, which
 * is readable by any injected script. The refresh token lives in an httpOnly
 * cookie the browser attaches automatically and JavaScript cannot read.
 *
 * A page reload therefore starts with no access token; `AuthProvider` calls
 * `POST /auth/refresh` once on mount to silently restore the session from the
 * cookie.
 *
 * Automatic refresh
 * -----------------
 * When a request returns 401, the client refreshes once and replays the
 * original request. Concurrent 401s share a single in-flight refresh promise
 * rather than each firing their own — without that, five parallel requests
 * would trigger five rotations and the reuse-detection logic on the server
 * would correctly treat four of them as replays and kill the session.
 */

import type { ApiErrorBody } from '@/types/api';

const API_BASE = '/api/v1';

/** An error carrying the server's structured error envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Field-level validation messages, keyed by field name. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details?.['fields'];
    return typeof fields === 'object' && fields !== null
      ? (fields as Record<string, string>)
      : {};
  }

  get isAuthError(): boolean {
    return this.status === 401;
  }
}

/* -------------------------------------------------------------------------- */
/* In-memory access token                                                      */
/* -------------------------------------------------------------------------- */
let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

/** Register a callback invoked when the session cannot be recovered. */
export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

/* -------------------------------------------------------------------------- */
/* Refresh coordination                                                        */
/* -------------------------------------------------------------------------- */
let refreshInFlight: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) return null;
    const body = (await response.json()) as { accessToken: string };
    accessToken = body.accessToken;
    return body.accessToken;
  } catch {
    return null;
  }
}

/** Refresh the session, coalescing concurrent callers onto one request. */
export function refreshSession(): Promise<string | null> {
  refreshInFlight ??= performRefresh().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

/* -------------------------------------------------------------------------- */
/* Core request                                                                */
/* -------------------------------------------------------------------------- */
interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Skip the automatic refresh-and-retry. Used by the auth calls themselves. */
  skipAuthRetry?: boolean;
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let message = response.statusText || 'Request failed';
  let details: Record<string, unknown> | undefined;

  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    // A non-JSON body (a proxy error page, say) leaves the defaults in place.
  }

  return new ApiError(response.status, code, message, details);
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipAuthRetry = false, headers, ...init } = options;

  const send = async (): Promise<Response> => {
    const requestHeaders = new Headers(headers);
    requestHeaders.set('Accept', 'application/json');
    if (body !== undefined) requestHeaders.set('Content-Type', 'application/json');
    if (accessToken) requestHeaders.set('Authorization', `Bearer ${accessToken}`);

    return fetch(`${API_BASE}${path}`, {
      ...init,
      headers: requestHeaders,
      // Always send the refresh cookie; it is path-scoped server-side, so it
      // only actually travels to /auth routes.
      credentials: 'include',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  };

  let response = await send();

  if (response.status === 401 && !skipAuthRetry) {
    const renewed = await refreshSession();
    if (renewed) {
      response = await send();
    } else {
      accessToken = null;
      onSessionExpired?.();
    }
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  // 204 and other empty responses have no body to parse.
  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', ...(body !== undefined ? { body } : {}) }),

  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', ...(body !== undefined ? { body } : {}) }),

  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', ...(body !== undefined ? { body } : {}) }),

  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};
