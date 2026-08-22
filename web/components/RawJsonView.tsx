'use client';

import React, { useState } from 'react';
import { Copy, Check, FileJson } from 'lucide-react';
import { TraceTree } from '@/lib/types';

interface RawJsonViewProps {
  trace: TraceTree;
}

export const RawJsonView: React.FC<RawJsonViewProps> = ({ trace }) => {
  const [copied, setCopied] = useState(false);

  const jsonString = JSON.stringify(trace, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(jsonString);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex flex-1 flex-col overflow-hidden bg-obsidian-950 p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileJson className="h-4 w-4 text-hud-violet" />
          <span className="font-display text-xs font-bold text-slate-200">
            RAW TRACE JSON RECURSIVE TREE
          </span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-lg border border-obsidian-750 bg-obsidian-850 px-3 py-1.5 font-mono text-xs text-slate-200 hover:border-hud-cyan hover:text-hud-cyan"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-hud-emerald" />
              <span>COPIED</span>
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" />
              <span>COPY JSON</span>
            </>
          )}
        </button>
      </div>

      <pre className="flex-1 overflow-auto rounded-lg border border-obsidian-800 bg-obsidian-900/90 p-4 font-mono text-xs text-cyan-300">
        <code>{jsonString}</code>
      </pre>
    </div>
  );
};
