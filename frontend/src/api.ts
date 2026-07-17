/**
 * Thin fetch-based HTTP client for the backend API.
 *
 * Centralises the cross-cutting concerns every call needs: cookie-based session
 * auth (`credentials: "include"`), JSON (de)serialisation, empty-body (204)
 * handling, and turning non-2xx responses into a typed {@link ApiError} so
 * callers can `catch` and branch on `.status` (e.g. 401 -> logged out).
 */

/**
 * Error thrown for any non-2xx response. Carries the HTTP `status` so callers
 * can react to it (e.g. treat 401 as "session expired"). The `message` is the
 * best human-readable detail extracted from the response body.
 */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Core request helper for JSON endpoints.
 *
 * Serialises `body` to JSON (only when provided, so GET/DELETE send no body or
 * Content-Type), parses the response, and throws {@link ApiError} on failure.
 * FastAPI validation errors arrive as an array of `{msg}` objects under
 * `detail`; those are flattened into a single comma-joined message.
 *
 * @returns The parsed response body typed as `T` (or `undefined` for 204).
 */
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = {
    method,
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  };
  const resp = await fetch(path, opts);
  // 204 No Content: nothing to parse (e.g. successful DELETE).
  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  let data: any = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!resp.ok) {
    const detail = data && data.detail ? data.detail : resp.statusText;
    const msg = Array.isArray(detail)
      ? detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
      : String(detail);
    throw new ApiError(resp.status, msg);
  }
  return data as T;
}

/**
 * Variant of {@link request} for multipart uploads (e.g. certificate/PFX files).
 * Sends `FormData` so the browser can set the multipart boundary itself.
 */
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  // No Content-Type header: the browser sets multipart/form-data with the boundary.
  const resp = await fetch(path, { method: "POST", credentials: "include", body: form });
  const text = await resp.text();
  let data: any = undefined;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!resp.ok) {
    const detail = data && data.detail ? data.detail : resp.statusText;
    const msg = Array.isArray(detail)
      ? detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
      : String(detail);
    throw new ApiError(resp.status, msg);
  }
  return data as T;
}

/**
 * Public API surface used across the app. One method per HTTP verb, each
 * generic over the expected response type. `post`/`put` default the body to
 * `{}` so endpoints that expect a JSON object never receive a bare `undefined`.
 */
export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  del: <T>(path: string) => request<T>("DELETE", path),
  postForm: <T>(path: string, form: FormData) => requestForm<T>(path, form),
};
