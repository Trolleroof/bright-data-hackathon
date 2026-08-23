'use client';

import { useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import { ObjectImportState } from '@/lib/types';

interface Props {
  state: ObjectImportState | undefined;
  onToast: (message: string) => void;
  onRefresh: () => void;
}

const EXAMPLES = ['gray water bottle', 'white mug', 'cardboard box'];

/**
 * Ask the agent for an object by name.
 *
 * The camera can only report that *something* is there. Typing the name is the
 * other way in, and it is the one that works on a stage: no lighting, no
 * bounding box, no waiting for a blob to hold still. Bright Data reads MuJoCo's
 * model text for the name, the agent sizes a primitive from it, and the twin
 * hot-swaps it in — then the running skill gets an `avoid` step so the arm
 * routes around what just appeared.
 */
export function ObjectRequest({ state, onToast, onRefresh }: Props) {
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const importing = state?.status === 'IMPORTING';

  const submit = async (requested: string) => {
    const name = requested.trim();
    if (!name || busy || importing) return;
    setBusy(true);
    try {
      const response = await fetch('/api/import/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: name }),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || 'Object request failed');
      onToast(`Asking the agent for ${name}…`);
      setLabel('');
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Object request failed');
    } finally {
      setBusy(false);
      onRefresh();
    }
  };

  return <div className="mb-4 rounded-md border border-obsidian-700 bg-obsidian-900/40 p-4">
    <div className="flex items-center gap-2">
      <Sparkles className="h-4 w-4 text-sky-300" />
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-300">Put an object in the twin</p>
    </div>
    <p className="mt-1.5 text-xs text-slate-400">
      Name it and the agent reads MuJoCo model text for it via Bright Data, sizes the
      geometry, and drops it on the table. The arm routes around whatever lands.
    </p>

    <form
      className="mt-3 flex flex-wrap items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        void submit(label);
      }}
    >
      <input
        value={label}
        onChange={(event) => setLabel(event.target.value)}
        placeholder="gray water bottle"
        aria-label="Object to import"
        disabled={busy || importing}
        className="min-w-0 flex-1 rounded-md border border-obsidian-700 bg-obsidian-950 px-3 py-2 font-mono text-xs text-slate-100 placeholder:text-slate-600 focus:border-sky-500/60 focus:outline-none disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={busy || importing || !label.trim()}
        className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50"
      >
        {busy || importing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
        {importing ? 'Importing…' : 'Add to twin'}
      </button>
    </form>

    <div className="mt-2 flex flex-wrap items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-wider text-slate-600">try</span>
      {EXAMPLES.map((example) => <button
        key={example}
        type="button"
        disabled={busy || importing}
        onClick={() => void submit(example)}
        className="rounded-sm border border-obsidian-700 px-2 py-1 font-mono text-[10px] text-slate-400 hover:text-white disabled:opacity-50"
      >{example}</button>)}
    </div>
  </div>;
}
