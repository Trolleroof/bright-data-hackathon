'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Header } from '@/components/Header';
import { Sidebar } from '@/components/Sidebar';
import { WaterfallTimeline } from '@/components/WaterfallTimeline';
import { FlameGraph } from '@/components/FlameGraph';
import { RawJsonView } from '@/components/RawJsonView';
import { SpanInspector } from '@/components/SpanInspector';
import { EmptyState } from '@/components/EmptyState';
import {
  TraceTree,
  SpanNode,
  BackendStatus,
  ViewMode,
  FilterType,
} from '@/lib/types';

export default function FlightRecorderPage() {
  const [traces, setTraces] = useState<TraceTree[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('waterfall');
  const [status, setStatus] = useState<BackendStatus | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [utcTime, setUtcTime] = useState('--:--:--');
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  // Show quick HUD toast
  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((current) => (current === msg ? null : current));
    }, 2800);
  };

  // Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(now.toISOString().substring(11, 19) + ' UTC');
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch status
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/status', { cache: 'no-store' });
      if (res.ok) {
        const data: BackendStatus = await res.json();
        setStatus(data);
      }
    } catch {
      // ignore
    }
  }, []);

  // Fetch traces
  const fetchTraces = useCallback(
    async (autoSelectFirst = false) => {
      try {
        const res = await fetch('/api/traces', { cache: 'no-store' });
        if (res.ok) {
          const data = await res.json();
          const list: TraceTree[] = data.traces || [];
          setTraces(list);

          if (list.length > 0) {
            setSelectedTraceId((prev) => {
              if (autoSelectFirst || !prev || !list.some((t) => t.trace_id === prev)) {
                return list[0].trace_id;
              }
              return prev;
            });
          } else {
            setSelectedTraceId(null);
            setSelectedSpanId(null);
          }
        }
      } catch {
        // ignore
      }
    },
    []
  );

  // Initial load + periodic polling
  useEffect(() => {
    fetchStatus();
    fetchTraces(true);

    const pollInterval = setInterval(() => {
      fetchStatus();
      fetchTraces(false);
    }, 3000);

    return () => clearInterval(pollInterval);
  }, [fetchStatus, fetchTraces]);

  // Selected Trace Object
  const activeTrace = useMemo(() => {
    return traces.find((t) => t.trace_id === selectedTraceId) || null;
  }, [traces, selectedTraceId]);

  // Selected Span Object
  const activeSpan = useMemo(() => {
    if (!activeTrace || !selectedSpanId) return null;
    return (
      activeTrace.flat_spans.find((s) => s.span_id === selectedSpanId) || null
    );
  }, [activeTrace, selectedSpanId]);

  // Latest Operation
  const latestOp = useMemo(() => {
    if (!activeTrace || !activeTrace.flat_spans.length) return 'IDLE';
    const last = activeTrace.flat_spans[activeTrace.flat_spans.length - 1];
    return last.name;
  }, [activeTrace]);

  // Action: Run A
  const handleRunA = async () => {
    setIsTriggering(true);
    setIsStreaming(true);
    showToast('🚀 Launching Run A: goto fast path...');
    try {
      const res = await fetch('/api/traces/demo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run: 'A' }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.trace) {
          setTraces((prev) => [data.trace, ...prev]);
          setSelectedTraceId(data.trace.trace_id);
          setSelectedSpanId(null);
          showToast('✅ Run A telemetry recorded successfully');
        } else {
          await fetchTraces(true);
        }
      }
    } catch {
      showToast('❌ Failed to trigger Run A');
    } finally {
      setIsTriggering(false);
      setTimeout(() => setIsStreaming(false), 1500);
      fetchStatus();
    }
  };

  // Action: Run B
  const handleRunB = async () => {
    setIsTriggering(true);
    setIsStreaming(true);
    showToast('🌐 Launching Run B: compose(goto, avoid) with Bright Data...');
    try {
      const res = await fetch('/api/traces/demo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ run: 'B' }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.trace) {
          setTraces((prev) => [data.trace, ...prev]);
          setSelectedTraceId(data.trace.trace_id);
          setSelectedSpanId(null);
          showToast('✅ Run B & Bright Data enrichment recorded');
        } else {
          await fetchTraces(true);
        }
      }
    } catch {
      showToast('❌ Failed to trigger Run B');
    } finally {
      setIsTriggering(false);
      setTimeout(() => setIsStreaming(false), 1500);
      fetchStatus();
    }
  };

  // Action: Clear
  const handleClear = async () => {
    try {
      await fetch('/api/traces/clear', { method: 'POST' });
      setTraces([]);
      setSelectedTraceId(null);
      setSelectedSpanId(null);
      fetchStatus();
      showToast('🧹 All recorded spans cleared');
    } catch {
      showToast('❌ Failed to clear traces');
    }
  };

  // Action: Refresh
  const handleRefresh = async () => {
    showToast('⟳ Refreshing telemetry...');
    await Promise.all([fetchStatus(), fetchTraces(false)]);
  };

  // Keyboard hotkeys
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't intercept when typing in an input
      if (
        ['INPUT', 'TEXTAREA', 'SELECT'].includes(
          (e.target as HTMLElement)?.tagName
        )
      ) {
        return;
      }

      if (e.key === 'a' || e.key === 'A') {
        e.preventDefault();
        handleRunA();
      } else if (e.key === 'b' || e.key === 'B') {
        e.preventDefault();
        handleRunB();
      } else if (e.key === 'r' || e.key === 'R') {
        e.preventDefault();
        handleRefresh();
      } else if (e.key === 'c' || e.key === 'C') {
        e.preventDefault();
        handleClear();
      } else if (e.key === 'Escape') {
        setSelectedSpanId(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleRunA, handleRunB, handleRefresh, handleClear]);

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-obsidian-950 font-sans text-slate-100">
      {/* Background HUD Grid & Ambient Scanlines */}
      <div className="hud-grid-overlay" aria-hidden="true" />
      <div className="hud-scanlines" aria-hidden="true" />

      {/* Top Telemetry Header */}
      <Header
        status={status}
        totalTraces={status?.total_traces ?? traces.length}
        totalSpans={
          status?.total_spans ??
          traces.reduce((acc, t) => acc + t.span_count, 0)
        }
        latestOp={latestOp}
        isTriggering={isTriggering}
        onRunA={handleRunA}
        onRunB={handleRunB}
        onRefresh={handleRefresh}
        onClear={handleClear}
      />

      {/* Workspace Area: Sidebar + Main Stage */}
      <main className="relative z-10 flex flex-1 overflow-hidden">
        {/* Left Flight Log Sidebar */}
        <Sidebar
          traces={traces}
          selectedTraceId={selectedTraceId}
          onSelectTrace={(id) => {
            setSelectedTraceId(id);
            setSelectedSpanId(null);
          }}
          filter={filter}
          onFilterChange={setFilter}
          isStreaming={isStreaming}
          utcTime={utcTime}
        />

        {/* Center Main Stage */}
        <section className="relative flex flex-1 flex-col overflow-hidden bg-obsidian-950">
          {!activeTrace ? (
            <EmptyState onRunA={handleRunA} onRunB={handleRunB} />
          ) : viewMode === 'waterfall' ? (
            <WaterfallTimeline
              trace={activeTrace}
              selectedSpanId={selectedSpanId}
              onSelectSpan={setSelectedSpanId}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
            />
          ) : viewMode === 'flame' ? (
            <div className="flex flex-1 flex-col overflow-hidden">
              <WaterfallTimeline
                trace={activeTrace}
                selectedSpanId={selectedSpanId}
                onSelectSpan={setSelectedSpanId}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
              />
              <FlameGraph
                trace={activeTrace}
                selectedSpanId={selectedSpanId}
                onSelectSpan={setSelectedSpanId}
              />
            </div>
          ) : (
            <div className="flex flex-1 flex-col overflow-hidden">
              <WaterfallTimeline
                trace={activeTrace}
                selectedSpanId={selectedSpanId}
                onSelectSpan={setSelectedSpanId}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
              />
              <RawJsonView trace={activeTrace} />
            </div>
          )}
        </section>

        {/* Right Slide-in Span Inspector Drawer */}
        {selectedSpanId && activeSpan && (
          <SpanInspector
            span={activeSpan}
            trace={activeTrace}
            onClose={() => setSelectedSpanId(null)}
          />
        )}
      </main>

      {/* Toast HUD Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-lg border border-hud-cyan/40 bg-obsidian-900/95 px-4 py-2.5 font-mono text-xs text-slate-100 shadow-glow-cyan backdrop-blur-md animate-in fade-in slide-in-from-bottom-3 duration-200">
          <span className="h-2 w-2 rounded-full bg-hud-cyan animate-ping" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}
