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
