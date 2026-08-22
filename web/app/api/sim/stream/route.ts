import { proxyMjpeg } from '@/lib/mjpeg-proxy';

export const dynamic = 'force-dynamic';
export const fetchCache = 'force-no-store';
export const runtime = 'nodejs';
export const maxDuration = 3600;

export async function GET() {
  return proxyMjpeg('/api/sim/stream');
}
