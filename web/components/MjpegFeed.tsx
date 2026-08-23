'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, RotateCw, VideoOff } from 'lucide-react';
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

/** Backoff between automatic redials, capped so a dead backend stops hammering. */
const RETRY_MS = [500, 1000, 2000, 4000, 8000];

export function MjpegFeed({ src, label, active, idleMessage, error, reconnectKey = 0, className }: Props) {
  const [nonce, setNonce] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const retryTimer = useRef<number | undefined>(undefined);

  // A pending backoff must not outlive the panel, or it redials a closed feed.
  useEffect(() => () => window.clearTimeout(retryTimer.current), []);

  const redial = useCallback(() => {
    setLoaded(false);
    setNonce(Date.now());
  }, []);

  // A fresh request whenever the feed is (re)opened or the operator acts on it.
  useEffect(() => {
    if (!active) { setLoaded(false); setAttempt(0); return; }
    setAttempt(0);
    redial();
  }, [active, reconnectKey, redial]);

  // The backend closes a dead stream; retry only on a real image error instead
  // of guessing from MJPEG load events, which browsers do not emit per frame.
  const onError = useCallback(() => {
    setLoaded(false);
    const delay = RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];
    window.clearTimeout(retryTimer.current);
    retryTimer.current = window.setTimeout(() => { setAttempt((n) => n + 1); redial(); }, delay);
  }, [attempt, redial]);

  const onLoad = useCallback(() => {
    setLoaded(true);
    setAttempt(0);
  }, []);

  const retrying = active && !loaded && attempt > 0;

  return <div className={cn('relative overflow-hidden rounded-md border border-obsidian-800 bg-black', className)}>
    <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between bg-black/60 px-3 py-2 text-xs backdrop-blur-sm">
      <span className="font-medium text-slate-200">{label}</span>
      <div className="flex items-center gap-2">
        {active && <button onClick={() => { setAttempt(0); redial(); }} className="text-slate-500 transition-colors hover:text-white" aria-label={`Reconnect ${label} feed`}><RotateCw className="h-3 w-3" /></button>}
        <span className={`h-1.5 w-1.5 rounded-full ${active && loaded ? 'bg-emerald-400' : retrying ? 'bg-amber-400' : 'bg-slate-600'}`} />
      </div>
    </div>
    {active ? <>
      {/* Wait for the first redial to stamp a nonce: rendering at t=0 would open
          a stream connection that the very next effect immediately replaces. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {nonce > 0 && <img key={nonce} src={`${src}?t=${nonce}`} alt={`${label} live feed`} className="h-full w-full object-contain" onLoad={onLoad} onError={onError} />}
      {!loaded && <div className="absolute inset-0 flex items-center justify-center gap-2 text-xs text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        {retrying ? `Reconnecting to ${label.toLowerCase()}… (${attempt})` : 'Opening feed…'}
      </div>}
    </> : <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-xs text-slate-600"><VideoOff className="h-6 w-6" /><span>{error || idleMessage}</span></div>}
  </div>;
}
