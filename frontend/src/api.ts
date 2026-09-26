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

/** The page's language (carried on <html lang>), for the few messages the
 *  client writes itself. */
const isEn = () => typeof document !== "undefined" && document.documentElement.lang === "en";

/** What to say when the server gave no readable reason (network down, proxy
 *  page, timeout): never the browser's raw "Failed to fetch". */
function fallbackMessage(status: number): string {
  const en = isEn();
  if (status === 0) return en ? "The server cannot be reached. Check your connection and try again."
                              : "Le serveur est injoignable. Vérifiez la connexion puis réessayez.";
  if (status === 408) return en ? "The server took too long to answer. Try again."
                                : "Le serveur a mis trop de temps à répondre. Réessayez.";
  if (status === 413) return en ? "The file is too large." : "Le fichier est trop volumineux.";
  if (status === 502 || status === 503 || status === 504)
    return en ? "The service is restarting. Try again in a few seconds."
              : "Le service redémarre. Réessayez dans quelques secondes.";
  if (status >= 500) return en ? "Unexpected server error. Try again." : "Erreur inattendue du serveur. Réessayez.";
  return en ? "Error" : "Erreur";
}

/** No answer after this long: the call fails with a readable message instead
 *  of leaving a spinner forever. */
const TIMEOUT_MS = 30000;

/**
 * Core of every call: sends, turns a network failure or a timeout into an
 * {@link ApiError} (status 0 / 408), parses the body and throws on non-2xx.
 * FastAPI validation errors arrive as an array of `{msg}` objects under
 * `detail`; those are flattened into a single message.
 *
 * Two answers concern the whole app rather than the screen that asked, so they
 * are also announced as window events: a 401 (the session is gone,
 * "app:session-lost") and a 403 "access_*" (the account was disabled or put
 * back on hold, "app:access-changed").
 */
async function send<T>(path: string, opts: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let resp: Response;
  try {
    resp = await fetch(path, {
      ...opts,
      credentials: "include",
      signal: ctrl.signal,
      headers: { ...(opts.headers as Record<string, string> | undefined), "Accept-Language": isEn() ? "en" : "fr" },
    });
  } catch (e: any) {
    throw new ApiError(e?.name === "AbortError" ? 408 : 0, fallbackMessage(e?.name === "AbortError" ? 408 : 0));
  } finally {
    clearTimeout(timer);
  }
  // 204 No Content: nothing to parse (e.g. successful DELETE).
  if (resp.status === 204) return undefined as T;
  const text = await resp.text().catch(() => "");
  let data: any = undefined;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!resp.ok) {
    const detail = data && typeof data === "object" && data.detail ? data.detail : null;
    const msg = Array.isArray(detail)
      ? detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ")
      : detail ? String(detail) : fallbackMessage(resp.status);
    if (typeof window !== "undefined") {
      if (resp.status === 401 && !/^\/api\/auth\//.test(path)) window.dispatchEvent(new Event("app:session-lost"));
      if (resp.status === 403 && typeof detail === "string" && detail.startsWith("access_"))
        window.dispatchEvent(new Event("app:access-changed"));
    }
    throw new ApiError(resp.status, msg);
  }
  return data as T;
}

/** JSON endpoints. The body is serialised only when given, so GET/DELETE send
 *  neither body nor Content-Type. */
function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  return send<T>(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

/** Multipart uploads (e.g. certificate/PFX files). No Content-Type header: the
 *  browser sets multipart/form-data with its boundary. */
function requestForm<T>(path: string, form: FormData): Promise<T> {
  return send<T>(path, { method: "POST", body: form });
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

/** What to tell the user about a failed call: the server's message, else a
 *  generic word in the page's language (the page carries it on <html lang>). */
export function errorText(e: unknown): string {
  if (e instanceof ApiError && e.message) return e.message;
  // A TypeError from a render or a parse: not a message for the user.
  return fallbackMessage(-1);
}

/** A field that saves when one leaves it may be gone by the time the server
 *  answers (the next step is already shown). Its failure is then said by the
 *  layout, whatever screen is open (Layout listens to this event). */
export function reportSaveError(message: string) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("app:save-error", { detail: message }));
}
