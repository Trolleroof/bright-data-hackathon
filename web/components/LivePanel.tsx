'use client';

import { useEffect, useState } from 'react';
import { Camera, RefreshCw, ScanLine } from 'lucide-react';

const backend = 'http://127.0.0.1:8080';

export function LivePanel() {
  const [live, setLive] = useState<{ running: boolean; error?: string | null; tag_seen?: boolean; cube_xy?: [number, number] | null; synced_xy?: [number, number] | null; fps?: number }>({ running: false });
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const refresh = async () => {
    try { setLive(await fetch(`${backend}/api/live/status`, { cache: 'no-store' }).then((r) => r.json())); }
    catch { setLive({ running: false, error: 'Start the local server to use live view.' }); }
  };
  useEffect(() => {
    refresh();
    const statusTimer = window.setInterval(refresh, 1000);
    return () => window.clearInterval(statusTimer);
  }, []);
  const start = async () => { setLive(await fetch(`${backend}/api/live/start`, { method: 'POST' }).then((r) => r.json())); };
  const sync = async () => {
    try {
      const data = await fetch(`${backend}/api/live/sync`, { method: 'POST' }).then((r) => r.json());
      setLive(data);
      setSyncMessage(data.synced ? `Twin synced to ${data.synced_xy[0].toFixed(3)}, ${data.synced_xy[1].toFixed(3)} m` : data.error || 'Sync failed.');
    } catch { setSyncMessage('Twin server is unreachable.'); }
  };

  return <section className="border-b border-obsidian-800 bg-obsidian-900 px-5 py-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3"><div><p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Live workspace</p><h2 className="text-base font-semibold text-white">Camera → digital twin</h2></div><div className="flex gap-2"><button onClick={start} className="flex items-center gap-2 rounded-md bg-white px-3 py-2 text-xs font-semibold text-slate-950"><Camera className="h-3.5 w-3.5" /> Start camera</button><button disabled={!live.running} onClick={sync} className="flex items-center gap-2 rounded-md border border-obsidian-700 px-3 py-2 text-xs font-semibold text-slate-200 disabled:opacity-40"><ScanLine className="h-3.5 w-3.5" /> Sync cube</button></div></div>
    {live.error ? <p className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">{live.error}</p> : <><div className="grid gap-3 lg:grid-cols-2"><Feed title="Camera" src={`${backend}/api/live/camera.mjpg`} ready={live.running} /><Feed title="MuJoCo twin" src={`${backend}/api/live/sim.mjpg`} ready={live.running} /></div><p className="mt-2 font-mono text-[10px] text-slate-500">{live.running ? `${live.tag_seen ? 'tag found' : 'tag not found'} · ${live.cube_xy ? `${live.cube_xy[0].toFixed(3)}, ${live.cube_xy[1].toFixed(3)} m` : 'cube unavailable'} · ${live.fps ?? 0} fps` : 'Camera is off. Starting it requests macOS camera access.'}</p>{syncMessage && <p className={`mt-2 text-xs ${live.synced_xy ? 'text-emerald-300' : 'text-amber-300'}`}>{syncMessage}</p>}</>}
  </section>;
}

function Feed({ title, src, ready }: { title: string; src: string; ready: boolean }) {
  return <div className="overflow-hidden rounded-md border border-obsidian-800 bg-obsidian-950"><div className="flex items-center justify-between border-b border-obsidian-800 px-3 py-2"><span className="text-xs font-medium text-slate-200">{title}</span><RefreshCw className="h-3 w-3 text-slate-600" /></div>{ready ? <img className="aspect-video w-full object-cover" src={src} alt={`${title} live feed`} /> : <div className="flex aspect-video items-center justify-center text-xs text-slate-600">Not running</div>}</div>;
}
