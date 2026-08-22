import { TraceTree, SpanNode, SpanEvent } from './types';

let mockTracesStore: TraceTree[] = [];

export function generateCanonicalTrace(runType: 'A' | 'B' = 'A'): TraceTree {
  const isRunB = runType === 'B';
  const nowNs = Date.now() * 1_000_000;
  const traceId = Array.from({ length: 32 }, () =>
    Math.floor(Math.random() * 16).toString(16)
  ).join('');

  const makeSpanId = () =>
    Array.from({ length: 16 }, () =>
      Math.floor(Math.random() * 16).toString(16)
    ).join('');

  const rootSpanId = makeSpanId();
  let currentOffsetMs = 0;
  const spans: SpanNode[] = [];
  const events: SpanEvent[] = [];

  const primitive = isRunB ? 'compose(goto, avoid)' : 'goto';
  const rootTitle = isRunB
    ? 'Demo Run B: compose(goto, avoid)'
    : 'Demo Run A: goto';

  // Helper to add span
  const addStep = (
    name: string,
    durationMs: number,
    attrs: Record<string, any>,
    stepEvents: { name: string; offsetFromStartMs?: number; attrs: Record<string, any> }[] = []
  ) => {
    const spanId = makeSpanId();
    const startOffsetMs = currentOffsetMs;
    const startNs = nowNs + Math.round(startOffsetMs * 1_000_000);
    const endNs = startNs + Math.round(durationMs * 1_000_000);

    const spanEvts: SpanEvent[] = [];
    stepEvents.forEach((se) => {
      const evOffset = startOffsetMs + (se.offsetFromStartMs ?? durationMs * 0.5);
      const evObj: SpanEvent = {
        name: se.name,
        span_id: spanId,
        span_name: name,
        timestamp_ns: nowNs + Math.round(evOffset * 1_000_000),
        offset_ms: Math.round(evOffset * 100) / 100,
        percent_offset: 0, // will compute after total
        attributes: se.attrs,
      };
      events.push(evObj);
      spanEvts.push(evObj);
    });

    const node: SpanNode = {
      name,
      trace_id: traceId,
      span_id: spanId,
      parent_id: rootSpanId,
      start_time_ns: startNs,
      end_time_ns: endNs,
      duration_ms: Math.round(durationMs * 100) / 100,
      offset_ms: Math.round(startOffsetMs * 100) / 100,
      percent_start: 0,
      percent_width: 0,
      attributes: attrs,
      events: spanEvts,
      status: { code: 'OK', description: 'Execution succeeded' },
      children: [],
      depth: 1,
    };

    spans.push(node);
    currentOffsetMs += durationMs + 8; // Small inter-span pipeline delay
    return node;
  };

  // 1. Detect
  addStep(
    'detect',
    64.5,
    {
      'camera.fps': 30.0,
      'camera.resolution': '1280x720',
      'camera.backend': 'v4l2_so101',
      cube_detected: true,
      cube_area_px: 1480,
      cube_centroid_xy: [640, 360],
      tag_count: 1,
    },
    isRunB
      ? [
          {
            name: 'obstacle_detected',
            offsetFromStartMs: 32.0,
            attrs: {
              color: 'blue',
              contour_area_px: 3420,
              label: 'bottle',
              confidence: 0.96,
            },
          },
        ]
      : []
  );

  // 2. Tag Pose
  addStep('tag_pose', 42.1, {
    'tag.family': 'tag36h11',
    'tag.size_cm': 6.5,
    'tag.seen': true,
    'tag.distance_m': 0.72,
    'tag.rotation_euler_deg': [0.4, -1.2, 89.5],
    'reprojection_error_px': 0.18,
  });

  // 3. Update Twin
  addStep(
    'update_twin',
    95.4,
    {
      'twin.prompt_state': 'RECORDING',
      'twin.target_body': 'cube',
      'twin.drift_compensation_mm': 0.2,
      'twin.step_hz': 500,
      'twin.physics_engine': 'MuJoCo 3.2.0',
    },
    [
      {
        name: 'physical_prompt',
        offsetFromStartMs: 82.0,
        attrs: {
          recording_s: 8.14,
          bag_frames: 244,
          prompt_state: 'PROMPTED',
          target_square: 'back_right',
          obstacle: isRunB,
          trajectory_variance_mm: 0.85,
        },
      },
    ]
  );

  // 4. Extract Params
  addStep('extract_params', 58.2, {
    extractor: 'waypoint_fast_path',
    input_bag: 'bag_20260822_01.npz',
    waypoints_count: 48,
    smoothness_metric: 0.984,
    temporal_delta_ms: 16.6,
  });

  // 5. Scrape (Bright Data)
  if (isRunB) {
    addStep('scrape', 184.6, {
      sponsor: 'Bright Data',
      catalog_url:
        'https://www.ikea.com/us/en/p/ikea-365-water-bottle-dark-gray-70478228/',
      item_name: 'IKEA 365+ water bottle',
      width_cm: 7.0,
      height_cm: 24.0,
      weight_g: 120.0,
      material: 'plastic',
      density_kg_m3: 950.0,
      friction: 0.35,
      mass_defaulted: false,
      cached: false,
      geom: 'cylinder',
      'brightdata.proxy': 'lum-customer-hl-zone-datacenter',
      'brightdata.latency_ms': 184.2,
      'brightdata.status': 200,
    });
  } else {
    addStep('scrape', 12.0, {
      sponsor: 'Bright Data',
      status: 'bypassed_for_goto',
      required: false,
      reason: 'Standard target cube geometry already parameterized',
    });
  }

  // 6. Patch Spec
  const stepsSpec = isRunB
    ? [
        {
          op: 'replay_trajectory',
          path: [
            [0.0, 0.0, 0.0],
            [0.28, 0.18, 2.0],
          ],
        },
        {
          op: 'avoid',
          at: [-0.12, 0.05],
          geom: 'cylinder',
          width_cm: 7.0,
          height_cm: 24.0,
          weight_g: 120.0,
          material: 'plastic',
        },
      ]
    : [
        {
          op: 'goto',
          start: [0.0, 0.0],
          end: [0.28, 0.18],
          duration_s: 2.0,
        },
      ];

  addStep('patch_spec', 72.8, {
    spec_version: 2,
    ops: primitive,
    hot_swap_strategy: 'lockless_atomic_swap',
    spec_json: JSON.stringify(stepsSpec, null, 2),
    active_controller: 'bidex_cartesian_impedance',
  });

  // 7. Test Gate
  addStep('test', 110.3, {
    test_gate: 'replay_bag_exam',
    collision_free: true,
    max_error_cm: 0.38,
    result: 'PASS',
    sim_fidelity_score: 0.994,
    boundary_clearance_cm: 4.2,
  });

  // 8. Approve
  addStep(
    'approve',
    34.7,
    {
      gate: 'fast_path_auto_approval',
      operator: 'autonomous_verifier',
      latency_ms: 34.7,
      confidence_threshold: 0.95,
      actual_confidence: 0.994,
      safety_interlock: 'CLEAR',
    },
    [
      {
        name: 'release',
        offsetFromStartMs: 28.0,
        attrs: {
          hot_swap: true,
          zero_downtime: true,
          spec_version: 2,
          twin_state: 'UNINTERRUPTED',
          switchover_latency_us: 120,
        },
      },
    ]
  );

  // 9. Port run sync
  addStep('port_sync', 48.0, {
    integration: 'Port',
    result: 'synced',
    entity_flow: 'physical_prompt → change_request → factory_run → approval → twin_release',
    blocking: false,
  }, [
    {
      name: 'port_entities_upserted',
      offsetFromStartMs: 38.0,
      attrs: { blueprints: isRunB ? 6 : 5, board: 'Bidex physical prompts' },
    },
  ]);

  // 10. Skill Execution
  addStep('skill_exec', 280.0, {
    engine: 'mujoco_so101',
    duration_s: 2.2,
    trajectory_fidelity: 0.998,
    status: 'COMPLETED',
    peak_torque_nm: 1.42,
    final_placement_error_mm: 0.45,
  });

  const totalDurationMs = currentOffsetMs;
  const rootNode: SpanNode = {
    name: 'flight_recorder',
    trace_id: traceId,
    span_id: rootSpanId,
    parent_id: null,
    start_time_ns: nowNs,
    end_time_ns: nowNs + Math.round(totalDurationMs * 1_000_000),
    duration_ms: Math.round(totalDurationMs * 100) / 100,
    offset_ms: 0,
    percent_start: 0,
    percent_width: 100,
    attributes: {
      'service.name': 'bidex',
      'run.name': rootTitle,
      'run.primitive': primitive,
      'run.mode': 'fast_path',
      'table.tag_id': 0,
      zero_downtime: 'true',
      version: '2.4.0',
    },
    events: [],
    status: { code: 'OK', description: 'Run completed successfully' },
    children: [...spans],
    depth: 0,
  };

  // Recalculate percent offsets & widths
  spans.forEach((s) => {
    s.percent_start =
      totalDurationMs > 0
        ? Math.round((s.offset_ms / totalDurationMs) * 1000) / 10
        : 0;
    s.percent_width =
      totalDurationMs > 0
        ? Math.max(0.6, Math.round((s.duration_ms / totalDurationMs) * 1000) / 10)
        : 100;
  });

  events.forEach((e) => {
    e.percent_offset =
      totalDurationMs > 0
        ? Math.round((e.offset_ms / totalDurationMs) * 1000) / 10
        : 0;
  });

  const flatSpans = [rootNode, ...spans];

  const traceTree: TraceTree = {
    trace_id: traceId,
    root_name: rootTitle,
    run_name: rootTitle,
    span_count: flatSpans.length,
    event_count: events.length,
    start_time_ns: nowNs,
    end_time_ns: nowNs + Math.round(totalDurationMs * 1_000_000),
    total_duration_ms: Math.round(totalDurationMs * 100) / 100,
    events: events,
    root_spans: [rootNode],
    flat_spans: flatSpans,
  };

  return traceTree;
}

export function getCachedTraces(): TraceTree[] {
  if (mockTracesStore.length === 0) {
    // Generate an initial Run B and Run A so the UI looks spectacular on first load
    const runB = generateCanonicalTrace('B');
    const runA = generateCanonicalTrace('A');
    mockTracesStore = [runB, runA];
  }
  return mockTracesStore;
}

export function addCachedTrace(trace: TraceTree) {
  mockTracesStore.unshift(trace);
  if (mockTracesStore.length > 50) {
    mockTracesStore.pop();
  }
}

export function clearCachedTraces() {
  mockTracesStore = [];
}
