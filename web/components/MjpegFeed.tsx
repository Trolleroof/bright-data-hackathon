'use client';

import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, VideoOff } from 'lucide-react';
import { cn } from '@/lib/utils';

interface MjpegFeedProps {
  /** Proxy route serving multipart/x-mixed-replace, e.g. /api/sim/stream */
  src: string;
  label: string;
  /** Whether the backend says this feed is producing frames. */
  active: boolean;
  /** Shown instead of the feed when it is not active. */
  idleMessage: string;
  /** Backend-reported reason the feed is down, if any. */
  error?: string | null;
  /** Bump to force the <img> to drop and re-open the stream. */
  reconnectKey?: number;
  className?: string;
}

/**
 * A live MJPEG viewport.
 *
 * The browser decodes multipart/x-mixed-replace natively in an <img>, so this
 * needs no video player, no WebSocket and no polling loop — but it also gives
 * no ready-state events beyond load/error, hence the explicit status overlay.
 */
export const MjpegFeed: React.FC<MjpegFeedProps> = ({
  src,
  label,
  active,
  idleMessage,
  error,
  reconnectKey = 0,
  className,
}) => {
  const [phase, setPhase] = useState<'connecting' | 'streaming' | 'failed'>(
    'connecting'
  );
  const [nonce, setNonce] = useState(() => Date.now());
  const wasActive = useRef(active);

  // Re-open the stream whenever the feed comes back up or is reset upstream.
  useEffect(() => {
    if (active && !wasActive.current) {
      setNonce(Date.now());
      setPhase('connecting');
    }
    wasActive.current = active;
  }, [active]);

  useEffect(() => {
    if (reconnectKey > 0) {
      setNonce(Date.now());
      setPhase('connecting');
    }
  }, [reconnectKey]);

  const streamUrl = `${src}?t=${nonce}`;

  return (
    <div
      className={cn(
        'relative flex items-center justify-center overflow-hidden rounded-lg border border-obsidian-800 bg-black',
        className
      )}
    >
      {active ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={streamUrl}
            src={streamUrl}
            alt={label}
            className="h-full w-full object-contain"
            onLoad={() => setPhase('streaming')}
            onError={() => setPhase('failed')}
          />

          {phase === 'connecting' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-obsidian-950/80 font-mono text-xs text-slate-400">
              <Loader2 className="h-5 w-5 animate-spin text-hud-cyan" />
              <span>opening {label} feed…</span>
            </div>
          )}

          {phase === 'failed' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-obsidian-950/90 px-6 text-center font-mono text-xs text-hud-ruby">
              <AlertTriangle className="h-5 w-5" />
              <span>{label} stream dropped</span>
              <button
                type="button"
                onClick={() => {
                  setNonce(Date.now());
                  setPhase('connecting');
                }}
                className="mt-1 rounded border border-hud-ruby/40 px-2 py-1 text-[10px] uppercase tracking-widest text-hud-ruby hover:bg-hud-ruby/10"
              >
                reconnect
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center gap-2 px-8 py-16 text-center">
          <VideoOff className="h-7 w-7 text-obsidian-600" />
          <span className="font-mono text-xs text-slate-500">{idleMessage}</span>
          {error && (
            <span className="max-w-sm font-mono text-[11px] leading-relaxed text-hud-amber">
              {error}
            </span>
          )}
        </div>
      )}

      {/* Corner brackets: this is a viewport, not a screenshot. */}
      <span className="pointer-events-none absolute left-2 top-2 h-4 w-4 border-l border-t border-hud-cyan/40" />
      <span className="pointer-events-none absolute right-2 top-2 h-4 w-4 border-r border-t border-hud-cyan/40" />
      <span className="pointer-events-none absolute bottom-2 left-2 h-4 w-4 border-b border-l border-hud-cyan/40" />
      <span className="pointer-events-none absolute bottom-2 right-2 h-4 w-4 border-b border-r border-hud-cyan/40" />

      <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded bg-obsidian-950/70 px-2 py-1">
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            active && phase === 'streaming'
              ? 'bg-hud-ruby animate-pulse'
              : 'bg-obsidian-600'
          )}
        />
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-300">
          {label}
        </span>
      </div>
    </div>
  );
};
