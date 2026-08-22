'use client';

import React, { useState, useMemo } from 'react';
import {
  Search,
  Clock,
  Zap,
  Globe,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  SlidersHorizontal,
} from 'lucide-react';
import { TraceTree, FilterType } from '@/lib/types';
import { cn, formatDuration, formatTimestamp } from '@/lib/utils';

interface SidebarProps {
  traces: TraceTree[];
  selectedTraceId: string | null;
  onSelectTrace: (traceId: string) => void;
  filter: FilterType;
  onFilterChange: (filter: FilterType) => void;
  isStreaming: boolean;
  utcTime: string;
}

export const Sidebar: React.FC<SidebarProps> = ({
  traces,
  selectedTraceId,
  onSelectTrace,
  filter,
  onFilterChange,
  isStreaming,
  utcTime,
}) => {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredTraces = useMemo(() => {
    return traces.filter((trace) => {
      // Run type filter
      const name = (trace.run_name || trace.root_name || '').toLowerCase();
      if (filter === 'run_a') {
        const matchesA = name.includes('run a') || name.includes('goto');
        if (!matchesA) return false;
      } else if (filter === 'run_b') {
        const matchesB =
          name.includes('run b') ||
          name.includes('avoid') ||
          name.includes('compose');
        if (!matchesB) return false;
      }

      // Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const idMatch = trace.trace_id.toLowerCase().includes(q);
        const nameMatch = name.includes(q);
        if (!idMatch && !nameMatch) return false;
      }

      return true;
    });
  }, [traces, filter, searchQuery]);

  return (
    <aside className="flex h-full w-80 flex-shrink-0 flex-col border-r border-obsidian-800 bg-obsidian-900/95">
      {/* Sidebar Header */}
      <div className="border-b border-obsidian-800 p-3.5">
        <div className="mb-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-display text-xs font-bold tracking-wider text-slate-300">
              FLIGHT LOGS
            </span>
            <span className="rounded bg-obsidian-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-hud-cyan">
              {filteredTraces.length} / {traces.length}
            </span>
          </div>
          {isStreaming && (
            <span className="flex items-center gap-1 font-mono text-[10px] text-hud-cyan">
              <span className="h-1.5 w-1.5 animate-ping rounded-full bg-hud-cyan" />
              INGESTING
            </span>
          )}
        </div>

        {/* Filter Pills */}
        <div className="grid grid-cols-3 gap-1 rounded-lg bg-obsidian-850 p-1">
          <button
            onClick={() => onFilterChange('all')}
            className={cn(
              'rounded py-1 text-center font-display text-[11px] font-bold tracking-wider transition-all',
              filter === 'all'
                ? 'bg-obsidian-750 text-slate-100 shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            ALL
          </button>
          <button
            onClick={() => onFilterChange('run_a')}
            className={cn(
              'rounded py-1 text-center font-display text-[11px] font-bold tracking-wider transition-all',
              filter === 'run_a'
                ? 'bg-hud-cyan/20 text-hud-cyan shadow-sm'
                : 'text-slate-400 hover:text-cyan-400'
            )}
          >
            RUN A
          </button>
          <button
            onClick={() => onFilterChange('run_b')}
            className={cn(
              'rounded py-1 text-center font-display text-[11px] font-bold tracking-wider transition-all',
              filter === 'run_b'
                ? 'bg-hud-violet/20 text-purple-300 shadow-sm'
                : 'text-slate-400 hover:text-purple-300'
            )}
          >
            RUN B
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative mt-2">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search trace ID or name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full rounded-md border border-obsidian-750 bg-obsidian-850 py-1.5 pl-8 pr-2.5 font-mono text-xs text-slate-200 placeholder-slate-500 focus:border-hud-cyan/50 focus:outline-none focus:ring-1 focus:ring-hud-cyan/40"
          />
        </div>
      </div>

      {/* Trace Cards Scrollable List */}
      <div className="flex-1 overflow-y-auto p-2.5 space-y-2">
        {filteredTraces.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-2 rounded-full border border-obsidian-750 bg-obsidian-850 p-3 text-slate-500">
              <SlidersHorizontal className="h-5 w-5" />
            </div>
            <span className="font-display text-xs font-bold text-slate-300">
              NO MATCHING TRACES
            </span>
            <span className="mt-1 text-[11px] text-slate-400">
              {traces.length === 0
                ? 'Trigger Run A or Run B above to start logging'
                : 'Try adjusting your search or filter'}
            </span>
          </div>
        ) : (
          filteredTraces.map((trace) => {
            const isSelected = trace.trace_id === selectedTraceId;
            const isRunB =
              (trace.run_name || '').toLowerCase().includes('run b') ||
              (trace.run_name || '').toLowerCase().includes('avoid');

            const hasPrompt = (trace.events || []).some(
              (e) => e.name === 'physical_prompt'
            );
            const hasRelease = (trace.events || []).some(
              (e) => e.name === 'release'
            );
            const hasObstacle = (trace.events || []).some(
              (e) => e.name === 'obstacle_detected'
            );
            const hasBrightData = (trace.flat_spans || []).some(
              (s) => s.name === 'scrape' && s.attributes?.sponsor === 'Bright Data' && s.attributes?.item_name
            );

            return (
              <div
                key={trace.trace_id}
                onClick={() => onSelectTrace(trace.trace_id)}
                className={cn(
                  'group relative cursor-pointer rounded-lg border p-3 transition-all',
                  isSelected
                    ? isRunB
                      ? 'border-hud-violet/60 bg-hud-violet/10 shadow-glow-violet'
                      : 'border-hud-cyan/60 bg-hud-cyan/10 shadow-glow-cyan'
                    : 'border-obsidian-800 bg-obsidian-850/60 hover:border-obsidian-700 hover:bg-obsidian-850'
                )}
              >
                {/* Header Row: Badge & Duration */}
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={cn(
                      'rounded px-2 py-0.5 font-display text-[10px] font-bold tracking-wider',
                      isRunB
                        ? 'border border-hud-violet/40 bg-hud-violet/20 text-purple-300'
                        : 'border border-hud-cyan/40 bg-hud-cyan/20 text-hud-cyan'
                    )}
                  >
                    {isRunB ? 'RUN B // COMPOSE' : 'RUN A // GOTO'}
                  </span>

                  <span className="font-mono text-xs font-bold text-slate-200">
                    {formatDuration(trace.total_duration_ms)}
                  </span>
                </div>

                {/* Trace Title */}
                <div className="mt-2 font-display text-xs font-semibold text-slate-100 group-hover:text-white line-clamp-1">
                  {trace.run_name || trace.root_name}
                </div>

                {/* Event Chips Row */}
                <div className="mt-2 flex flex-wrap items-center gap-1 text-[9px] font-mono">
                  {hasPrompt && (
                    <span className="flex items-center gap-0.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-400 border border-amber-500/30">
                      <Zap className="h-2.5 w-2.5" /> PROMPT
                    </span>
                  )}
                  {hasRelease && (
                    <span className="flex items-center gap-0.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-400 border border-emerald-500/30">
                      <CheckCircle2 className="h-2.5 w-2.5" /> RELEASE
                    </span>
                  )}
                  {hasObstacle && (
                    <span className="flex items-center gap-0.5 rounded bg-rose-500/15 px-1.5 py-0.5 text-rose-400 border border-rose-500/30">
                      <AlertCircle className="h-2.5 w-2.5" /> OBSTACLE
                    </span>
                  )}
                  {hasBrightData && (
                    <span className="flex items-center gap-0.5 rounded bg-purple-500/20 px-1.5 py-0.5 text-purple-300 border border-purple-500/40">
                      <Globe className="h-2.5 w-2.5" /> BRIGHT DATA
                    </span>
                  )}
                </div>

                {/* Footer Row: Timestamp & Span Counts */}
                <div className="mt-2.5 flex items-center justify-between border-t border-obsidian-800/80 pt-2 text-[10px] text-slate-400">
                  <span className="flex items-center gap-1 font-mono">
                    <Clock className="h-3 w-3" />
                    {formatTimestamp(trace.start_time_ns)}
                  </span>
                  <div className="flex items-center gap-1.5 font-mono">
                    <span>{trace.span_count} spans</span>
                    <span>•</span>
                    <span>{trace.event_count} evts</span>
                    <ChevronRight className="h-3 w-3 text-slate-500 group-hover:text-slate-300" />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Sidebar Footer */}
      <div className="flex items-center justify-between border-t border-obsidian-800 bg-obsidian-950/80 px-3.5 py-2 text-[11px]">
        <div className="flex items-center gap-1.5 text-slate-400">
          <span className="h-2 w-2 rounded-full bg-hud-emerald shadow-glow-emerald" />
          <span className="font-mono text-[10px]">OTEL 127.0.0.1:8080</span>
        </div>
        <span className="font-mono text-[10px] text-slate-300 font-semibold">{utcTime}</span>
      </div>
    </aside>
  );
};
