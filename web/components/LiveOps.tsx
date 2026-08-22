'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Camera,
  CircleSlash,
  Crosshair,
  Play,
  Power,
  RotateCcw,
  ServerCrash,
  Video,
} from 'lucide-react';
import { MjpegFeed } from '@/components/MjpegFeed';
import { TableMap } from '@/components/TableMap';
import { LiveState, TwinSource } from '@/lib/types';
import { cn } from '@/lib/utils';

const SOURCES: { id: TwinSource; label: string; hint: string }[] = [
  { id: 'camera', label: 'TRACK_CUBE', hint: 'camera drives the cube' },
  { id: 'skill', label: 'SKILL ENGINE', hint: 'replay outputs/skill_spec.json' },
  { id: 'idle', label: 'IDLE', hint: 'physics only' },
];

interface LiveOpsProps {
  live: LiveState | null;
  onToast: (message: string) => void;
  onRefresh: () => void;
}

const Readout: React.FC<{
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'bad' | 'warn';
}> = ({ label, value, tone = 'default' }) => (
  <div className="rounded border border-obsidian-800 bg-obsidian-900/60 px-3 py-2">
    <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-obsidian-600">
      {label}
    </div>
    <div
      className={cn(
        'mt-0.5 truncate font-mono text-sm',
        tone === 'good' && 'text-hud-emerald',
        tone === 'bad' && 'text-hud-ruby',
        tone === 'warn' && 'text-hud-amber',
        tone === 'default' && 'text-slate-200'
      )}
      title={value}
    >
      {value}
    </div>
  </div>
);

export const LiveOps: React.FC<LiveOpsProps> = ({ live, onToast, onRefresh }) => {
  const [busy, setBusy] = useState<string | null>(null);
  const [reconnect, setReconnect] = useState(0);

  const control = useCallback(
    async (body: Record<string, unknown>, note: string) => {
      setBusy(note);
      try {
        const res = await fetch('/api/live/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          onToast(`⚠ ${data.error ?? note + ' failed'}`);
        } else {
          onToast(`✅ ${note}`);
          setReconnect((n) => n + 1);
        }
      } catch {
        onToast(`⚠ ${note} failed — is web/server.py running?`);
      } finally {
        setBusy(null);
        onRefresh();
      }
    },
    [onToast, onRefresh]
  );

  // Boot the twin automatically the first time the live tab is opened with a
  // reachable backend: judges should not have to press play to see the world.
  const twinRunning = live?.twin.running ?? false;
  const backendOnline = live?.backend_online ?? false;
  useEffect(() => {
    if (backendOnline && !twinRunning && busy === null) {
      control({ target: 'twin', action: 'start', source: 'skill' }, 'twin online');
    }
    // Runs once per transition into "backend up but twin down".
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendOnline, twinRunning]);

  if (!live) {
    return (
      <div className="flex flex-1 items-center justify-center font-mono text-sm text-slate-500">
        connecting to live services…
      </div>
    );
  }

  const { twin, camera } = live;

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      {!live.backend_online && (
        <div className="flex items-center gap-3 rounded-lg border border-hud-amber/40 bg-hud-amber-dim px-4 py-3">
          <ServerCrash className="h-5 w-5 shrink-0 text-hud-amber" />
          <div className="font-mono text-xs leading-relaxed text-hud-amber">
            Live backend offline. The twin render and the camera feed both come
            from the Python service — start it with{' '}
            <code className="rounded bg-obsidian-950/70 px-1.5 py-0.5 text-slate-200">
              python web/server.py --twin --camera
            </code>
          </div>
        </div>
      )}

      {/* Control rail */}
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-obsidian-800 bg-obsidian-900/70 p-2.5">
        <span className="px-1 font-mono text-[10px] uppercase tracking-[0.2em] text-obsidian-600">
          cube source
        </span>
        {SOURCES.map((source) => (
          <button
            key={source.id}
            type="button"
            title={source.hint}
            disabled={busy !== null}
            onClick={() =>
              control(
                { target: 'twin', action: 'configure', source: source.id },
                `twin source → ${source.label}`
              )
            }
            className={cn(
              'rounded border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40',
              twin.source === source.id
                ? 'border-hud-cyan/60 bg-hud-cyan-dim text-hud-cyan'
                : 'border-obsidian-700 text-slate-400 hover:border-obsidian-600 hover:text-slate-200'
            )}
          >
            {source.label}
          </button>
        ))}

        <span className="mx-1 h-5 w-px bg-obsidian-800" />

        <span className="px-1 font-mono text-[10px] uppercase tracking-[0.2em] text-obsidian-600">
          view
        </span>
        {(live.views.length ? live.views : ['operator']).map((view) => (
          <button
            key={view}
            type="button"
            disabled={busy !== null}
            onClick={() =>
              control({ target: 'twin', action: 'configure', view }, `view → ${view}`)
            }
            className={cn(
              'rounded border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors disabled:opacity-40',
              twin.view === view
                ? 'border-hud-violet/60 bg-hud-violet-dim text-hud-violet'
                : 'border-obsidian-700 text-slate-400 hover:border-obsidian-600 hover:text-slate-200'
            )}
          >
            {view}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              control({ target: 'twin', action: 'reset' }, 'twin reset to t=0')
            }
            className="flex items-center gap-1.5 rounded border border-obsidian-700 px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-widest text-slate-300 hover:border-hud-cyan/50 hover:text-hud-cyan disabled:opacity-40"
          >
            <RotateCcw className="h-3 w-3" /> replay
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              control(
                {
                  target: 'twin',
                  action: twin.running ? 'stop' : 'start',
                  source: twin.source,
                },
                twin.running ? 'twin stopped' : 'twin online'
              )
            }
            className={cn(
              'flex items-center gap-1.5 rounded border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-widest disabled:opacity-40',
              twin.running
                ? 'border-hud-ruby/50 text-hud-ruby hover:bg-hud-ruby/10'
                : 'border-hud-emerald/50 text-hud-emerald hover:bg-hud-emerald/10'
            )}
          >
            {twin.running ? <Power className="h-3 w-3" /> : <Play className="h-3 w-3" />}
            {twin.running ? 'stop twin' : 'start twin'}
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() =>
              control(
                { target: 'camera', action: camera.running ? 'stop' : 'start' },
                camera.running ? 'camera stopped' : 'camera online'
              )
            }
            className={cn(
              'flex items-center gap-1.5 rounded border px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-widest disabled:opacity-40',
              camera.running
                ? 'border-hud-ruby/50 text-hud-ruby hover:bg-hud-ruby/10'
                : 'border-hud-cyan/50 text-hud-cyan hover:bg-hud-cyan/10'
            )}
          >
            {camera.running ? <CircleSlash className="h-3 w-3" /> : <Camera className="h-3 w-3" />}
            {camera.running ? 'stop camera' : 'start camera'}
          </button>
        </div>
      </div>

      {/* Viewports */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="flex flex-col gap-3 xl:col-span-2">
          <MjpegFeed
            src="/api/sim/stream"
            label="MuJoCo twin"
            active={twin.running}
            idleMessage="twin is not running"
            error={twin.error}
            reconnectKey={reconnect}
            className="h-[clamp(260px,46vh,620px)] shrink-0"
          />
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Readout
              label="source"
              value={twin.source}
              tone={twin.source === 'idle' ? 'warn' : 'good'}
            />
            <Readout label="sim time" value={`${twin.sim_time.toFixed(2)} s`} />
            <Readout label="render" value={`${twin.render_fps.toFixed(1)} fps`} />
            <Readout
              label="cube (world)"
              value={`${twin.cube_xy[0].toFixed(3)}, ${twin.cube_xy[1].toFixed(3)} m`}
            />
            <Readout
              label="skill step"
              value={
                twin.skill_steps
                  ? `${Math.min(twin.skill_step + 1, twin.skill_steps)}/${twin.skill_steps}${
                      twin.skill_finished ? ' · done' : ''
                    }`
                  : '—'
              }
            />
            <Readout label="primitive" value={twin.skill_op ?? '—'} />
            <Readout
              label="hot swaps"
              value={String(twin.hot_swaps)}
              tone={twin.hot_swaps > 0 ? 'good' : 'default'}
            />
            <Readout
              label="ee cursor"
              value={
                twin.ee_xyz
                  ? `${twin.ee_xyz[0].toFixed(2)}, ${twin.ee_xyz[1].toFixed(2)}, ${twin.ee_xyz[2].toFixed(2)}`
                  : '—'
              }
            />
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <MjpegFeed
            src="/api/camera/stream"
            label="track_cube"
            active={camera.running}
            idleMessage="camera is not running"
            error={
              camera.error ??
              (live.apriltag_size_cm
                ? null
                : 'APRILTAG_SIZE_CM is unset in .env — measure the outer black square of the printed tag.')
            }
            reconnectKey={reconnect}
            className="h-[clamp(180px,26vh,340px)] shrink-0"
          />
          <div className="grid grid-cols-2 gap-2">
            <Readout
              label="tag 0"
              value={camera.tag_seen ? 'LOCKED' : 'not seen'}
              tone={camera.tag_seen ? 'good' : 'bad'}
            />
            <Readout label="surface" value={camera.surface} />
            <Readout label="latency" value={`${camera.latency_ms.toFixed(1)} ms`} />
            <Readout label="capture" value={`${camera.fps.toFixed(1)} fps`} />
            <Readout
              label="cube (tag frame)"
              value={
                camera.cube_xy
                  ? `${camera.cube_xy[0].toFixed(3)}, ${camera.cube_xy[1].toFixed(3)} m`
                  : '—'
              }
              tone={camera.cube_xy ? 'default' : 'warn'}
            />
            <Readout label="prompt" value={camera.prompt_state} />
          </div>

          <div className="rounded-lg border border-obsidian-800 bg-obsidian-900/70 p-3">
            <div className="mb-2 flex items-center gap-2">
              <Crosshair className="h-3.5 w-3.5 text-hud-cyan" />
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                table map
              </span>
            </div>
            <div className="aspect-[4/3] w-full overflow-hidden rounded border border-obsidian-800">
              <TableMap
                twinCube={twin.cube_xy}
                cameraCube={camera.running ? camera.cube_xy : null}
                ee={twin.ee_xyz}
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-3 font-mono text-[9px] uppercase tracking-wider text-obsidian-600">
              <span className="flex items-center gap-1">
                <Box className="h-3 w-3 text-hud-ruby" /> twin cube
              </span>
              <span className="flex items-center gap-1">
                <Video className="h-3 w-3 text-hud-cyan" /> camera read
              </span>
              <span className="flex items-center gap-1">
                <Crosshair className="h-3 w-3 text-hud-blue" /> skill cursor
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
