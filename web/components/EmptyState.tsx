'use client';

import { Play } from 'lucide-react';

export function EmptyState({ onRunA, onRunB }: { onRunA: () => void; onRunB: () => void }) {
  return <div className="flex flex-1 flex-col items-center justify-center p-8 text-center"><p className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">No trace selected</p><h2 className="mt-2 text-xl font-semibold text-white">Start a run or choose one from the log.</h2><p className="mt-2 max-w-md text-sm text-slate-400">Camera and twin can stay open above while the trace is recorded.</p><div className="mt-5 flex gap-2"><button onClick={onRunA} className="flex items-center gap-2 rounded-md bg-emerald-400 px-3 py-2 text-sm font-semibold text-slate-950"><Play className="h-4 w-4 fill-current" /> Run A</button><button onClick={onRunB} className="rounded-md border border-obsidian-700 px-3 py-2 text-sm font-semibold text-white">Run B</button></div></div>;
}
