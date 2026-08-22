'use client';

import { useEffect, useState } from 'react';
import { Loader2, VideoOff } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  src: string;
  label: string;
  active: boolean;
  idleMessage: string;
  error?: string | null;
  reconnectKey?: number;
  className?: string;
}

export function MjpegFeed({ src, label, active, idleMessage, error, reconnectKey = 0, className }: Props) {
  const [nonce, setNonce] = useState(Date.now());
  const [loaded, setLoaded] = useState(false);
  useEffect(() => { if (active) { setNonce(Date.now()); setLoaded(false); } }, [active, reconnectKey]);

  return <div className={cn('relative overflow-hidden rounded-md border border-obsidian-800 bg-black', className)}>
    <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between bg-black/60 px-3 py-2 text-xs backdrop-blur-sm"><span className="font-medium text-slate-200">{label}</span><span className={`h-1.5 w-1.5 rounded-full ${active && loaded ? 'bg-emerald-400' : 'bg-slate-600'}`} /></div>
    {active ? <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${src}?t=${nonce}`} alt={`${label} live feed`} className="h-full w-full object-contain" onLoad={() => setLoaded(true)} onError={() => setLoaded(false)} />
      {!loaded && <div className="absolute inset-0 flex items-center justify-center gap-2 text-xs text-slate-500"><Loader2 className="h-4 w-4 animate-spin" /> Opening feed…</div>}
    </> : <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-xs text-slate-600"><VideoOff className="h-6 w-6" /><span>{error || idleMessage}</span></div>}
  </div>;
}
