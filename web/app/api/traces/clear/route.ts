import { NextResponse } from 'next/server';
import { clearCachedTraces } from '@/lib/canonical-traces';

export const dynamic = 'force-dynamic';

export async function POST() {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 600);
    fetch('http://127.0.0.1:8080/api/traces/clear', {
      method: 'POST',
      signal: controller.signal,
    }).catch(() => {});
    clearTimeout(timeoutId);
  } catch {
    // ignore
  }

  clearCachedTraces();
  return NextResponse.json({ status: 'cleared' });
}
