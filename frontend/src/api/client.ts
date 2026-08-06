/**
 * The single HTTP boundary for the application.
 *
 * Everything that talks to the API goes through here: base URL resolution,
 * auth headers, error normalisation and token refresh. No component calls
 * `fetch` directly.
 */

const BASE_URL = (import.meta.env['VITE_API_BASE_URL'] as string | undefined) ?? '/api/v1';

const ACCESS_TOKEN_KEY = 'aegis.access_token';
const REFRESH_TOKEN_KEY = 'aegis.refresh_token';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | undefined;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** Whether retrying the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }

  /** Field-level validation problems, when the server returned them. */
  get validationProblems(): string[] {
    const problems = this.details?.['problems'];
    if (Array.isArray(problems)) return problems.map(String);

    const errors = this.details?.['errors'];
    if (Array.isArray(errors)) {
      return errors.map((entry) => {
        const e = entry as { loc?: unknown[]; msg?: string };
        const field = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : '';
        return field ? `${field}: ${e.msg ?? 'invalid'}` : (e.msg ?? 'invalid');
      });
    }
    return [];
  }
}

export const tokenStore = {
  get access(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY);
  },
  get refresh(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  },
  set(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  },
  setAccess(access: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
  },
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler = () => {};

/** Registered by the auth provider so a hard 401 can clear the session. */
export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Internal: prevents infinite recursion through the refresh path. */
  skipRefresh?: boolean;
}

/**
 * Concurrent 401s must not each trigger their own refresh. The first request
 * to notice an expired token owns the refresh; the rest await the same promise.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refresh = tokenStore.refresh;
  if (!refresh) return false;

  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!response.ok) return false;
      const data = (await response.json()) as { access_token: string; refresh_token: string };
      tokenStore.set(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, skipRefresh = false } = options;

  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const token = tokenStore.access;
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check your connection.');
  }

  // Expired access token: refresh once, then replay the original request.
  if (response.status === 401 && !skipRefresh && tokenStore.refresh) {
    if (await refreshAccessToken()) {
      return request<T>(path, { ...options, skipRefresh: true });
    }
    tokenStore.clear();
    onUnauthorized();
  }

  if (response.status === 204) return undefined as T;

  const payload = await parseBody(response);

  if (!response.ok) {
    const error = payload as {
      error?: string;
      message?: string;
      details?: Record<string, unknown>;
    };
    throw new ApiError(
      response.status,
      error?.error ?? 'unknown_error',
      error?.message ?? `Request failed with status ${response.status}.`,
      error?.details,
    );
  }

  return payload as T;
}

async function parseBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) {
    return await response.text();
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) =>
    request<T>(path, signal ? { signal } : {}),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>(path, { method: 'POST', body, ...(signal ? { signal } : {}) }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

/** Absolute URL for an API path, with optional query parameters. */
export function buildUrl(path: string, params?: Record<string, string>): string {
  const url = `${BASE_URL}${path}`;
  if (!params || Object.keys(params).length === 0) return url;
  const query = new URLSearchParams(params).toString();
  return `${url}?${query}`;
}

export interface SseFrame {
  event: string;
  data: string;
}

/**
 * Consume a Server-Sent Events stream.
 *
 * Implemented over `fetch` rather than `EventSource` because `EventSource`
 * cannot set request headers: the only way to authenticate it would be a token
 * in the query string, which leaks into browser history, proxy logs and the
 * Referer header. A streamed `fetch` sends a normal Authorization header.
 */
export async function* streamEvents(
  path: string,
  signal: AbortSignal,
): AsyncGenerator<SseFrame> {
  const token = tokenStore.access;
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  });

  if (!response.ok) {
    const payload = (await parseBody(response)) as { message?: string; error?: string } | null;
    throw new ApiError(
      response.status,
      payload?.error ?? 'stream_failed',
      payload?.message ?? 'The event stream could not be opened.',
    );
  }
  if (!response.body) {
    throw new ApiError(0, 'stream_unsupported', 'Streaming is not supported by this browser.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line. A partial frame stays in the
      // buffer until the rest of it arrives.
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');

        const frame = parseFrame(raw);
        if (frame) yield frame;
      }
    }
  } finally {
    reader.cancel().catch(() => {
      /* the stream is already closing; nothing to recover */
    });
  }
}

function parseFrame(raw: string): SseFrame | null {
  let event = 'message';
  const dataLines: string[] = [];

  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue; // comment / heartbeat
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) return null;
  return { event, data: dataLines.join('\n') };
}

/** Triggers a browser download for an authenticated endpoint. */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const token = tokenStore.access;
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const payload = (await parseBody(response)) as { message?: string; error?: string } | null;
    throw new ApiError(
      response.status,
      payload?.error ?? 'download_failed',
      payload?.message ?? 'The download could not be completed.',
    );
  }

  const disposition = response.headers.get('content-disposition') ?? '';
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? fallbackName;

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoke on the next tick; revoking synchronously can cancel the download
  // in some browsers before it starts.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
