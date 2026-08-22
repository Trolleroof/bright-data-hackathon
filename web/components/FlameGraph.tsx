'use client';

import React from 'react';
import { TraceTree, SpanNode } from '@/lib/types';
import { cn, formatDuration, getSpanTheme } from '@/lib/utils';

interface FlameGraphProps {
  trace: TraceTree;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
}

export const FlameGraph: React.FC<FlameGraphProps> = ({
  trace,
  selectedSpanId,
  onSelectSpan,
}) => {
  const rootSpan = trace.root_spans[0] || trace.flat_spans[0];
  const children = trace.flat_spans.filter((s) => s.span_id !== rootSpan?.span_id);

  return (
    <div className="flex flex-1 flex-col overflow-y-auto p-6 bg-obsidian-950">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="font-display text-sm font-bold tracking-wider text-slate-200">
            FLAME HIERARCHY STACK
          </h3>
          <p className="text-xs text-slate-400">
            Visual hierarchy of root orchestration and child pipelines
          </p>
        </div>
        <span className="font-mono text-xs font-bold text-hud-cyan">
          TOTAL: {formatDuration(trace.total_duration_ms)}
        </span>
      </div>

      {/* Layer 0: Root Span */}
      {rootSpan && (
        <div className="mb-2">
          <div
            onClick={() => onSelectSpan(rootSpan.span_id)}
            className={cn(
              'flex h-12 w-full cursor-pointer items-center justify-between rounded-lg border px-4 transition-all',
              rootSpan.span_id === selectedSpanId
                ? 'border-hud-cyan bg-hud-cyan/20 shadow-glow-cyan'
                : 'border-hud-cyan/40 bg-hud-cyan/10 hover:border-hud-cyan hover:bg-hud-cyan/15'
            )}
          >
            <div className="flex items-center gap-2">
              <span className="text-base">⚡</span>
              <span className="font-mono text-xs font-bold text-hud-cyan">
                {rootSpan.name} ({rootSpan.attributes['run.name'] || 'pipeline'})
              </span>
            </div>
            <span className="font-mono text-xs font-bold text-slate-200">
              {formatDuration(rootSpan.duration_ms)} (100%)
            </span>
          </div>
        </div>
      )}

      {/* Layer 1: Sequential Children Pipeline */}
      <div className="flex w-full gap-1.5 overflow-x-auto rounded-lg border border-obsidian-800 bg-obsidian-900/60 p-2">
        {children.map((span) => {
          const theme = getSpanTheme(span.name);
          const isSelected = span.span_id === selectedSpanId;
          const pct = Math.max(8, span.percent_width);

          return (
            <div
              key={span.span_id}
              onClick={() => onSelectSpan(span.span_id)}
              style={{ flex: `${pct} 0 0%` }}
              className={cn(
                'group flex h-28 cursor-pointer flex-col justify-between rounded-md border p-2.5 transition-all',
                theme.bg,
                theme.border,
                isSelected
                  ? 'ring-2 ring-hud-cyan shadow-glow-cyan'
                  : 'hover:brightness-125'
              )}
            >
              <div className="flex items-start justify-between gap-1">
                <span className="text-sm">{theme.icon}</span>
                <span className="rounded bg-obsidian-950/80 px-1 py-0.5 font-mono text-[9px] text-slate-300">
                  {span.percent_width.toFixed(1)}%
                </span>
              </div>

              <div>
                <div
                  className={cn(
                    'font-mono text-xs font-bold leading-tight truncate',
                    theme.color
                  )}
                >
                  {span.name}
                </div>
                <div className="mt-1 font-mono text-[10px] text-slate-300">
                  {formatDuration(span.duration_ms)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
