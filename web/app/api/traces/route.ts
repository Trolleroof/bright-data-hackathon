import { NextResponse } from 'next/server';
import { getCachedTraces, clearCachedTraces } from '@/lib/canonical-traces';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 800);
    const backendRes = await fetch('http://127.0.0.1:8080/api/traces', {
      signal: controller.signal,
      cache: 'no-store',
    });
    clearTimeout(timeoutId);

    if (backendRes.ok) {
      const data = await backendRes.json();
      if (data.traces && data.traces.length > 0) {
        return NextResponse.json(data);
      }
    }
  } catch {
    // Python backend not running or timed out
  }

  const traces = getCachedTraces();
  return NextResponse.json({
    traces,
    count: traces.length,
  });
}

export async function POST(req: Request) {
  try {
    const body = await req.json().catch(() => ({}));
    if (body.action === 'clear') {
      try {
        await fetch('http://127.0.0.1:8080/api/traces/clear', {
          method: 'POST',
        });
      } catch {
        // ignore
      }
      clearCachedTraces();
      return NextResponse.json({ status: 'cleared' });
    }
  } catch {
    // ignore
  }

  return NextResponse.json({ status: 'ok' });
}
