import { BACKEND_URL } from '@/lib/backend';

/**
 * Pipe a backend multipart/x-mixed-replace feed straight through to the browser.
 *
 * The body is forwarded as a stream, never buffered — buffering an endless
 * MJPEG response would hang the request forever. If the backend is down we
 * return 503 so the <img> fires onError and the panel can say why.
 */
export async function proxyMjpeg(path: string): Promise<Response> {
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}${path}`, { cache: 'no-store' });
  } catch {
    return new Response('live backend offline', { status: 503 });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response('no live feed', { status: 503 });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type':
        upstream.headers.get('content-type') ??
        'multipart/x-mixed-replace; boundary=bidexframe',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      Connection: 'keep-alive',
      // Nothing between here and the browser may buffer a live feed.
      'X-Accel-Buffering': 'no',
    },
  });
}
