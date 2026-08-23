import { NextResponse } from 'next/server';
import { backendJson } from '@/lib/backend';

export const dynamic = 'force-dynamic';

/**
 * Ask the agent for an object by name: {"label": "gray water bottle"}.
 *
 * The camera is one way to discover an object; this is the other. The import
 * runs on a background thread, so this only waits for the flip to IMPORTING.
 */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const result = await backendJson<Record<string, unknown>>(
    '/api/import/request',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    8000
  );

  if (!result) {
    return NextResponse.json(
      { error: 'backend offline — start it with: python web/server.py --twin --camera' },
      { status: 503 }
    );
  }
  return NextResponse.json(result);
}
