'use client';

import React from 'react';
import { Play, Activity, Zap, Radio } from 'lucide-react';

interface EmptyStateProps {
  onRunA: () => void;
  onRunB: () => void;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ onRunA, onRunB }) => {
  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-obsidian-950 p-8 text-center">
      {/* Reticle Radar Target */}
      <div className="relative mb-6 flex h-28 w-28 items-center justify-center">
        {/* Outer Ring */}
        <div className="absolute inset-0 rounded-full border border-dashed border-hud-cyan/40 animate-[spin_20s_linear_infinite]" />
        {/* Middle Ring */}
        <div className="absolute inset-3 rounded-full border border-hud-cyan/60" />
        {/* Radar Crosshairs */}
        <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-hud-cyan/40" />
        <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-hud-cyan/40" />
        {/* Center Target */}
        <div className="h-4 w-4 rounded-full bg-hud-cyan shadow-glow-cyan animate-pulse" />
      </div>

      <div className="max-w-md">
        <span className="font-display text-xs font-bold tracking-widest text-hud-cyan">
          AVIONICS TELEMETRY STANDBY
        </span>
        <h2 className="mt-1 font-display text-2xl font-black text-slate-100">
          NO FLIGHT TRACE SELECTED
        </h2>
        <p className="mt-2 text-xs text-slate-400">
          Trigger a zero-downtime physical prompt demo run or select an existing flight log from the telemetry sidebar.
        </p>

        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            onClick={onRunA}
            className="flex items-center gap-2 rounded-lg border border-hud-cyan/50 bg-hud-cyan/15 px-4 py-2 text-xs font-bold text-hud-cyan transition-all hover:bg-hud-cyan/25 hover:shadow-glow-cyan"
          >
            <Play className="h-3.5 w-3.5 fill-hud-cyan" />
            Launch Run A (goto)
          </button>

          <button
            onClick={onRunB}
            className="flex items-center gap-2 rounded-lg border border-hud-violet/50 bg-hud-violet/15 px-4 py-2 text-xs font-bold text-purple-300 transition-all hover:bg-hud-violet/25 hover:shadow-glow-violet"
          >
            <Play className="h-3.5 w-3.5 fill-purple-400 text-purple-400" />
            Launch Run B (compose + avoid)
          </button>
        </div>
      </div>
    </div>
  );
};
