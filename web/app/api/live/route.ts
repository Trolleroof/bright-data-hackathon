import { NextResponse } from 'next/server';
import { backendJson } from '@/lib/backend';
import { LiveState } from '@/lib/types';

export const dynamic = 'force-dynamic';

/** Offline shape: same keys the HUD reads, so the UI never branches on null. */
const OFFLINE: LiveState = {
  backend_online: false,
  twin: {
    running: false,
    error: 'backend offline — run: python web/server.py --twin',
    source: 'idle',
    view: 'operator',
    sim_time: 0,
    cube_xy: [0, 0],
    ee_xyz: null,
    skill_op: null,
    skill_step: 0,
    skill_steps: 0,
    skill_finished: false,
    spec_version: null,
    hot_swaps: 0,
    mesh_rung: 0,
    mesh_label: '',
    mesh_source: null,
    mesh_swaps: 0,
    render_fps: 0,
    frames: 0,
    views: [],
    spec_path: null,
  },
  camera: {
    running: false,
    error: 'backend offline — run: python web/server.py --camera',
    tag_seen: false,
    cube_xy: null,
    raw_xy: null,
    surface: '?',
    latency_ms: 0,
    fps: 0,
    width: 0,
    height: 0,
    frames: 0,
    prompt_state: 'IDLE',
    detection: null,
  },
  object_import: {
    status: 'IDLE',
    label: '',
    bbox: [],
    confidence: 0,
    hardcoded: false,
    source: null,
    rung: null,
    detail: '',
    error: null,
    asset: null,
    started_at: null,
    elapsed_ms: null,
  },
  views: ['operator', 'overhead', 'front', 'wide'],
  apriltag_size_cm: null,
  camera_index: 0,
  tracer_mode: 'local',
  port_ready: false,
  brightdata_ready: false,
};

export async function GET() {
  const live = await backendJson<LiveState>('/api/live');
  if (!live) return NextResponse.json(OFFLINE);
  return NextResponse.json({ ...live, backend_online: true });
}
