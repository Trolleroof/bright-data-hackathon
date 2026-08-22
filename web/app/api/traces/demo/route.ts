import { NextResponse } from 'next/server';
import { generateCanonicalTrace, addCachedTrace } from '@/lib/canonical-traces';

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  let runType: 'A' | 'B' = 'A';
  try {
    const body = await req.json().catch(() => ({}));
    if (body.run && (body.run === 'B' || body.run.toString().toLowerCase().includes('b') || body.run.toString().toLowerCase().includes('avoid'))) {
      runType = 'B';
    }
  } catch {
    // default to A
  }

  // Attempt backend proxy
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600);
    fetch('http://127.0.0.1:8080/api/traces/demo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run: runType }),
      signal: controller.signal,
    }).catch(() => {});
    clearTimeout(timeoutId);
  } catch {
    // ignore
  }

  const newTrace = generateCanonicalTrace(runType);
  addCachedTrace(newTrace);

  return NextResponse.json({
    status: 'ok',
    run: runType,
    trace_id: newTrace.trace_id,
    trace: newTrace,
  });
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const runParam = searchParams.get('run') || 'A';
  const runType = runParam.toUpperCase() === 'B' ? 'B' : 'A';

  const newTrace = generateCanonicalTrace(runType);
  addCachedTrace(newTrace);

  return NextResponse.json({
    status: 'ok',
    run: runType,
    trace_id: newTrace.trace_id,
    trace: newTrace,
  });
}
