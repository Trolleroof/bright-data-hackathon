import { proxyBackend } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const body = await req.text();
  return proxyBackend('/api/checks/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body || '{}',
  });
}
