'use client';

import { useCallback, useState } from 'react';
import { Camera, Circle, Loader2, Play, RefreshCw, Square } from 'lucide-react';
import { LiveState } from '@/lib/types';
import { ImportPrompt } from '@/components/ImportPrompt';
import { MjpegFeed } from '@/components/MjpegFeed';

interface Props {
  live: LiveState | null;
  onToast: (message: string) => void;
  onRefresh: () => void;
}

export function LiveOps({ live, onToast, onRefresh }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [reconnect, setReconnect] = useState(0);

  const control = useCallback(async (body: Record<string, unknown>, label: string) => {
    setBusy(label);
    try {
      const response = await fetch('/api/live/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || `${label} failed`);
      if (result.camera?.error) throw new Error(result.camera.error);
      if (result.twin?.error) throw new Error(result.twin.error);
      onToast(label);
      setReconnect((value) => value + 1);
    } catch (error) {
      onToast(error instanceof Error ? error.message : `${label} failed`);
    } finally {
      setBusy(null);
      onRefresh();
    }
  }, [onRefresh, onToast]);

  if (!live) return <section className="p-5 text-sm text-slate-500">Connecting to the local backend…</section>;
  if (!live.backend_online) return <section className="m-5 rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">Start <code>python web/server.py</code> to use the camera and twin.</section>;

  const { twin, camera } = live;
  const sync = () => control(
    { target: 'twin', action: twin.running ? 'configure' : 'start', source: 'camera' },
    camera.tag_seen ? 'Twin is following the camera cube' : 'Camera started; show AprilTag 0 to sync the cube'
  );
  const runSkill = async () => {
    await control({ target: 'twin', action: twin.running ? 'configure' : 'start', source: 'skill' }, 'Skill source selected');
    await control({ target: 'twin', action: 'reset' }, 'Skill replay started');
  };
  const record = (skill: 'A' | 'B') => control(
    { target: 'camera', action: 'record', skill },
    camera.prompt_state === 'RECORDING' ? `Skill ${camera.recording_skill} recording stopped` : `Skill ${skill} recording started`
  );

  return <section className="border-b border-obsidian-800 p-5">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Live workspace</p>
        <h2 className="mt-1 text-lg font-semibold text-white">Camera → digital twin</h2>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Twin camera view"
          value={twin.view}
          onChange={(event) => control({ target: 'twin', action: 'configure', view: event.target.value }, `View changed to ${event.target.value}`)}
          className="rounded-md border border-obsidian-700 bg-obsidian-900 px-3 py-2 text-xs text-slate-200"
        >
          {live.views.map((view) => <option key={view} value={view}>{view}</option>)}
        </select>
        <button disabled={busy !== null} onClick={sync} className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50">
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Camera className="h-3.5 w-3.5" />} Sync camera
        </button>
        <button disabled={busy !== null} onClick={runSkill} className="flex items-center gap-2 rounded-md border border-obsidian-700 px-3 py-2 text-xs font-semibold text-slate-100 disabled:opacity-50"><Play className="h-3.5 w-3.5" /> Run skill</button>
        {camera.prompt_state === 'RECORDING' ? <button disabled={busy !== null} onClick={() => record(camera.recording_skill || 'A')} className="flex items-center gap-2 rounded-md border border-red-400/60 px-3 py-2 text-xs font-semibold text-red-200 disabled:opacity-50"><Square className="h-3.5 w-3.5" /> Stop Skill {camera.recording_skill}</button> : <>
          <button disabled={busy !== null} onClick={() => record('A')} className="flex items-center gap-2 rounded-md border border-obsidian-700 px-3 py-2 text-xs font-semibold text-slate-100 disabled:opacity-50"><Circle className="h-3.5 w-3.5" /> Record Skill A</button>
          <button disabled={busy !== null} onClick={() => record('B')} className="flex items-center gap-2 rounded-md border border-amber-400/60 px-3 py-2 text-xs font-semibold text-amber-200 disabled:opacity-50"><Circle className="h-3.5 w-3.5" /> Record Skill B</button>
        </>}
        <button disabled={busy !== null} onClick={() => control({ target: 'twin', action: 'reset' }, 'Twin reset')} className="p-2 text-slate-500 hover:text-white" aria-label="Reset twin"><RefreshCw className="h-4 w-4" /></button>
      </div>
    </div>

    {live.object_import && <ImportPrompt state={live.object_import} onToast={onToast} onRefresh={onRefresh} />}

    <div className="grid gap-3 lg:grid-cols-2">
      <MjpegFeed src="/api/camera/stream" label="Camera" active={camera.running} idleMessage="Click Sync camera to start" error={camera.error} reconnectKey={reconnect} className="aspect-video" />
      <MjpegFeed src="/api/sim/stream" label="MuJoCo twin" active={twin.running} idleMessage="Click Sync camera or Run skill to start" error={twin.error} reconnectKey={reconnect} className="aspect-video" />
    </div>

    <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[11px] text-slate-500">
      <span>camera {camera.fps.toFixed(1)} fps</span>
      <span className={camera.tag_seen ? 'text-emerald-300' : 'text-amber-300'}>{camera.tag_seen ? 'tag locked' : 'tag not seen'}</span>
      <span>twin {twin.render_fps.toFixed(1)} fps</span>
      <span>source {twin.source}</span>
      <span>{camera.prompt_state === 'RECORDING' ? `recording Skill ${camera.recording_skill}` : camera.prompt_state === 'PROMPTED' ? 'recording saved; factory started' : 'ready to record'}</span>
      <span>cube {twin.cube_xy[0].toFixed(3)}, {twin.cube_xy[1].toFixed(3)} m</span>
      <span>{camera.detection ? `sees ${camera.detection.label}` : 'no extra object'}</span>
      <span>{twin.mesh_label}</span>
    </div>
  </section>;
}
