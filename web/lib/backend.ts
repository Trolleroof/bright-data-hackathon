/**
 * The Python flight-recorder backend (web/server.py).
 *
 * Every live feature — the twin render, the camera feed, the cube telemetry —
 * lives there because it needs MuJoCo and OpenCV. Next.js proxies to it so the
 * browser only ever talks to one origin, and so a backend that is not running
 * degrades to a readable "offline" state instead of a CORS error.
 */
export const BACKEND_URL =
  process.env.BIDEX_BACKEND_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8080';

/** Short-timeout JSON fetch. Returns null when the backend is down or slow. */
export async function backendJson<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 1500
): Promise<T | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      signal: controller.signal,
      cache: 'no-store',
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

/** Proxy a request to the Python backend for Next.js route handlers. */
export async function proxyBackend(
  path: string,
  init?: RequestInit
): Promise<Response> {
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, { ...init, cache: 'no-store' });
    const body = await res.text();
    return new Response(body, {
      status: res.status,
      headers: {
        'Content-Type': res.headers.get('content-type') ?? 'application/json',
      },
    });
  } catch {
    return new Response(JSON.stringify({ error: 'backend offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
