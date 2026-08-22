import { NextResponse } from 'next/server';
import { getCachedTraces } from '@/lib/canonical-traces';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 800);
    const backendRes = await fetch('http://127.0.0.1:8080/api/status', {
      signal: controller.signal,
      cache: 'no-store',
    });
    clearTimeout(timeoutId);

    if (backendRes.ok) {
      const data = await backendRes.json();
      return NextResponse.json(data);
    }
  } catch {
    // Python backend not running, fallback to internal cached telemetry
  }

  const traces = getCachedTraces();
  const totalSpans = traces.reduce((acc, t) => acc + t.span_count, 0);

  return NextResponse.json({
    service: 'bidex',
    tracer_mode: 'signoz',
    signoz_endpoint: 'http://localhost:4318/v1/traces',
    signoz_ready: false,
    port_ready: false,
    brightdata_ready: false,
    total_spans: totalSpans,
    total_traces: traces.length,
  });
}
