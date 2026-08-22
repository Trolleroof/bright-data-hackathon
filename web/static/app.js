/**
 * BIDEX FLIGHT RECORDER & TRACE TIMELINE VIEWER
 * High-craft avionics telemetry HUD, waterfall flamechart, and live SSE engine.
 */

(() => {
  'use strict';

  // --- State Management ---
  const state = {
    traces: [],
    selectedTraceId: null,
    selectedSpanId: null,
    filter: 'all', // 'all', 'run_a', 'run_b'
    viewMode: 'waterfall', // 'waterfall', 'flame', 'json'
    serverStatus: null,
    sseConnected: false,
    eventSource: null,
    pollTimer: null,
    clockTimer: null,
    streamPulseTimer: null,
    isStreamingTrace: false,
  };

  // --- Icon & Color Mappings ---
  const SPAN_ICONS = {
    flight_recorder: '⚡',
    detect: '📷',
    tag_pose: '🎯',
    update_twin: '🔄',
    extract_params: '⚙️',
    scrape: '🌐',
    patch_spec: '📝',
    test: '🛡️',
    approve: '💎',
    skill_exec: '▶',
  };

  // --- DOM Elements Cache ---
  const el = {
    // Header & Status
    sseStatusPill: document.getElementById('sse-status-pill'),
    sseStatusText: document.getElementById('sse-status-text'),
    tracerStatusPill: document.getElementById('tracer-status-pill'),
    tracerStatusText: document.getElementById('tracer-status-text'),
    metricTracesCount: document.getElementById('metric-traces-count'),
    metricSpansCount: document.getElementById('metric-spans-count'),
    metricLatestOp: document.getElementById('metric-latest-op'),

    // Buttons
    btnRunA: document.getElementById('btn-run-a'),
    btnRunB: document.getElementById('btn-run-b'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnClear: document.getElementById('btn-clear'),

    // Sidebar
    runsListContainer: document.getElementById('runs-list-container'),
    sidebarRunCount: document.getElementById('sidebar-run-count'),
    filterChips: document.querySelectorAll('.filter-chip'),
    footerSseMsg: document.getElementById('footer-sse-msg'),
    footerClock: document.getElementById('footer-clock'),

    // Trace Banner
    bannerModeTag: document.getElementById('banner-mode-tag'),
    bannerTraceName: document.getElementById('banner-trace-name'),
    bannerTraceId: document.getElementById('banner-trace-id'),
    btnCopyTraceId: document.getElementById('btn-copy-trace-id'),
    bannerDuration: document.getElementById('banner-duration'),
    bannerSpanCount: document.getElementById('banner-span-count'),
    bannerEventCount: document.getElementById('banner-event-count'),
    bannerHotSwap: document.getElementById('banner-hot-swap'),

    // Waterfall Stage
    timelineRuler: document.getElementById('timeline-ruler'),
    timelineMilestonesTrack: document.getElementById('timeline-milestones-track'),
    waterfallBody: document.getElementById('waterfall-body'),
    waterfallEmptyState: document.getElementById('waterfall-empty-state'),
    rawJsonContainer: document.getElementById('raw-json-container'),
    rawJsonCode: document.getElementById('raw-json-code'),
    viewModeBtns: document.querySelectorAll('.view-mode-btn'),

    // Span Inspector Drawer
    spanInspectorDrawer: document.getElementById('span-inspector-drawer'),
    btnCloseInspector: document.getElementById('btn-close-inspector'),
    inspSpanTypeBadge: document.getElementById('insp-span-type-badge'),
    inspSpanName: document.getElementById('insp-span-name'),
    inspTimingFill: document.getElementById('insp-timing-fill'),
    inspDuration: document.getElementById('insp-duration'),
    inspOffset: document.getElementById('insp-offset'),
    inspPercent: document.getElementById('insp-percent'),
    inspStatus: document.getElementById('insp-status'),
    inspSpanId: document.getElementById('insp-span-id'),
    inspParentId: document.getElementById('insp-parent-id'),
    inspTraceId: document.getElementById('insp-trace-id'),
    sponsorCard: document.getElementById('sponsor-card'),
    sponsorTagsContainer: document.getElementById('sponsor-tags-container'),
    specJsonCard: document.getElementById('spec-json-card'),
    inspSpecCode: document.getElementById('insp-spec-code'),
    inspAttrCount: document.getElementById('insp-attr-count'),
    inspAttributesList: document.getElementById('insp-attributes-list'),
    inspEventCount: document.getElementById('insp-event-count'),
    inspEventsList: document.getElementById('insp-events-list'),

    // Toasts
    toastContainer: document.getElementById('toast-container'),
  };

  // --- API Client ---
  const api = {
    async getStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.warn('Failed to fetch status:', err);
        return null;
      }
    },

    async getTraces() {
      try {
        const res = await fetch('/api/traces');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.warn('Failed to fetch traces:', err);
        return { traces: [], count: 0 };
      }
    },

    async triggerDemo(runType) {
      try {
        const res = await fetch('/api/traces/demo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run: runType }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.error('Failed to trigger demo trace:', err);
        showToast(`Trigger failed: ${err.message}`, 'error');
        return null;
      }
    },

    async clearTraces() {
      try {
        const res = await fetch('/api/traces/clear', {
          method: 'POST',
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        console.error('Failed to clear traces:', err);
        showToast(`Clear failed: ${err.message}`, 'error');
        return null;
      }
    },
  };

  // --- Initialization ---
  async function init() {
    setupEventListeners();
    setupClock();
    connectSSE();
    await refreshAll();

    // Polling fallback check every 3s
    state.pollTimer = setInterval(async () => {
      if (!state.sseConnected) {
        await refreshAll();
      }
    }, 3000);
  }

  // --- Clock ---
  function setupClock() {
    const update = () => {
      const now = new Date();
      const timeStr = now.toISOString().substring(11, 19) + ' UTC';
      if (el.footerClock) el.footerClock.textContent = timeStr;
    };
    update();
    state.clockTimer = setInterval(update, 1000);
  }

  // --- Real-time SSE Connection ---
  function connectSSE() {
    if (state.eventSource) {
      state.eventSource.close();
    }

    try {
      const es = new EventSource('/api/traces/stream');
      state.eventSource = es;

      es.onopen = () => {
        state.sseConnected = true;
        updateSseStatus(true);
      };

      es.addEventListener('span', (e) => {
        try {
          const spanData = JSON.parse(e.data);
          handleIncomingSpan(spanData);
        } catch (err) {
          console.error('Error parsing SSE span:', err);
        }
      });

      es.onerror = () => {
        state.sseConnected = false;
        updateSseStatus(false);
      };
    } catch (err) {
      console.warn('SSE setup error:', err);
      state.sseConnected = false;
      updateSseStatus(false);
    }
  }

  function updateSseStatus(connected) {
    if (connected) {
      el.sseStatusPill.className = 'telemetry-pill live-pill';
      el.sseStatusText.textContent = 'LIVE SSE STREAM';
      el.footerSseMsg.textContent = 'SSE Connected (Port 8080)';
    } else {
      el.sseStatusPill.className = 'telemetry-pill';
      el.sseStatusText.textContent = 'STREAM RECONNECTING...';
      el.footerSseMsg.textContent = 'Polling fallback active (3s)';
    }
  }

  // Debounced handler for incoming stream spans
  let sseDebounceTimer = null;
  function handleIncomingSpan(spanData) {
    // Pulse latest op
    if (el.metricLatestOp) {
      el.metricLatestOp.textContent = spanData.name.toUpperCase();
      el.metricLatestOp.classList.add('text-cyan');
    }

    // Increment raw span counter
    if (el.metricSpansCount) {
      const current = parseInt(el.metricSpansCount.textContent, 10) || 0;
      el.metricSpansCount.textContent = current + 1;
    }

    // Indicate streaming
    state.isStreamingTrace = true;
    clearTimeout(state.streamPulseTimer);
    state.streamPulseTimer = setTimeout(() => {
      state.isStreamingTrace = false;
      renderSidebarRuns();
    }, 1200);

    // Debounce trace tree re-fetch
    clearTimeout(sseDebounceTimer);
    sseDebounceTimer = setTimeout(async () => {
      await refreshTracesData(false);
    }, 100);
  }

  // --- Data Fetching ---
  async function refreshAll() {
    await Promise.all([refreshStatus(), refreshTracesData(true)]);
  }

  async function refreshStatus() {
    const status = await api.getStatus();
    if (!status) return;
    state.serverStatus = status;

    if (el.metricTracesCount) el.metricTracesCount.textContent = status.total_traces ?? 0;
    if (el.metricSpansCount) el.metricSpansCount.textContent = status.total_spans ?? 0;

    if (el.tracerStatusText) {
      el.tracerStatusText.textContent = `TRACING : ${(status.tracer_mode || 'local').toUpperCase()}`;
    }
    if (el.tracerStatusPill) el.tracerStatusPill.className = 'telemetry-pill tracing-pill';
  }

  async function refreshTracesData(autoSelectLatest = false) {
    const data = await api.getTraces();
    state.traces = data.traces || [];

    if (el.metricTracesCount) el.metricTracesCount.textContent = state.traces.length;

    // Auto-select latest trace if none selected or previous ID vanished
    if (state.traces.length > 0) {
      const exists = state.traces.some((t) => t.trace_id === state.selectedTraceId);
      if (!exists || (autoSelectLatest && !state.selectedTraceId)) {
        state.selectedTraceId = state.traces[0].trace_id;
      }
    } else {
      state.selectedTraceId = null;
      state.selectedSpanId = null;
    }

    renderSidebarRuns();
    renderActiveTrace();
  }

  // --- Filtering ---
  function getFilteredTraces() {
    if (state.filter === 'run_a') {
      return state.traces.filter((t) => (t.run_name || '').toLowerCase().includes('run a') || (t.run_name || '').toLowerCase().includes('goto'));
    }
    if (state.filter === 'run_b') {
      return state.traces.filter((t) => (t.run_name || '').toLowerCase().includes('run b') || (t.run_name || '').toLowerCase().includes('avoid') || (t.run_name || '').toLowerCase().includes('compose'));
    }
    return state.traces;
  }

  // --- UI Rendering: Sidebar Runs ---
  function renderSidebarRuns() {
    const filtered = getFilteredTraces();
    el.sidebarRunCount.textContent = `${filtered.length} RUNS`;

    if (filtered.length === 0) {
      el.runsListContainer.innerHTML = `
        <div class="sidebar-empty">
          <div class="empty-radar"></div>
          <div class="empty-title">NO TRACES LOGGED</div>
          <div class="empty-sub">Trigger Run A or Run B to record telemetry</div>
        </div>
      `;
      return;
    }

    el.runsListContainer.innerHTML = filtered
      .map((t) => {
        const isActive = t.trace_id === state.selectedTraceId;
        const isRunB = (t.run_name || '').toLowerCase().includes('run b') || (t.run_name || '').toLowerCase().includes('avoid');
        const badgeClass = isRunB ? 'run-badge badge-run-b' : 'run-badge';
        const badgeLabel = isRunB ? 'RUN B: COMPOSE' : 'RUN A: GOTO';

        // Extract event badges
        const hasPrompt = (t.events || []).some((e) => e.name === 'physical_prompt');
        const hasRelease = (t.events || []).some((e) => e.name === 'release');
        const hasObstacle = (t.events || []).some((e) => e.name === 'obstacle_detected');

        // Formatted timestamp
        const timeStr = formatDuration(t.total_duration_ms);

        const streamingClass = isActive && state.isStreamingTrace ? 'is-streaming' : '';

        return `
          <div class="run-card ${isActive ? 'active' : ''} ${streamingClass}" data-trace-id="${t.trace_id}">
            <div class="run-card-top">
              <span class="${badgeClass}">${badgeLabel}</span>
              <span class="run-duration-pill mono">${timeStr}</span>
            </div>
            <div class="run-title" title="${escapeHtml(t.run_name || t.root_name)}">${escapeHtml(t.run_name || t.root_name)}</div>
            <div class="run-meta-row">
              <span>${t.span_count} spans</span>
              <span class="mono">${t.trace_id.substring(0, 8)}...</span>
            </div>
            <div class="run-tags-row">
              ${hasPrompt ? '<span class="run-tag">PROMPTED</span>' : ''}
              ${hasRelease ? '<span class="run-tag tag-release">RELEASE (HOT-SWAP)</span>' : ''}
              ${hasObstacle ? '<span class="run-tag tag-obstacle">OBSTACLE (BRIGHT DATA)</span>' : ''}
            </div>
          </div>
        `;
      })
      .join('');

    // Attach click listeners to cards
    el.runsListContainer.querySelectorAll('.run-card').forEach((card) => {
      card.addEventListener('click', () => {
        const traceId = card.getAttribute('data-trace-id');
        selectTrace(traceId);
      });
    });
  }

  function selectTrace(traceId) {
    state.selectedTraceId = traceId;
    renderSidebarRuns();
    renderActiveTrace();
  }

  // --- UI Rendering: Active Trace Main Stage ---
  function getSelectedTrace() {
    return state.traces.find((t) => t.trace_id === state.selectedTraceId) || null;
  }

  function renderActiveTrace() {
    const trace = getSelectedTrace();

    if (!trace) {
      // Empty state
      el.bannerTraceName.textContent = 'NO ACTIVE FLIGHT TRACE';
      el.bannerTraceId.textContent = '--------------------------------';
      el.bannerDuration.textContent = '0.00 ms';
      el.bannerSpanCount.textContent = '0';
      el.bannerEventCount.textContent = '0';
      el.bannerModeTag.textContent = 'STANDBY';

      el.waterfallEmptyState.classList.remove('hidden');
      el.timelineRuler.innerHTML = '';
      el.timelineMilestonesTrack.innerHTML = '';
      el.rawJsonContainer.classList.add('hidden');
      closeSpanInspector();
      return;
    }

    el.waterfallEmptyState.classList.add('hidden');

    // Update Banner
    el.bannerTraceName.textContent = trace.run_name || trace.root_name || 'Pipeline Trace';
    el.bannerTraceId.textContent = trace.trace_id;
    el.bannerDuration.textContent = formatDuration(trace.total_duration_ms);
    el.bannerSpanCount.textContent = trace.span_count;
    el.bannerEventCount.textContent = trace.event_count;
    el.bannerModeTag.textContent = 'FAST PATH: ~15-30s';

    // Check release event
    const hasRelease = (trace.events || []).some((e) => e.name === 'release');
    el.bannerHotSwap.textContent = hasRelease ? 'HOT-SWAPPED (v2)' : 'STANDBY';

    // Render Raw JSON representation
    el.rawJsonCode.textContent = JSON.stringify(trace, null, 2);

    if (state.viewMode === 'json') {
      el.rawJsonContainer.classList.remove('hidden');
      return;
    } else {
      el.rawJsonContainer.classList.add('hidden');
    }

    if (state.viewMode === 'flame') {
      el.waterfallBody.classList.add('flame-mode');
    } else {
      el.waterfallBody.classList.remove('flame-mode');
    }

    // Render Timeline Scale Ruler & Milestones
    renderTimelineRuler(trace);
    renderTimelineMilestones(trace);

    // Render Waterfall Rows
    renderWaterfallRows(trace);
  }

  // --- Timeline Ruler Calculation ---
  function renderTimelineRuler(trace) {
    const totalMs = Math.max(0.01, trace.total_duration_ms);
    const rulerEl = el.timelineRuler;
    rulerEl.innerHTML = '';

    // Calculate nice step intervals (e.g. 0.05ms, 0.1ms, 0.5ms, 1ms, 5ms, 50ms, 100ms)
    const rawStep = totalMs / 6;
    const magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
    const residual = rawStep / magnitude;
    let niceStep = magnitude;
    if (residual > 5) niceStep = 5 * magnitude;
    else if (residual > 2) niceStep = 2 * magnitude;

    niceStep = Math.max(0.01, niceStep);

    for (let t = 0; t <= totalMs * 1.02; t += niceStep) {
      const pct = (t / totalMs) * 100;
      if (pct > 100) break;

      const tick = document.createElement('div');
      tick.className = 'ruler-tick';
      tick.style.left = `${pct}%`;
      tick.textContent = formatDuration(t);
      rulerEl.appendChild(tick);
    }
  }

  // --- Prominent Vertical Milestones ---
  function renderTimelineMilestones(trace) {
    const container = el.timelineMilestonesTrack;
    container.innerHTML = '';
    const events = trace.events || [];

    events.forEach((ev) => {
      const pct = Math.min(99.5, Math.max(0.5, ev.percent_offset || 0));
      const marker = document.createElement('div');

      let markerClass = 'timeline-milestone-marker';
      let flagClass = 'milestone-flag';
      let icon = '●';

      if (ev.name === 'release') {
        markerClass += ' marker-release';
        flagClass += ' flag-release';
        icon = '⚡ RELEASE (HOT-SWAP)';
      } else if (ev.name === 'obstacle_detected') {
        markerClass += ' marker-obstacle';
        flagClass += ' flag-obstacle';
        icon = '🌐 OBSTACLE (BRIGHT DATA)';
      } else if (ev.name === 'physical_prompt') {
        icon = '🛑 PHYSICAL PROMPT';
      }

      marker.className = markerClass;
      marker.style.left = `${pct}%`;

      const flag = document.createElement('div');
      flag.className = flagClass;
      flag.textContent = `${icon} [+${formatDuration(ev.offset_ms)}]`;
      flag.title = `${ev.name} event on span ${ev.span_name}`;

      marker.appendChild(flag);
      container.appendChild(marker);
    });
  }

  // --- Waterfall Rows Rendering ---
  function renderWaterfallRows(trace) {
    const spans = trace.flat_spans || trace.root_spans || [];
    el.waterfallBody.innerHTML = '';

    if (spans.length === 0) {
      el.waterfallBody.innerHTML = `
        <div class="waterfall-empty-state">
          <div class="empty-code">NO SPAN NODES RECORDED</div>
        </div>
      `;
      return;
    }

    spans.forEach((s) => {
      const isSelected = s.span_id === state.selectedSpanId;
      const depth = s.depth || 0;
      const icon = SPAN_ICONS[s.name] || '▫';
      const row = document.createElement('div');
      row.className = `waterfall-row ${isSelected ? 'selected' : ''}`;
      row.setAttribute('data-span-id', s.span_id);

      // Depth connector formatting
      let indentStr = '';
      if (depth > 0) {
        indentStr = '│  '.repeat(depth - 1) + '└── ';
      }

      // Inline parameter tags
      let inlineChipsHtml = '';
      if (s.name === 'scrape' && s.attributes?.sponsor) {
        const itemInfo = s.attributes.item_name || (s.attributes.width_cm ? `${s.attributes.width_cm}x${s.attributes.height_cm}cm` : 'Bypassed');
        inlineChipsHtml += `<span class="span-inline-chip chip-brightdata">Bright Data: ${escapeHtml(itemInfo)}</span>`;
      } else if (s.name === 'test' && s.attributes?.result) {
        inlineChipsHtml += `<span class="span-inline-chip chip-pass">PASS (${s.attributes.max_error_cm || 0}cm)</span>`;
      } else if (s.name === 'approve' && s.events?.some((e) => e.name === 'release')) {
        inlineChipsHtml += `<span class="span-inline-chip chip-pass">⚡ HOT-SWAP v2</span>`;
      } else if (s.name === 'update_twin' && s.events?.some((e) => e.name === 'physical_prompt')) {
        inlineChipsHtml += `<span class="span-inline-chip chip-event-pin">🛑 PROMPTED</span>`;
      }

      // Bar class
      const barThemeClass = `bar-${s.name.replace(/[^a-zA-Z0-9_]/g, '')}`;

      // Calculate bar layout
      const leftPct = Math.min(99.5, Math.max(0, s.percent_start ?? 0));
      const widthPct = Math.min(100 - leftPct, Math.max(0.6, s.percent_width ?? 1));

      // Inline event pins on the bar
      let eventPinsHtml = '';
      (s.events || []).forEach((ev) => {
        const pinClass = ev.name === 'release' ? 'bar-event-pin pin-release' : 'bar-event-pin';
        eventPinsHtml += `<div class="${pinClass}" title="Event: ${escapeHtml(ev.name)}"></div>`;
      });

      row.innerHTML = `
        <div class="span-tree-col">
          ${indentStr ? `<span class="tree-indent-guide">${indentStr}</span>` : ''}
          <span class="span-row-icon">${icon}</span>
          <span class="span-row-name">${escapeHtml(s.name)}</span>
          ${inlineChipsHtml}
          <span class="span-row-duration-pill">${formatDuration(s.duration_ms)}</span>
        </div>
        <div class="span-track-col">
          <div class="waterfall-bar ${barThemeClass}" style="left: ${leftPct}%; width: ${widthPct}%;">
            ${eventPinsHtml}
            <span class="bar-label-text">${escapeHtml(s.name)} (${formatDuration(s.duration_ms)})</span>
          </div>
        </div>
      `;

      row.addEventListener('click', () => {
        selectSpan(s.span_id);
      });

      el.waterfallBody.appendChild(row);
    });
  }

  function selectSpan(spanId) {
    state.selectedSpanId = spanId;

    // Highlight row
    el.waterfallBody.querySelectorAll('.waterfall-row').forEach((r) => {
      if (r.getAttribute('data-span-id') === spanId) {
        r.classList.add('selected');
      } else {
        r.classList.remove('selected');
      }
    });

    renderSpanInspector(spanId);
  }

  // --- Slide-in Span Inspector Drawer ---
  function renderSpanInspector(spanId) {
    const trace = getSelectedTrace();
    if (!trace) return;

    const spans = trace.flat_spans || trace.root_spans || [];
    const spanNode = spans.find((s) => s.span_id === spanId);
    if (!spanNode) return;

    // Open drawer
    el.spanInspectorDrawer.classList.add('open');

    // Header info
    el.inspSpanTypeBadge.textContent = spanNode.depth === 0 ? 'ROOT SPAN' : 'CHILD SPAN';
    el.inspSpanName.textContent = spanNode.name;

    // Timing
    const totalMs = Math.max(0.001, trace.total_duration_ms);
    const durationMs = spanNode.duration_ms || 0;
    const offsetMs = spanNode.offset_ms || 0;
    const pct = ((durationMs / totalMs) * 100).toFixed(1);

    el.inspDuration.textContent = formatDuration(durationMs);
    el.inspOffset.textContent = `+${formatDuration(offsetMs)}`;
    el.inspPercent.textContent = `${pct}%`;
    el.inspTimingFill.style.width = `${Math.max(2, Math.min(100, pct))}%`;
    el.inspStatus.textContent = spanNode.status?.code || 'OK';

    // Identifiers
    el.inspSpanId.textContent = spanNode.span_id;
    el.inspParentId.textContent = spanNode.parent_id || 'None (Root)';
    el.inspTraceId.textContent = spanNode.trace_id;

    // Sponsor Card (Bright Data)
    const attrs = spanNode.attributes || {};
    if (spanNode.name === 'scrape' || attrs.sponsor === 'Bright Data' || attrs.catalog_url) {
      el.sponsorCard.classList.remove('hidden');
      el.sponsorTagsContainer.innerHTML = `
        <span class="span-inline-chip chip-brightdata">URL: ${escapeHtml(attrs.catalog_url || 'Bright Data Scraper')}</span>
        ${attrs.item_name ? `<span class="span-inline-chip chip-pass">Item: ${escapeHtml(attrs.item_name)}</span>` : ''}
        ${attrs.width_cm ? `<span class="span-inline-chip chip-brightdata">Width: ${attrs.width_cm}cm</span>` : ''}
        ${attrs.height_cm ? `<span class="span-inline-chip chip-brightdata">Height: ${attrs.height_cm}cm</span>` : ''}
        ${attrs.geom ? `<span class="span-inline-chip chip-pass">Geometry: ${escapeHtml(attrs.geom)}</span>` : ''}
      `;
    } else {
      el.sponsorCard.classList.add('hidden');
    }

    // Spec Patch JSON block
    if (attrs.spec_json) {
      el.specJsonCard.classList.remove('hidden');
      try {
        const parsed = JSON.parse(attrs.spec_json);
        el.inspSpecCode.textContent = JSON.stringify(parsed, null, 2);
      } catch (e) {
        el.inspSpecCode.textContent = attrs.spec_json;
      }
    } else {
      el.specJsonCard.classList.add('hidden');
    }

    // Attributes Table
    const attrEntries = Object.entries(attrs).filter(([k]) => k !== 'spec_json');
    el.inspAttrCount.textContent = attrEntries.length;

    if (attrEntries.length === 0) {
      el.inspAttributesList.innerHTML = `<div class="attr-row"><span class="attr-key">No custom attributes recorded</span></div>`;
    } else {
      el.inspAttributesList.innerHTML = attrEntries
        .map(([k, v]) => {
          let valDisplay = typeof v === 'object' ? JSON.stringify(v) : String(v);
          return `
            <div class="attr-row">
              <span class="attr-key">${escapeHtml(k)}</span>
              <span class="attr-val mono">${escapeHtml(valDisplay)}</span>
            </div>
          `;
        })
        .join('');
    }

    // Recorded Events List
    const events = spanNode.events || [];
    el.inspEventCount.textContent = events.length;

    if (events.length === 0) {
      el.inspEventsList.innerHTML = `<div class="event-item-card"><span class="event-item-time">No events recorded on this span</span></div>`;
    } else {
      el.inspEventsList.innerHTML = events
        .map((ev) => {
          let cardClass = 'event-item-card';
          if (ev.name === 'release') cardClass += ' event-rel';
          else if (ev.name === 'physical_prompt') cardClass += ' event-hot';

          const evAttrs = Object.entries(ev.attributes || {});
          const attrsHtml = evAttrs
            .map(([ak, av]) => `<div class="event-attr-line mono"><span style="color:#64748b;">${escapeHtml(ak)}:</span> ${escapeHtml(String(av))}</div>`)
            .join('');

          return `
            <div class="${cardClass}">
              <div class="event-item-top">
                <span class="event-item-name">${escapeHtml(ev.name)}</span>
                <span class="event-item-time mono">+${formatDuration((ev.timestamp_ns - trace.start_time_ns) / 1_000_000.0)}</span>
              </div>
              <div class="event-attrs-grid">
                ${attrsHtml}
              </div>
            </div>
          `;
        })
        .join('');
    }
  }

  function closeSpanInspector() {
    el.spanInspectorDrawer.classList.remove('open');
    state.selectedSpanId = null;
    el.waterfallBody.querySelectorAll('.waterfall-row').forEach((r) => r.classList.remove('selected'));
  }

  // --- Event Listeners & Keyboard Navigation ---
  function setupEventListeners() {
    // Run Buttons
    el.btnRunA.addEventListener('click', async () => {
      showToast('Emitting Run A (goto) physical prompt trace...', 'info');
      await api.triggerDemo('A');
      await refreshTracesData(true);
    });

    el.btnRunB.addEventListener('click', async () => {
      showToast('Emitting Run B (compose goto + avoid) trace...', 'info');
      await api.triggerDemo('B');
      await refreshTracesData(true);
    });

    // Refresh & Clear
    el.btnRefresh.addEventListener('click', async () => {
      showToast('Refreshing telemetry...', 'info');
      await refreshAll();
    });

    el.btnClear.addEventListener('click', async () => {
      if (confirm('Clear all flight recorder traces?')) {
        await api.clearTraces();
        showToast('Flight recorder cleared', 'warn');
        await refreshAll();
      }
    });

    // Copy Trace ID
    el.btnCopyTraceId.addEventListener('click', () => {
      const id = el.bannerTraceId.textContent;
      if (id && !id.includes('---')) {
        navigator.clipboard.writeText(id);
        showToast(`Copied Trace ID: ${id.substring(0, 12)}...`, 'success');
      }
    });

    // Inspector Close
    el.btnCloseInspector.addEventListener('click', closeSpanInspector);

    // Sidebar Filters
    el.filterChips.forEach((chip) => {
      chip.addEventListener('click', () => {
        el.filterChips.forEach((c) => c.classList.remove('active'));
        chip.classList.add('active');
        state.filter = chip.getAttribute('data-filter') || 'all';
        renderSidebarRuns();
      });
    });

    // View Mode Toggles
    el.viewModeBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        el.viewModeBtns.forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        state.viewMode = btn.getAttribute('data-view') || 'waterfall';
        renderActiveTrace();
      });
    });

    // Global Keybindings
    window.addEventListener('keydown', (e) => {
      // Avoid hotkeys when typing in input
      if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

      const key = e.key.toLowerCase();
      if (key === 'a') {
        e.preventDefault();
        el.btnRunA.click();
      } else if (key === 'b') {
        e.preventDefault();
        el.btnRunB.click();
      } else if (key === 'r') {
        e.preventDefault();
        el.btnRefresh.click();
      } else if (key === 'c') {
        e.preventDefault();
        el.btnClear.click();
      } else if (e.key === 'Escape') {
        closeSpanInspector();
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        // Navigate spans
        const trace = getSelectedTrace();
        if (!trace) return;
        const spans = trace.flat_spans || trace.root_spans || [];
        if (spans.length === 0) return;

        e.preventDefault();
        const currentIndex = spans.findIndex((s) => s.span_id === state.selectedSpanId);
        let nextIndex = 0;
        if (e.key === 'ArrowDown') {
          nextIndex = currentIndex < spans.length - 1 ? currentIndex + 1 : 0;
        } else {
          nextIndex = currentIndex > 0 ? currentIndex - 1 : spans.length - 1;
        }
        selectSpan(spans[nextIndex].span_id);
      }
    });
  }

  // --- Toast Notifications ---
  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'hud-toast';

    let icon = '⚡';
    if (type === 'warn' || type === 'error') icon = '⚠️';
    else if (type === 'success') icon = '✓';

    toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
    el.toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => toast.remove(), 200);
    }, 2800);
  }

  // --- Utilities ---
  function formatDuration(ms) {
    if (ms == null || isNaN(ms)) return '0.00 ms';
    if (ms < 1.0) {
      return `${ms.toFixed(2)} ms`;
    } else if (ms < 1000) {
      return `${ms.toFixed(1)} ms`;
    } else {
      return `${(ms / 1000).toFixed(2)} s`;
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Start app on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
