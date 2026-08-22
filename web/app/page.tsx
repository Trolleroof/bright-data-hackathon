'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChecksPanel } from '@/components/ChecksPanel';
import { EmptyState } from '@/components/EmptyState';
import { Header } from '@/components/Header';
import { LiveOps } from '@/components/LiveOps';
import { Sidebar } from '@/components/Sidebar';
import { SpanInspector } from '@/components/SpanInspector';
import { TraceView } from '@/components/TraceView';
import { BackendStatus, FilterType, LiveState, TraceTree } from '@/lib/types';

export default function ControlRoom() {
  const [traces, setTraces] = useState<TraceTree[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [live, setLive] = useState<LiveState | null>(null);
  const [utcTime, setUtcTime] = useState('--:--:--');
  const [toast, setToast] = useState<string | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [isProgramRunning, setIsProgramRunning] = useState(false);

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((current) => current === message ? null : current), 2800);
  }, []);

  const fetchStatus = useCallback(async () => {
    try { const response = await fetch('/api/status', { cache: 'no-store' }); if (response.ok) setStatus(await response.json()); } catch { /* local backend may be starting */ }
  }, []);

  const fetchLive = useCallback(async () => {
    try { const response = await fetch('/api/live', { cache: 'no-store' }); if (response.ok) setLive(await response.json()); } catch { /* fallback payload handles offline state */ }
  }, []);

  const fetchTraces = useCallback(async (selectFirst = false) => {
    try {
      const response = await fetch('/api/traces', { cache: 'no-store' });
      if (!response.ok) return;
      const list: TraceTree[] = (await response.json()).traces || [];
      setTraces(list);
      setSelectedTraceId((current) => list.length === 0 ? null : selectFirst || !list.some((trace) => trace.trace_id === current) ? list[0].trace_id : current);
    } catch { /* keep the last good list */ }
  }, []);

  useEffect(() => {
    fetchStatus(); fetchLive(); fetchTraces(true);
    const liveTimer = window.setInterval(fetchLive, 500);
    const dataTimer = window.setInterval(() => { fetchStatus(); fetchTraces(); }, 3000);
    const clockTimer = window.setInterval(() => setUtcTime(`${new Date().toISOString().slice(11, 19)} UTC`), 1000);
    return () => { window.clearInterval(liveTimer); window.clearInterval(dataTimer); window.clearInterval(clockTimer); };
  }, [fetchLive, fetchStatus, fetchTraces]);

  const activeTrace = useMemo(() => traces.find((trace) => trace.trace_id === selectedTraceId) || null, [traces, selectedTraceId]);
  const activeSpan = useMemo(() => activeTrace?.flat_spans.find((span) => span.span_id === selectedSpanId) || null, [activeTrace, selectedSpanId]);
  const runDemo = async (run: 'A' | 'B') => {
    setIsTriggering(true);
    try {
      const response = await fetch('/api/traces/demo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Run failed');
      await fetchTraces(true);
      showToast(`Run ${run} recorded`);
    } catch (error) { showToast(error instanceof Error ? error.message : 'Run failed'); }
    finally { setIsTriggering(false); }
  };

  const clearTraces = async () => {
    await fetch('/api/traces/clear', { method: 'POST' });
    setTraces([]); setSelectedTraceId(null); setSelectedSpanId(null);
    showToast('Traces cleared');
  };

  const runProgram = async () => {
    if (isProgramRunning) return;
    setIsProgramRunning(true);
    showToast('Running checks…');
    try {
      const response = await fetch('/api/checks/run', { method: 'POST' });
      const job = await response.json();
      if (!response.ok || !job.job_id) throw new Error(job.error || 'Could not start checks');
      while (true) {
        await new Promise((resolve) => window.setTimeout(resolve, 500));
        const poll = await fetch(`/api/checks/job?id=${job.job_id}&since=-1`, { cache: 'no-store' });
        const result = await poll.json();
        if (result.state === 'done') { showToast(result.exit_code === 0 ? 'All checks passed' : 'Checks failed'); break; }
      }
    } catch (error) { showToast(error instanceof Error ? error.message : 'Could not run checks'); }
    finally { setIsProgramRunning(false); }
  };

  return <div className="flex h-screen flex-col overflow-hidden bg-obsidian-950 text-slate-100">
    <Header status={status} isTriggering={isTriggering} isProgramRunning={isProgramRunning} onRunA={() => runDemo('A')} onRunB={() => runDemo('B')} onRefresh={() => { fetchLive(); fetchStatus(); fetchTraces(); }} onClear={clearTraces} onRunProgram={runProgram} />
    <main className="flex min-h-0 flex-1">
      <Sidebar traces={traces} selectedTraceId={selectedTraceId} onSelectTrace={(id) => { setSelectedTraceId(id); setSelectedSpanId(null); }} filter={filter} onFilterChange={setFilter} isStreaming={isTriggering} utcTime={utcTime} />
      <div className="min-w-0 flex-1 overflow-y-auto">
        <LiveOps live={live} onToast={showToast} onRefresh={fetchLive} />
        {activeTrace ? <TraceView trace={activeTrace} selectedSpanId={selectedSpanId} onSelectSpan={setSelectedSpanId} /> : <EmptyState onRunA={() => runDemo('A')} onRunB={() => runDemo('B')} />}
      </div>
      {activeTrace && activeSpan && <SpanInspector span={activeSpan} trace={activeTrace} onClose={() => setSelectedSpanId(null)} />}
    </main>
    <ChecksPanel onToast={showToast} />
    {toast && <div className="fixed bottom-5 right-5 z-50 rounded-md border border-obsidian-700 bg-obsidian-900 px-4 py-2.5 text-xs shadow-lg">{toast}</div>}
  </div>;
}
