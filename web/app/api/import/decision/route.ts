import { NextResponse } from 'next/server';
import { backendJson } from '@/lib/backend';

export const dynamic = 'force-dynamic';

/**
 * Answer the object-import prompt: {"decision": "import" | "dismiss" | "reset"}.
 *
 * "import" kicks off a Bright Data mesh search (or, for the hardcoded grey
 * water bottle, the primitive stub) on a background thread, so this only waits
 * for the state flip to IMPORTING — the UI polls /api/live for the outcome.
 */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const result = await backendJson<Record<string, unknown>>(
    '/api/import/decision',
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
