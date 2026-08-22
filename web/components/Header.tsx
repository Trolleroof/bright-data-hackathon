'use client';

import { Loader2, Play, RefreshCw, Trash2 } from 'lucide-react';
import { BackendStatus } from '@/lib/types';

interface HeaderProps {
  status: BackendStatus | null;
  isTriggering: boolean;
  isProgramRunning: boolean;
  onRunA: () => void;
  onRunB: () => void;
  onRefresh: () => void;
  onClear: () => void;
  onRunProgram: () => void;
}

export function Header({
  status,
  isTriggering,
  isProgramRunning,
  onRunA,
  onRunB,
  onRefresh,
  onClear,
  onRunProgram,
}: HeaderProps) {
  const mode = status?.backend_online ? 'backend live' : 'demo mode';
  const port = status ? (status.port_ready ? 'Port ready' : 'Port keys missing') : 'Port demo';
  const bright = status ? (status.brightdata_ready ? 'Bright Data ready' : 'Bright Data keys missing') : 'Bright Data demo';

  return (
    <header className="border-b border-obsidian-800 bg-obsidian-900 px-5 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-white">Bidex</h1>
          <p className="mt-0.5 font-mono text-[11px] text-slate-500">
            {mode} · {port} · {bright}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            disabled={isProgramRunning}
            onClick={onRunProgram}
            className="flex items-center gap-1.5 rounded-md bg-emerald-400 px-3 py-2 text-xs font-semibold text-obsidian-950 disabled:opacity-50"
          >
            {isProgramRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-current" />}
            {isProgramRunning ? 'Running…' : 'Run checks'}
          </button>
          <button
            disabled={isTriggering}
            onClick={onRunA}
            className="flex items-center gap-1.5 rounded-md border border-sky-400/50 px-3 py-2 text-xs font-semibold text-sky-200 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" /> Run A
          </button>
          <button
            disabled={isTriggering}
            onClick={onRunB}
            className="flex items-center gap-1.5 rounded-md border border-amber-400/60 px-3 py-2 text-xs font-semibold text-amber-200 disabled:opacity-50"
          >
            <Play className="h-3.5 w-3.5" /> Run B
          </button>
          <button onClick={onRefresh} className="p-2 text-slate-400 hover:text-white" aria-label="Refresh">
            <RefreshCw className="h-4 w-4" />
          </button>
          <button onClick={onClear} className="p-2 text-slate-500 hover:text-rose-300" aria-label="Clear traces">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
