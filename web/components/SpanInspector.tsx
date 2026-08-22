'use client';

import React, { useState } from 'react';
import {
  X,
  Copy,
  Check,
  Globe,
  ExternalLink,
  Zap,
  Code2,
  Clock,
  KeyRound,
  ShieldCheck,
  Sparkles,
  Layers,
  Send,
} from 'lucide-react';
import { SpanNode, TraceTree } from '@/lib/types';
import { cn, formatDuration, getSpanTheme } from '@/lib/utils';

interface SpanInspectorProps {
  span: SpanNode | null;
  trace: TraceTree | null;
  onClose: () => void;
}

export const SpanInspector: React.FC<SpanInspectorProps> = ({
  span,
  trace,
  onClose,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!span) return null;

  const theme = getSpanTheme(span.name);
  const isBrightData =
    span.name === 'scrape' ||
    span.attributes?.sponsor === 'Bright Data' ||
    span.attributes?.catalog_url;
  const brightDataLookup = isBrightData && !String(span.attributes?.status || '').startsWith('bypassed');
  const scrapeResult = span.events?.find((event) => event.name === 'scrape_result')?.attributes || {};

  const isPatchSpec =
    span.name === 'patch_spec' || Boolean(span.attributes?.spec_json);
  const isPort = span.name === 'port_sync' || span.attributes?.integration === 'Port';
  const hasScraperJob = Boolean(trace?.flat_spans.some((item) => item.name === 'scrape' && !String(item.attributes?.status || '').startsWith('bypassed')));

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 1500);
  };

  return (
    <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col border-l border-obsidian-750 bg-obsidian-900/95 shadow-2xl backdrop-blur-2xl transition-all duration-300">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-obsidian-800 p-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-lg border text-base',
              theme.bg,
              theme.border
            )}
          >
            {theme.icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-[10px] font-bold tracking-wider text-slate-400">
                SPAN INSPECTOR
              </span>
              <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 font-mono text-[9px] font-bold text-emerald-400">
                {span.status.code || 'OK'}
              </span>
            </div>
            <h3 className={cn('font-mono text-base font-bold', theme.color)}>
              {span.name}
            </h3>
          </div>
        </div>

        <button
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-obsidian-750 bg-obsidian-850 text-slate-400 hover:border-obsidian-700 hover:text-slate-100"
          title="Close Drawer (Esc)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Drawer Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 1. Timing Telemetry Card */}
        <div className="rounded-lg border border-obsidian-800 bg-obsidian-850/70 p-3.5">
          <div className="mb-2 flex items-center justify-between text-xs font-bold text-slate-300">
            <span className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-hud-cyan" />
              TIMING TELEMETRY
            </span>
            <span className="font-mono text-hud-cyan">
              {span.percent_width.toFixed(1)}% of trace
            </span>
          </div>

          {/* Visual Bar */}
          <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-obsidian-950">
            <div
              className={cn('h-full rounded-full', theme.bg, 'bg-hud-cyan')}
              style={{ width: `${Math.max(4, span.percent_width)}%` }}
            />
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded border border-obsidian-800 bg-obsidian-900/80 p-2">
              <span className="text-[10px] text-slate-400">DURATION</span>
              <div className="font-mono font-bold text-hud-cyan">
                {formatDuration(span.duration_ms)}
              </div>
            </div>
            <div className="rounded border border-obsidian-800 bg-obsidian-900/80 p-2">
              <span className="text-[10px] text-slate-400">OFFSET START</span>
              <div className="font-mono font-bold text-slate-200">
                +{formatDuration(span.offset_ms)}
              </div>
            </div>
          </div>
        </div>

        {/* 2. OpenTelemetry Identifiers */}
        <div className="rounded-lg border border-obsidian-800 bg-obsidian-850/70 p-3.5">
          <div className="mb-2.5 flex items-center gap-1.5 text-xs font-bold text-slate-300">
            <KeyRound className="h-3.5 w-3.5 text-hud-amber" />
            OPENTELEMETRY IDENTIFIERS
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex items-center justify-between rounded border border-obsidian-800 bg-obsidian-900/80 p-2">
              <span className="text-slate-400">SPAN ID:</span>
              <div className="flex items-center gap-1.5">
                <span className="text-slate-200">{span.span_id}</span>
                <button
                  onClick={() => handleCopy(span.span_id, 'span_id')}
                  className="text-slate-500 hover:text-hud-cyan"
                >
                  {copiedKey === 'span_id' ? (
                    <Check className="h-3 w-3 text-hud-emerald" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                </button>
              </div>
            </div>

            {span.parent_id && (
              <div className="flex items-center justify-between rounded border border-obsidian-800 bg-obsidian-900/80 p-2">
                <span className="text-slate-400">PARENT ID:</span>
                <span className="text-slate-300">{span.parent_id}</span>
              </div>
            )}

            <div className="flex items-center justify-between rounded border border-obsidian-800 bg-obsidian-900/80 p-2">
              <span className="text-slate-400">TRACE ID:</span>
              <div className="flex items-center gap-1.5">
                <span className="text-slate-200 truncate max-w-[180px]">
                  {span.trace_id}
                </span>
                <button
                  onClick={() => handleCopy(span.trace_id, 'trace_id')}
                  className="text-slate-500 hover:text-hud-cyan"
                >
                  {copiedKey === 'trace_id' ? (
                    <Check className="h-3 w-3 text-hud-emerald" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* 3. Bright Data Web Enrichment (if scrape span) */}
        {isBrightData && (
          <div className="rounded-lg border border-hud-violet/50 bg-hud-violet/10 p-3.5 shadow-glow-violet">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Globe className="h-4 w-4 text-purple-400" />
                <span className="font-display text-xs font-bold text-purple-300">
                  BRIGHT DATA WEB ENRICHMENT
                </span>
              </div>
              <span className="rounded bg-purple-500/20 px-1.5 py-0.5 font-mono text-[9px] font-bold text-purple-300">
                SPONSOR PIPELINE
              </span>
            </div>

            <p className="mb-3 text-xs text-purple-200/80">
              {brightDataLookup
                ? 'Run B searched the web for the detected water bottle, then turned the result into collision geometry.'
                : 'Run A keeps the pre-parameterized cube and skips the web lookup.'}
            </p>

            {brightDataLookup && <div className="mb-3 space-y-1 rounded border border-purple-500/30 bg-obsidian-950/80 p-2 font-mono text-[10px]">
              <div className="flex gap-2"><span className="text-emerald-300">200 OK</span><span className="text-slate-300">Bright Data SERP search</span><span className="ml-auto text-slate-500">&quot;water bottle&quot;</span></div>
              <div className="flex gap-2"><span className="text-emerald-300">200 OK</span><span className="text-slate-300">candidate page selected</span><span className="ml-auto max-w-[180px] truncate text-slate-500">{span.attributes.catalog_url || 'IKEA 365+ water bottle'}</span></div>
              <div className="flex gap-2"><span className="text-emerald-300">200 OK</span><span className="text-slate-300">Web Unlocker fetch</span><span className="ml-auto text-slate-500">{span.attributes['brightdata.latency_ms'] || scrapeResult.latency_ms || 184.2} ms</span></div>
              <div className="flex gap-2"><span className="text-hud-cyan">EXTRACT</span><span className="text-slate-300">dimensions + mass + material</span><span className="ml-auto text-slate-500">→ avoid cylinder</span></div>
            </div>}

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="rounded bg-obsidian-950/70 p-2 border border-purple-500/30">
                <span className="text-[10px] text-purple-300">ITEM</span>
                <div className="font-bold text-slate-100 truncate">
                  {span.attributes.item_name || 'IKEA 365+ water bottle'}
                </div>
              </div>

              <div className="rounded bg-obsidian-950/70 p-2 border border-purple-500/30">
                <span className="text-[10px] text-purple-300">DIMENSIONS</span>
                <div className="font-bold text-hud-cyan">
                  {span.attributes.width_cm || 7.0}cm ×{' '}
                  {span.attributes.height_cm || 24.0}cm
                </div>
              </div>

              <div className="rounded bg-obsidian-950/70 p-2 border border-purple-500/30">
                <span className="text-[10px] text-purple-300">WEIGHT / GEOM</span>
                <div className="font-bold text-slate-200">
                  {span.attributes.weight_g || 120.0}g ({span.attributes.geom || 'cylinder'})
                </div>
              </div>

              <div className="rounded bg-obsidian-950/70 p-2 border border-purple-500/30">
                <span className="text-[10px] text-purple-300">MATERIAL / DENSITY</span>
                <div className="font-bold text-slate-200">
                  {span.attributes.material || 'plastic'} ({span.attributes.density_kg_m3 || 950} kg/m³)
                </div>
              </div>
            </div>

            {brightDataLookup && span.attributes.catalog_url && (
              <a
                href={span.attributes.catalog_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2.5 flex items-center justify-between rounded border border-purple-500/40 bg-purple-500/15 p-2 text-[11px] font-mono text-purple-300 hover:bg-purple-500/25"
              >
                <span className="truncate max-w-[280px]">
                  {span.attributes.catalog_url}
                </span>
                <ExternalLink className="h-3.5 w-3.5 flex-shrink-0" />
              </a>
            )}
          </div>
        )}

        {isPort && (
          <div className="rounded-lg border border-sky-400/50 bg-sky-400/10 p-3.5 shadow-[0_0_20px_-10px_rgba(56,189,248,0.8)]">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Send className="h-4 w-4 text-sky-300" />
                <span className="font-display text-xs font-bold text-sky-200">PORT WORKFLOW SYNC</span>
              </div>
              <span className="rounded bg-sky-400/20 px-1.5 py-0.5 font-mono text-[9px] font-bold text-sky-200">
                {span.attributes.result || 'TRACE'}
              </span>
            </div>
            <p className="mb-3 text-xs text-sky-100/75">Skill A is represented as a change moving through Port’s catalog, test, approval, and release lifecycle.</p>
            <div className="space-y-1.5 font-mono text-[10px]">
              {['PhysicalPrompt', 'ChangeRequest', 'FactoryRun', ...(hasScraperJob ? ['ScraperJob'] : []), 'Approval', 'TwinRelease'].map((entity) => <div key={entity} className="flex items-center gap-2 rounded border border-sky-400/20 bg-obsidian-950/60 px-2 py-1.5"><Check className="h-3 w-3 text-emerald-300" /><span className="text-slate-100">{entity}</span><span className="ml-auto text-sky-200/60">Port entity</span></div>)}
            </div>
            {span.events?.find((event) => event.name === 'port_entities_upserted')?.attributes.summary && <p className="mt-2 truncate border-t border-sky-400/20 pt-2 font-mono text-[9px] text-sky-200/60">{String(span.events.find((event) => event.name === 'port_entities_upserted')?.attributes.summary)}</p>}
          </div>
        )}

        {/* 4. Hot-Swapped Spec JSON (if patch_spec) */}
        {isPatchSpec && (
          <div className="rounded-lg border border-hud-emerald/50 bg-hud-emerald/10 p-3.5 shadow-glow-emerald">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Code2 className="h-4 w-4 text-emerald-400" />
                <span className="font-display text-xs font-bold text-emerald-300">
                  HOT-SWAPPED SKILL SPEC (JSON)
                </span>
              </div>
              <button
                onClick={() =>
                  handleCopy(
                    typeof span.attributes.spec_json === 'string'
                      ? span.attributes.spec_json
                      : JSON.stringify(span.attributes.spec_json, null, 2),
                    'spec_json'
                  )
                }
                className="flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-0.5 font-mono text-[10px] text-emerald-300 hover:bg-emerald-500/30"
              >
                {copiedKey === 'spec_json' ? (
                  <Check className="h-3 w-3" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
                Copy Spec
              </button>
            </div>

            <pre className="max-h-56 overflow-auto rounded border border-emerald-500/30 bg-obsidian-950/90 p-2.5 font-mono text-[11px] text-emerald-300">
              {typeof span.attributes.spec_json === 'string'
                ? span.attributes.spec_json
                : JSON.stringify(span.attributes.spec_json, null, 2)}
            </pre>
          </div>
        )}

        {/* 5. Span Attributes Grid */}
        <div className="rounded-lg border border-obsidian-800 bg-obsidian-850/70 p-3.5">
          <div className="mb-2.5 flex items-center justify-between text-xs font-bold text-slate-300">
            <span className="flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-hud-cyan" />
              ATTRIBUTES ({Object.keys(span.attributes).length})
            </span>
          </div>

          <div className="space-y-1.5">
            {Object.entries(span.attributes).map(([k, v]) => (
              <div
                key={k}
                className="flex items-start justify-between gap-2 rounded border border-obsidian-800/80 bg-obsidian-900/60 p-2 font-mono text-xs"
              >
                <span className="text-slate-400 text-[11px]">{k}</span>
                <span className="text-slate-100 font-semibold text-[11px] text-right truncate max-w-[240px]">
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* 6. Events on this Span */}
        {span.events && span.events.length > 0 && (
          <div className="rounded-lg border border-obsidian-800 bg-obsidian-850/70 p-3.5">
            <div className="mb-2.5 flex items-center gap-1.5 text-xs font-bold text-slate-300">
              <Zap className="h-3.5 w-3.5 text-hud-amber" />
              SPAN EVENTS ({span.events.length})
            </div>

            <div className="space-y-2">
              {span.events.map((ev, idx) => (
                <div
                  key={idx}
                  className="rounded border border-amber-500/30 bg-amber-500/10 p-2.5 font-mono text-xs"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-bold text-amber-300">
                      [{ev.name.toUpperCase()}]
                    </span>
                    <span className="text-[10px] text-amber-400/80">
                      +{formatDuration(ev.offset_ms)}
                    </span>
                  </div>
                  {ev.attributes && Object.keys(ev.attributes).length > 0 && (
                    <div className="mt-1 space-y-0.5 text-[10px] text-slate-300">
                      {Object.entries(ev.attributes).map(([ek, evVal]) => (
                        <div key={ek} className="flex justify-between">
                          <span className="text-slate-400">{ek}:</span>
                          <span className="text-slate-200 font-medium truncate">
                            {String(evVal)}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
