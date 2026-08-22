export type ViewMode = 'waterfall' | 'flame' | 'json';
export type FilterType = 'all' | 'run_a' | 'run_b';

export interface SpanEvent {
  name: string;
  span_id?: string;
  span_name?: string;
  timestamp_ns: number;
  offset_ms: number;
  percent_offset: number;
  attributes: Record<string, any>;
}

export interface SpanStatus {
  code: 'OK' | 'ERROR' | 'UNSET' | string;
  description?: string;
}

export interface SpanNode {
  name: string;
  trace_id: string;
  span_id: string;
  parent_id: string | null;
  start_time_ns: number;
  end_time_ns: number;
  duration_ms: number;
  offset_ms: number;
  percent_start: number;
  percent_width: number;
  attributes: Record<string, any>;
  events: SpanEvent[];
  status: SpanStatus;
  depth?: number;
  children: SpanNode[];
}

export interface TraceTree {
  trace_id: string;
  root_name: string;
  run_name: string;
  span_count: number;
  event_count: number;
  start_time_ns: number;
  end_time_ns: number;
  total_duration_ms: number;
  events: SpanEvent[];
  root_spans: SpanNode[];
  flat_spans: SpanNode[];
}

export interface BackendStatus {
  service: string;
  tracer_mode: 'local' | string;
  port_ready: boolean;
  brightdata_ready: boolean;
  total_spans: number;
  total_traces: number;
}

/* --- Live ops: the headless twin and the camera feed ---------------------- */

export type TwinSource = 'idle' | 'camera' | 'skill';
export type TwinView = 'operator' | 'overhead' | 'front' | 'wide' | string;
export type PromptState = 'IDLE' | 'RECORDING' | 'PROMPTED' | string;
export type WorkspaceTab = 'live' | 'recorder';

export interface TwinState {
  running: boolean;
  error: string | null;
  source: TwinSource;
  view: TwinView;
  sim_time: number;
  cube_xy: [number, number] | number[];
  ee_xyz: [number, number, number] | number[] | null;
  skill_op: string | null;
  skill_step: number;
  skill_steps: number;
  skill_finished: boolean;
  spec_version: number | null;
  hot_swaps: number;
  /* Which rung of the geometry ladder the obstacle came from: 1 the product's
     own AR mesh, 2 a mesh found on the wider 3D web, 3 the primitive cylinder. */
  mesh_rung: number;
  mesh_label: string;
  mesh_source: string | null;
  mesh_swaps: number;
  render_fps: number;
  frames: number;
  views: string[];
  spec_path: string | null;
}

export interface CameraState {
  running: boolean;
  error: string | null;
  tag_seen: boolean;
  cube_xy: [number, number] | number[] | null;
  raw_xy: [number, number] | number[] | null;
  surface: string;
  latency_ms: number;
  fps: number;
  width: number;
  height: number;
  frames: number;
  prompt_state: PromptState;
}

export interface LiveState {
  backend_online: boolean;
  twin: TwinState;
  camera: CameraState;
  views: string[];
  apriltag_size_cm: string | null;
  camera_index: number;
  tracer_mode: string;
  port_ready: boolean;
  brightdata_ready: boolean;
}
