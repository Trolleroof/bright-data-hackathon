import { NextResponse } from 'next/server';
import { backendJson } from '@/lib/backend';

export const dynamic = 'force-dynamic';

/**
 * Start/stop the camera and the headless twin from the UI.
 *
 * Opening a webcam or booting MuJoCo can take a second or two, so this gets a
 * longer timeout than the polling routes.
 */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}));
  const result = await backendJson<Record<string, unknown>>(
    '/api/live/control',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    12000
  );

  if (!result) {
    return NextResponse.json(
      {
        error:
          'backend offline — start it with: python web/server.py --twin --camera',
      },
      { status: 503 }
    );
  }
  return NextResponse.json(result);
}
