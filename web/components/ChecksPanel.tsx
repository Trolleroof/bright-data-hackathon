'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  CircleSlash,
  Loader2,
  Play,
  Square,
  Terminal,
  XCircle,
} from 'lucide-react';
import { CheckDefinition, CheckJob, CheckLogLine, CheckResult } from '@/lib/types';
import { cn } from '@/lib/utils';

interface ChecksPanelProps {
  onToast: (msg: string) => void;
}

const POLL_MS = 500;

export const ChecksPanel: React.FC<ChecksPanelProps> = ({ onToast }) => {
  const [open, setOpen] = useState(true);
  const [checks, setChecks] = useState<CheckDefinition[]>([]);
  const [suite, setSuite] = useState<string[]>([]);
  const [job, setJob] = useState<CheckJob | null>(null);
  const [lines, setLines] = useState<CheckLogLine[]>([]);
  const [results, setResults] = useState<CheckResult[]>([]);
  const [offline, setOffline] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const cursorRef = useRef(-1);
  const jobIdRef = useRef<string | null>(null);

  const running = job?.state === 'running';

  // Load the check catalog once.
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/api/checks', { cache: 'no-store' });
        const data = await res.json();
        if (!res.ok) {
          setOffline(true);
          return;
        }
        setChecks(data.checks || []);
        setSuite(data.suite || []);
        setOffline(false);
      } catch {
        setOffline(true);
      }
    })();
  }, []);

  // Keep the log pinned to the newest line.
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines]);

  const poll = useCallback(async () => {
    const id = jobIdRef.current;
    if (!id) return;
    try {
      const res = await fetch(
        `/api/checks/job?id=${encodeURIComponent(id)}&since=${cursorRef.current}`,
        { cache: 'no-store' }
      );
      if (!res.ok) return;
      const data: CheckJob = await res.json();
      cursorRef.current = data.cursor;
      if (data.lines.length) {
        setLines((prev) => [...prev, ...data.lines].slice(-400));
      }
      setResults(data.results);
      setJob(data);
      if (data.state === 'done') {
        jobIdRef.current = null;
        const failed = data.results.filter((r) => !r.passed);
        onToast(
          failed.length === 0
            ? `All ${data.results.length} check(s) passed in ${Math.round(
                (data.duration_ms ?? 0) / 100
              ) / 10}s`
            : `FAIL: ${failed.map((r) => r.label).join(', ')}`
        );
      }
    } catch {
      // transient; the next tick retries
    }
  }, [onToast]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(poll, POLL_MS);
    return () => clearInterval(timer);
  }, [running, poll]);

  const startRun = useCallback(
    async (ids: string[]) => {
      if (jobIdRef.current) return;
      setLines([]);
      setResults([]);
      cursorRef.current = -1;
      setOpen(true);
      try {
        const res = await fetch('/api/checks/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ checks: ids }),
        });
        const data = await res.json();
        if (!res.ok) {
          setOffline(res.status === 503);
          setLines([{ n: 0, stream: 'meta', text: data.error || 'run failed' }]);
          onToast(data.error || 'Run failed');
          return;
        }
        setOffline(false);
        jobIdRef.current = data.job_id;
        setJob(data);
        onToast(`Running ${ids.join(', ')}...`);
      } catch {
        setOffline(true);
        onToast('Check runner unreachable');
      }
    },
    [onToast]
  );

  const cancelRun = useCallback(async () => {
    const id = jobIdRef.current ?? job?.job_id;
    if (!id) return;
    await fetch('/api/checks/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: id }),
    });
    onToast('Cancel signal sent');
  }, [job, onToast]);

  const resultFor = (id: string) => results.find((r) => r.check === id);

  return (
    <div className="relative z-20 border-t border-obsidian-800 bg-obsidian-900/95 backdrop-blur-md">
      {/* Panel header */}
      <div className="flex items-center justify-between gap-3 px-5 py-2">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-2 font-display text-[10px] font-bold tracking-[0.25em] text-hud-cyan"
        >
          <Terminal className="h-3.5 w-3.5" />
          CHECK RUNNER
          <ChevronDown
            className={cn(
              'h-3.5 w-3.5 transition-transform',
              open ? 'rotate-0' : '-rotate-90'
            )}
          />
        </button>

        <div className="flex items-center gap-2">
          {offline && (
            <span className="font-mono text-[10px] text-hud-amber">
              runner offline — start `python web/server.py`
            </span>
          )}
          {running && (
            <button
              onClick={cancelRun}
              className="flex items-center gap-1.5 rounded border border-hud-ruby/40 bg-hud-ruby-dim px-2.5 py-1 font-mono text-[10px] text-hud-ruby hover:bg-hud-ruby/20"
            >
              <Square className="h-3 w-3" />
              STOP
            </button>
          )}
          <button
            onClick={() => startRun(suite)}
            disabled={running || offline || suite.length === 0}
            className="flex items-center gap-1.5 rounded border border-hud-cyan/40 bg-hud-cyan-dim px-3 py-1 font-mono text-[10px] font-bold text-hud-cyan hover:bg-hud-cyan/20 disabled:opacity-40"
          >
            {running ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3 w-3" />
            )}
            RUN ALL
          </button>
        </div>
      </div>

      {open && (
        <div className="flex flex-col gap-3 px-5 pb-4 lg:flex-row">
          {/* Check buttons */}
          <div className="flex w-full shrink-0 flex-col gap-1.5 lg:w-80">
            {checks.map((check) => {
              const result = resultFor(check.id);
              const isCurrent = running && job?.current === check.id;
              return (
                <button
                  key={check.id}
                  onClick={() => check.runnable && startRun([check.id])}
                  disabled={!check.runnable || running}
                  title={check.command}
                  className={cn(
                    'group flex items-center gap-2.5 rounded border px-3 py-2 text-left transition-colors',
                    check.runnable
                      ? 'border-obsidian-800 bg-obsidian-850 hover:border-hud-cyan/40 hover:bg-obsidian-750'
                      : 'border-obsidian-800/60 bg-obsidian-900 opacity-60',
                    isCurrent && 'border-hud-cyan/60 bg-obsidian-750',
                    running && check.runnable && !isCurrent && 'opacity-50'
                  )}
                >
                  <span className="shrink-0">
                    {isCurrent ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-hud-cyan" />
                    ) : !check.runnable ? (
                      <CircleSlash className="h-3.5 w-3.5 text-obsidian-600" />
                    ) : result?.passed ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-hud-emerald" />
                    ) : result ? (
                      <XCircle className="h-3.5 w-3.5 text-hud-ruby" />
                    ) : (
                      <Play className="h-3.5 w-3.5 text-obsidian-600 group-hover:text-hud-cyan" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-mono text-[11px] text-slate-100">
                      {check.label}
                    </span>
                    <span className="block truncate font-mono text-[9px] text-obsidian-600">
                      {check.description}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[9px] text-obsidian-600">
                    {result
                      ? `${Math.round(result.duration_ms)}ms`
                      : check.runnable
                        ? `~${check.expected_s}s`
                        : 'term'}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Live output */}
          <div
            ref={logRef}
            className="h-56 min-w-0 flex-1 overflow-auto rounded border border-obsidian-800 bg-obsidian-950 p-3 font-mono text-[11px] leading-relaxed"
          >
            {lines.length === 0 ? (
              <span className="text-obsidian-600">
                No run yet. Press RUN ALL, or pick a single check on the left.
                Camera checks stay terminal-only.
              </span>
            ) : (
              lines.map((line) => (
                <div
                  key={line.n}
                  className={cn(
                    'whitespace-pre-wrap break-words',
                    line.stream === 'meta'
                      ? line.text.startsWith('PASS')
                        ? 'text-hud-emerald'
                        : line.text.startsWith('FAIL') ||
                            line.text.startsWith('runner error')
                          ? 'text-hud-ruby'
                          : 'text-hud-cyan'
                      : 'text-slate-300'
                  )}
                >
                  {line.text || ' '}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
