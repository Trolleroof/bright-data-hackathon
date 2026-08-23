'use client';

import { useState } from 'react';
import { AlertTriangle, Box, CheckCircle2, Download, Loader2, X } from 'lucide-react';
import { ObjectImportState } from '@/lib/types';

interface Props {
  state: ObjectImportState;
  onToast: (message: string) => void;
  onRefresh: () => void;
}

const HEADLINE: Record<string, string> = {
  IDLE: 'Scanning for an object',
  AWAITING: 'New object detected',
  IMPORTING: 'Importing geometry',
  READY: 'Geometry loaded into the twin',
  FAILED: 'Import failed',
};

/** Where the numbers in the scene actually came from, in the operator's words. */
const AGENT_LABEL: Record<string, string> = {
  nim: 'NVIDIA NIM read the MJCF',
  offline_reader: 'offline MJCF reader',
  port_cache: 'reused from the Port catalog',
};

/**
 * The camera found a bounding box the twin has no geometry for. Nothing is
 * fetched until the operator says so — searching MuJoCo's model ecosystem
 * costs Bright Data quota and a few seconds, so it is a question, not a side
 * effect.
 *
 * Nothing binary is downloaded: Bright Data reads the *text* of real MJCF
 * models for similar objects, and the agent turns that text into one sized
 * MuJoCo primitive. The banner names the source and links the model it copied,
 * because a number with no provenance is the thing worth distrusting here.
 */
export function ImportPrompt({ state, onToast, onRefresh }: Props) {
  const [busy, setBusy] = useState(false);
  const status = state.status;

  // Nothing is shown unless the operator started a scan or one produced a
  // result. An unasked-for "import this?" banner over a live demo is worse
  // than no feature at all.
  const scanning = state.scanning ?? false;
  if (!['IMPORTING', 'READY', 'FAILED'].includes(status) && !(scanning && ['IDLE', 'AWAITING'].includes(status))) {
    return null;
  }

  const decide = async (decision: 'import' | 'dismiss' | 'reset' | 'stop') => {
    setBusy(true);
    try {
      const response = await fetch('/api/import/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Import request failed');
      if (decision === 'import') onToast(`Importing ${state.label}…`);
      if (decision === 'dismiss') onToast(`Skipped ${state.label}`);
      if (decision === 'stop') onToast('Stopped scanning');
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Import request failed');
    } finally {
      setBusy(false);
      onRefresh();
    }
  };

  const tone =
    status === 'IDLE' ? 'border-obsidian-700 bg-obsidian-900/40'
    : status === 'FAILED' ? 'border-red-500/40 bg-red-500/10'
    : status === 'READY' ? 'border-emerald-500/40 bg-emerald-500/10'
    : 'border-amber-500/40 bg-amber-500/10';

  const icon =
    status === 'IDLE' ? <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
    : status === 'IMPORTING' ? <Loader2 className="h-4 w-4 animate-spin text-amber-300" />
    : status === 'READY' ? <CheckCircle2 className="h-4 w-4 text-emerald-300" />
    : status === 'FAILED' ? <AlertTriangle className="h-4 w-4 text-red-300" />
    : <Box className="h-4 w-4 text-amber-300" />;

  return <div className={`mb-4 rounded-md border p-4 ${tone}`} role="status" aria-live="polite">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          {icon}
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-300">{HEADLINE[status]}</p>
          {state.hardcoded && <span className="rounded-sm bg-obsidian-900/70 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-slate-400">hardcoded stub</span>}
        </div>
        <p className="mt-1.5 text-sm font-semibold text-white">
          {status === 'IDLE' ? 'Point the camera at the object' : state.label || 'unknown object'}
          {state.confidence > 0 && <span className="ml-2 font-mono text-[11px] font-normal text-slate-400">{Math.round(state.confidence * 100)}% fill</span>}
        </p>
        <p className="mt-1 max-w-2xl text-xs text-slate-300">
          {status === 'AWAITING'
            ? <>Import this object into the simulation via Bright Data? {state.detail}</>
            : state.detail}
        </p>
        {status === 'FAILED' && state.error && <p className="mt-1 font-mono text-[11px] text-red-300">{state.error}</p>}
        {status === 'READY' && <>
          <p className="mt-1 font-mono text-[11px] text-slate-400">
            rung {state.rung} · {AGENT_LABEL[state.agent ?? ''] ?? state.source}
            {state.agent_model && ` (${state.agent_model})`}
            {state.elapsed_ms != null && ` · ${(state.elapsed_ms / 1000).toFixed(1)}s`}
            {state.port_entity && ` · port ${state.port_entity}`}
          </p>
          {state.reasoning && <p className="mt-1 max-w-2xl text-[11px] italic text-slate-400">{state.reasoning}</p>}
          {state.mujoco_url && <a
            href={state.mujoco_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-block max-w-2xl truncate font-mono text-[11px] text-sky-300 underline decoration-dotted"
          >{state.mujoco_url}</a>}
        </>}
        {state.bbox.length === 4 && <p className="mt-1 font-mono text-[11px] text-slate-500">bbox {state.bbox.join(', ')} px</p>}
      </div>

      <div className="flex items-center gap-2">
        {status === 'IDLE' && <button
          disabled={busy}
          onClick={() => decide('stop')}
          className="rounded-md border border-obsidian-700 px-3 py-2 text-xs font-semibold text-slate-200 disabled:opacity-50"
        >Stop scanning</button>}
        {status === 'AWAITING' && <>
          <button
            disabled={busy}
            onClick={() => decide('import')}
            className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            Import from MuJoCo text
          </button>
          <button
            disabled={busy}
            onClick={() => decide('dismiss')}
            className="rounded-md border border-obsidian-700 px-3 py-2 text-xs font-semibold text-slate-200 disabled:opacity-50"
          >
            Not now
          </button>
        </>}
        {(status === 'READY' || status === 'FAILED') && <button
          disabled={busy}
          onClick={() => decide('reset')}
          className="p-2 text-slate-400 hover:text-white disabled:opacity-50"
          aria-label="Dismiss import notice"
        ><X className="h-4 w-4" /></button>}
      </div>
    </div>
  </div>;
}
