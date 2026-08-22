'use client';

import React, { useState } from 'react';
import {
  Copy,
  Check,
  Zap,
  Globe,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  FileCode,
  Flame,
  BarChart3,
  Layers,
  ChevronRight,
  ShieldCheck,
} from 'lucide-react';
import { TraceTree, SpanNode, ViewMode } from '@/lib/types';
import { cn, formatDuration, getSpanTheme } from '@/lib/utils';

interface WaterfallTimelineProps {
  trace: TraceTree;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}

export const WaterfallTimeline: React.FC<WaterfallTimelineProps> = ({
  trace,
  selectedSpanId,
  onSelectSpan,
  viewMode,
  onViewModeChange,
}) => {
  const [copiedTraceId, setCopiedTraceId] = useState(false);

  const handleCopyTraceId = () => {
    navigator.clipboard.writeText(trace.trace_id);
    setCopiedTraceId(true);
    setTimeout(() => setCopiedTraceId(false), 1500);
  };

  const isRunB =
    (trace.run_name || '').toLowerCase().includes('run b') ||
    (trace.run_name || '').toLowerCase().includes('avoid');

  // Generate ruler tick marks (5 ticks across total duration)
  const ticks = [0, 0.25, 0.5, 0.75, 1.0].map((ratio) => ({
    ratio,
    ms: Math.round(trace.total_duration_ms * ratio),
  }));

  // Canonical stages pipeline
  const stages = [
    { num: '1', name: 'detect' },
    { num: '2', name: 'tag_pose' },
    { num: '3', name: 'update_twin' },
    { num: '4', name: 'extract_params' },
    { num: '5', name: 'scrape' },
    { num: '6', name: 'patch_spec' },
    { num: '7', name: 'test' },
    { num: '8', name: 'approve' },
    { num: '9', name: 'skill_exec' },
  ];

  return (
    <div className="flex h-full flex-1 flex-col overflow-hidden bg-obsidian-950">
      {/* 1. Active Trace Info Banner */}
      <div className="border-b border-obsidian-800 bg-obsidian-900/60 p-4 backdrop-blur-sm">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
              className={cn(
                'rounded-md px-2.5 py-1 font-display text-[10px] font-extrabold tracking-widest uppercase',
                isRunB
                  ? 'border border-hud-violet/50 bg-hud-violet/20 text-purple-300 shadow-glow-violet'
                  : 'border border-hud-cyan/50 bg-hud-cyan/20 text-hud-cyan shadow-glow-cyan'
              )}
            >
              FAST PATH // ZERO DOWNTIME
            </span>
            <h2 className="font-display text-lg font-bold text-slate-100">
              {trace.run_name || trace.root_name}
            </h2>

            {/* Trace ID Chip */}
            <div
              onClick={handleCopyTraceId}
              className="group flex cursor-pointer items-center gap-1.5 rounded border border-obsidian-750 bg-obsidian-850 px-2 py-0.5 font-mono text-[11px] text-slate-400 hover:border-hud-cyan/40 hover:text-slate-200"
              title="Click to copy Trace ID"
            >
              <span className="text-[10px] text-slate-400">TRACE:</span>
              <span className="text-hud-cyan font-semibold">
                {trace.trace_id.slice(0, 12)}...{trace.trace_id.slice(-4)}
              </span>
              {copiedTraceId ? (
                <Check className="h-3 w-3 text-hud-emerald" />
              ) : (
                <Copy className="h-3 w-3 text-slate-500 group-hover:text-hud-cyan" />
              )}
            </div>
          </div>

          {/* Banner Telemetry Stats */}
          <div className="flex items-center gap-4">
            <div className="flex flex-col items-end">
              <span className="text-[10px] font-semibold uppercase text-slate-400">
                TOTAL DURATION
              </span>
              <span className="font-mono text-sm font-bold text-hud-cyan">
                {formatDuration(trace.total_duration_ms)}
              </span>
            </div>

            <div className="h-7 w-px bg-obsidian-800" />

            <div className="flex flex-col items-end">
              <span className="text-[10px] font-semibold uppercase text-slate-400">
                SPANS
              </span>
              <span className="font-mono text-sm font-bold text-slate-200">
                {trace.span_count}
              </span>
            </div>

            <div className="h-7 w-px bg-obsidian-800" />

            <div className="flex flex-col items-end">
              <span className="text-[10px] font-semibold uppercase text-slate-400">
                MILESTONES
              </span>
              <span className="font-mono text-sm font-bold text-hud-amber">
                {trace.event_count}
              </span>
            </div>

            <div className="h-7 w-px bg-obsidian-800" />

            <div className="flex flex-col items-end">
              <span className="text-[10px] font-semibold uppercase text-slate-400">
                SPEC STATUS
              </span>
              <span className="font-mono text-sm font-bold text-hud-emerald flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                HOT-SWAPPED
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 2. Canonical Pipeline Flow Legend & View Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-obsidian-800 bg-obsidian-900/40 px-4 py-2 text-xs">
        <div className="flex items-center gap-1.5 overflow-x-auto py-1">
          <span className="font-display text-[10px] font-bold uppercase tracking-wider text-slate-400 mr-1 flex-shrink-0">
            PIPELINE:
          </span>
          {stages.map((stage, i) => (
            <React.Fragment key={stage.name}>
              <span
                className={cn(
                  'rounded px-2 py-0.5 font-mono text-[10px] font-medium flex-shrink-0',
                  stage.name === 'scrape' && isRunB
                    ? 'border border-hud-violet/50 bg-hud-violet/20 text-purple-300'
                    : stage.name === 'patch_spec'
                    ? 'border border-hud-emerald/50 bg-hud-emerald/20 text-emerald-300'
                    : 'border border-obsidian-750 bg-obsidian-850/80 text-slate-300'
                )}
              >
                {stage.num}. {stage.name}
              </span>
              {i < stages.length - 1 && (
                <span className="text-[10px] text-slate-400">→</span>
              )}
            </React.Fragment>
          ))}
        </div>

        {/* View Mode Buttons */}
        <div className="flex items-center gap-1 rounded-lg border border-obsidian-800 bg-obsidian-850 p-0.5">
          <button
            onClick={() => onViewModeChange('waterfall')}
            className={cn(
              'flex items-center gap-1.5 rounded px-2.5 py-1 font-display text-[11px] font-bold transition-all',
              viewMode === 'waterfall'
                ? 'bg-hud-cyan/20 text-hud-cyan'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            <BarChart3 className="h-3.5 w-3.5" />
            Waterfall
          </button>
          <button
            onClick={() => onViewModeChange('flame')}
            className={cn(
              'flex items-center gap-1.5 rounded px-2.5 py-1 font-display text-[11px] font-bold transition-all',
              viewMode === 'flame'
                ? 'bg-hud-amber/20 text-hud-amber'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            <Flame className="h-3.5 w-3.5" />
            Flame
          </button>
          <button
            onClick={() => onViewModeChange('json')}
            className={cn(
              'flex items-center gap-1.5 rounded px-2.5 py-1 font-display text-[11px] font-bold transition-all',
              viewMode === 'json'
                ? 'bg-hud-violet/20 text-purple-300'
                : 'text-slate-400 hover:text-slate-200'
            )}
          >
            <FileCode className="h-3.5 w-3.5" />
            JSON
          </button>
        </div>
      </div>

      {/* 3. Main Waterfall Body */}
      <div className="relative flex flex-1 flex-col overflow-hidden">
        {/* Time Scale Ruler */}
        <div className="flex border-b border-obsidian-800 bg-obsidian-900/90 text-[10px] font-mono text-slate-400">
          <div className="w-[340px] flex-shrink-0 border-r border-obsidian-800 px-4 py-2 font-display text-[10px] font-bold uppercase tracking-wider text-slate-400">
            SPAN OPERATION &amp; ATTRIBUTES
          </div>
          <div className="relative flex-1 py-2">
            {ticks.map((t, idx) => (
              <div
                key={idx}
                className="absolute top-0 bottom-0 flex flex-col justify-between -translate-x-1/2"
                style={{ left: `${t.ratio * 100}%` }}
              >
                <span className="px-1">{t.ms} ms</span>
                <div className="h-1.5 w-px bg-obsidian-700" />
              </div>
            ))}
          </div>
        </div>

        {/* Milestone Events Ribbon (Top track pins) */}
        {trace.events && trace.events.length > 0 && (
          <div className="relative flex border-b border-obsidian-800/80 bg-obsidian-900/40 py-2">
            <div className="w-[340px] flex-shrink-0 border-r border-obsidian-800 px-4 font-mono text-[10px] text-slate-400 flex items-center gap-1.5">
              <Zap className="h-3 w-3 text-hud-amber" />
              MILESTONES ({trace.events.length})
            </div>
            <div className="relative flex-1 h-6">
              {trace.events.map((ev, idx) => {
                const isPrompt = ev.name === 'physical_prompt';
                const isRelease = ev.name === 'release';
                const isObstacle = ev.name === 'obstacle_detected';

                return (
                  <div
                    key={idx}
                    className="group absolute top-0 -translate-x-1/2 cursor-pointer"
                    style={{ left: `${ev.percent_offset}%` }}
                    onClick={() => {
                      if (ev.span_id) onSelectSpan(ev.span_id);
                    }}
                  >
                    {/* Diamond Marker */}
                    <div
                      className={cn(
                        'flex items-center gap-1 rounded-full px-2 py-0.5 text-[9px] font-mono font-bold shadow-lg transition-transform group-hover:scale-110',
                        isPrompt
                          ? 'border border-amber-500/60 bg-amber-500/20 text-amber-300 shadow-glow-amber'
                          : isRelease
                          ? 'border border-emerald-500/60 bg-emerald-500/20 text-emerald-300 shadow-glow-emerald'
                          : 'border border-rose-500/60 bg-rose-500/20 text-rose-300'
                      )}
                    >
                      <span className="h-1.5 w-1.5 rotate-45 bg-current" />
                      [{ev.name.toUpperCase()}]
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Scrollable Waterfall Rows */}
        <div className="relative flex-1 overflow-y-auto overflow-x-hidden p-2">
          {/* Vertical Grid Lines for Ruler Alignment */}
          <div className="pointer-events-none absolute inset-0 left-[340px] flex">
            {ticks.map((t, idx) => (
              <div
                key={idx}
                className="absolute top-0 bottom-0 w-px border-r border-dashed border-obsidian-800/50"
                style={{ left: `${t.ratio * 100}%` }}
              />
            ))}
          </div>

          {/* Span Rows */}
          <div className="space-y-1.5">
            {trace.flat_spans.map((span) => {
              const isSelected = span.span_id === selectedSpanId;
              const theme = getSpanTheme(span.name);
              const depth = span.depth ?? (span.parent_id ? 1 : 0);

              // Quick summary badges
              const isScrape = span.name === 'scrape';
              const isPatch = span.name === 'patch_spec';
              const isTest = span.name === 'test';
              const isApprove = span.name === 'approve';

              return (
                <div
                  key={span.span_id}
                  onClick={() => onSelectSpan(span.span_id)}
                  className={cn(
                    'group flex cursor-pointer items-center rounded-lg border transition-all py-1.5',
                    isSelected
                      ? 'border-hud-cyan bg-hud-cyan/10 shadow-glow-cyan'
                      : 'border-obsidian-800/80 bg-obsidian-900/60 hover:border-obsidian-700 hover:bg-obsidian-850'
                  )}
                >
                  {/* Left: Span Info & Key Param Chips */}
                  <div
                    className="flex w-[340px] flex-shrink-0 items-center justify-between gap-2 border-r border-obsidian-800 pr-3"
                    style={{ paddingLeft: `${12 + depth * 18}px` }}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      <span className="text-sm">{theme.icon}</span>
                      <span
                        className={cn(
                          'font-mono text-xs font-bold tracking-tight truncate',
                          theme.color
                        )}
                      >
                        {span.name}
                      </span>
                    </div>

                    {/* Param Summary Chip */}
                    <div className="flex items-center gap-1">
                      {isScrape && span.attributes.item_name && (
                        <span className="rounded bg-purple-500/20 px-1.5 py-0.2 font-mono text-[9px] text-purple-300 border border-purple-500/40">
                          Bright Data 7x24cm
                        </span>
                      )}
                      {isPatch && (
                        <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 font-mono text-[9px] text-emerald-300 border border-emerald-500/40">
                          v2 {span.attributes.ops || 'spec'}
                        </span>
                      )}
                      {isTest && (
                        <span className="rounded bg-teal-500/20 px-1.5 py-0.2 font-mono text-[9px] text-teal-300 border border-teal-500/40">
                          PASS (0.38cm)
                        </span>
                      )}
                      {isApprove && (
                        <span className="rounded bg-emerald-500/20 px-1.5 py-0.2 font-mono text-[9px] text-emerald-300 border border-emerald-500/40">
                          AUTO APPROVE
                        </span>
                      )}
                      <span className="font-mono text-[10px] text-slate-400">
                        {formatDuration(span.duration_ms)}
                      </span>
                    </div>
                  </div>

                  {/* Right: Waterfall Duration Bar */}
                  <div className="relative flex flex-1 items-center px-2">
                    <div
                      className={cn(
                        'relative flex h-6 items-center rounded border transition-all',
                        theme.bg,
                        theme.border,
                        isSelected && 'ring-1 ring-hud-cyan'
                      )}
                      style={{
                        marginLeft: `${span.percent_start}%`,
                        width: `${Math.max(1.5, span.percent_width)}%`,
                        minWidth: '24px',
                      }}
                    >
                      <span className="px-1.5 font-mono text-[10px] font-bold text-slate-100 truncate">
                        {formatDuration(span.duration_ms)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};
