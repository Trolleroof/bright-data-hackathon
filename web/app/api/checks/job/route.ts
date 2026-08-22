import { proxyBackend } from '@/lib/backend';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get('id') ?? '';
  const since = searchParams.get('since') ?? '-1';
  return proxyBackend(
    `/api/checks/job?id=${encodeURIComponent(id)}&since=${encodeURIComponent(since)}`
  );
}
