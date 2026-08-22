'use client';

import { CheckCircle2, Copy } from 'lucide-react';
import { SpanNode, TraceTree } from '@/lib/types';
import { formatDuration } from '@/lib/utils';

export function TraceView({ trace, selectedSpanId, onSelectSpan }: { trace: TraceTree; selectedSpanId: string | null; onSelectSpan: (id: string) => void }) {
  const copy = () => navigator.clipboard.writeText(trace.trace_id);
  return <div className="flex min-h-0 flex-1 flex-col overflow-auto p-5">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-obsidian-800 pb-4"><div><p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Selected run</p><h2 className="mt-1 text-xl font-semibold text-white">{trace.run_name || trace.root_name}</h2><button onClick={copy} className="mt-2 flex items-center gap-1 font-mono text-[11px] text-slate-500 hover:text-slate-200"><Copy className="h-3 w-3" /> {trace.trace_id}</button></div><div className="flex gap-5 font-mono text-xs"><Metric label="duration" value={formatDuration(trace.total_duration_ms)} /><Metric label="spans" value={String(trace.span_count)} /><Metric label="events" value={String(trace.event_count)} /></div></div>
    <div className="mt-4 overflow-hidden rounded-md border border-obsidian-800"><div className="grid grid-cols-[minmax(12rem,1fr)_6rem_5rem] gap-3 border-b border-obsidian-800 bg-obsidian-900 px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-slate-500"><span>Step</span><span>Duration</span><span>Status</span></div>{trace.flat_spans.map((span) => <SpanRow key={span.span_id} span={span} selected={span.span_id === selectedSpanId} onClick={() => onSelectSpan(span.span_id)} />)}</div>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div><p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p><p className="mt-1 text-sm font-semibold text-slate-100">{value}</p></div>; }
function SpanRow({ span, selected, onClick }: { span: SpanNode; selected: boolean; onClick: () => void }) { return <button onClick={onClick} className={`grid w-full grid-cols-[minmax(12rem,1fr)_6rem_5rem] gap-3 border-b border-obsidian-800 px-4 py-3 text-left last:border-0 ${selected ? 'bg-obsidian-800' : 'hover:bg-obsidian-900'}`}><span className="min-w-0 truncate text-sm text-slate-200" style={{ paddingLeft: `${(span.depth ?? 0) * 14}px` }}>{span.name}</span><span className="font-mono text-xs text-slate-400">{formatDuration(span.duration_ms)}</span><span className="flex items-center gap-1 font-mono text-xs text-emerald-300"><CheckCircle2 className="h-3.5 w-3.5" /> {span.status.code}</span></button>; }
