'use client';

import React from 'react';
import {
  Play,
  RotateCw,
  Trash2,
  Radio,
  Zap,
  Activity,
  Layers,
  Sparkles,
} from 'lucide-react';
import { BackendStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

interface HeaderProps {
  status: BackendStatus | null;
  totalTraces: number;
  totalSpans: number;
  latestOp: string;
  isTriggering: boolean;
  onRunA: () => void;
  onRunB: () => void;
  onRefresh: () => void;
  onClear: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  totalTraces,
  totalSpans,
  latestOp,
  isTriggering,
  onRunA,
  onRunB,
  onRefresh,
  onClear,
}) => {
  return (
    <header className="relative z-10 flex flex-wrap items-center justify-between gap-4 border-b border-obsidian-800 bg-obsidian-900/90 px-5 py-3 backdrop-blur-md">
      {/* Brand & Live Badges */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          {/* Radar Emitter */}
          <div className="relative flex h-10 w-10 items-center justify-center rounded-lg border border-hud-cyan/30 bg-obsidian-850">
            <span className="h-2.5 w-2.5 rounded-full bg-hud-cyan shadow-glow-cyan" />
            <span className="absolute h-2.5 w-2.5 rounded-full bg-hud-cyan animate-radar-pulse" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-[10px] font-bold tracking-[0.25em] text-hud-cyan">
                AVIONICS FLIGHT RECORDER
              </span>
              <span className="rounded bg-hud-cyan/10 px-1.5 py-0.5 text-[9px] font-bold text-hud-cyan">
                v2.4
              </span>
            </div>
            <h1 className="font-display text-xl font-black tracking-wider text-slate-100">
              BIDEX <span className="text-hud-cyan">HUD</span>
            </h1>
          </div>
        </div>

        {/* Telemetry Status Pills */}
        <div className="hidden items-center gap-2.5 lg:flex">
          {/* Live Stream Pill */}
          <div className="flex items-center gap-2 rounded-full border border-hud-cyan/30 bg-obsidian-850/80 px-3 py-1 text-xs text-slate-300">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-hud-cyan opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-hud-cyan"></span>
            </span>
            <span className="font-mono text-[11px] font-medium tracking-wider text-slate-200">
              LIVE TELEMETRY
            </span>
          </div>

          {/* Zero Downtime Pill */}
          <div
            className="flex items-center gap-1.5 rounded-full border border-hud-emerald/40 bg-hud-emerald/10 px-3 py-1 text-xs text-emerald-300 shadow-glow-emerald"
            title="MuJoCo Twin runs continuously without pause"
          >
            <Zap className="h-3.5 w-3.5 text-hud-emerald" />
            <span className="font-mono text-[11px] font-bold tracking-wider">
              ZERO DOWNTIME : ACTIVE
            </span>
          </div>

          {/* SigNoz Pill */}
          <div className="flex items-center gap-1.5 rounded-full border border-obsidian-750 bg-obsidian-850 px-3 py-1 text-xs text-slate-300">
            <Radio className="h-3.5 w-3.5 text-hud-violet" />
            <span className="font-mono text-[11px] text-slate-300">
              SIGNOZ :{' '}
              <strong className="text-slate-100">
                {status?.signoz_ready ? 'OTLP READY' : 'LOCAL ENGINE'}
              </strong>
            </span>
          </div>
        </div>
      </div>

      {/* Center Telemetry Stats */}
      <div className="hidden items-center gap-6 xl:flex">
        <div className="flex items-center gap-3 rounded-lg border border-obsidian-800 bg-obsidian-850/60 px-3.5 py-1.5">
          <Layers className="h-4 w-4 text-slate-400" />
          <div className="flex flex-col">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Flight Traces
            </span>
            <span className="font-mono text-sm font-bold text-slate-100">
              {totalTraces}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-obsidian-800 bg-obsidian-850/60 px-3.5 py-1.5">
          <Activity className="h-4 w-4 text-slate-400" />
          <div className="flex flex-col">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Raw Spans
            </span>
            <span className="font-mono text-sm font-bold text-slate-100">
              {totalSpans}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3 rounded-lg border border-hud-cyan/20 bg-hud-cyan/5 px-3.5 py-1.5">
          <Sparkles className="h-4 w-4 text-hud-cyan" />
          <div className="flex flex-col">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-hud-cyan">
              Latest Op
            </span>
            <span className="font-mono text-sm font-bold uppercase text-hud-cyan">
              {latestOp || 'IDLE'}
            </span>
          </div>
        </div>
      </div>

      {/* Action Controls */}
      <div className="flex items-center gap-2.5">
        {/* Run A Button */}
        <button
          onClick={onRunA}
          disabled={isTriggering}
          className={cn(
            'group relative flex items-center gap-2.5 overflow-hidden rounded-lg border border-hud-cyan/40 bg-hud-cyan/15 px-3.5 py-1.5 text-xs font-semibold text-hud-cyan transition-all hover:border-hud-cyan hover:bg-hud-cyan/25 hover:shadow-glow-cyan active:scale-95 disabled:opacity-50'
          )}
          title="Simulate Run A (goto) physical prompt trace (Key: A)"
        >
          <Play className="h-3.5 w-3.5 fill-hud-cyan transition-transform group-hover:scale-110" />
          <div className="flex flex-col text-left">
            <span className="font-display text-xs font-bold leading-none">
              RUN A
            </span>
            <span className="font-mono text-[9px] text-hud-cyan/80">goto</span>
          </div>
          <kbd className="ml-1 rounded border border-hud-cyan/40 bg-obsidian-950/80 px-1.5 py-0.5 font-mono text-[9px] text-hud-cyan">
            A
          </kbd>
        </button>

        {/* Run B Button */}
        <button
          onClick={onRunB}
          disabled={isTriggering}
          className={cn(
            'group relative flex items-center gap-2.5 overflow-hidden rounded-lg border border-hud-violet/50 bg-hud-violet/15 px-3.5 py-1.5 text-xs font-semibold text-purple-300 transition-all hover:border-hud-violet hover:bg-hud-violet/25 hover:shadow-glow-violet active:scale-95 disabled:opacity-50'
          )}
          title="Simulate Run B (compose goto + avoid bottle) trace with Bright Data enrichment (Key: B)"
        >
          <Play className="h-3.5 w-3.5 fill-purple-400 text-purple-400 transition-transform group-hover:scale-110" />
          <div className="flex flex-col text-left">
            <span className="font-display text-xs font-bold leading-none text-purple-200">
              RUN B
            </span>
            <span className="font-mono text-[9px] text-purple-300">
              compose + avoid
            </span>
          </div>
          <kbd className="ml-1 rounded border border-purple-500/40 bg-obsidian-950/80 px-1.5 py-0.5 font-mono text-[9px] text-purple-300">
            B
          </kbd>
        </button>

        <div className="mx-1 h-6 w-px bg-obsidian-750" />

        {/* Refresh Button */}
        <button
          onClick={onRefresh}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-obsidian-750 bg-obsidian-850 text-slate-300 transition-all hover:border-obsidian-700 hover:bg-obsidian-800 hover:text-slate-100"
          title="Refresh trace telemetry (Key: R)"
        >
          <RotateCw className="h-4 w-4" />
        </button>

        {/* Clear Button */}
        <button
          onClick={onClear}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-obsidian-750 bg-obsidian-850 text-rose-400 transition-all hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-300"
          title="Clear recorded spans (Key: C)"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
};
