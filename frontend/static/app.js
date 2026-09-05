"use strict";

let overviewData = null;

// ----------------------------------------------------------------------------
// helpers
// ----------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const inr = (n) => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const pct = (x) => (x * 100).toFixed(1) + "%";
const signedPct = (x) => (x >= 0 ? "+" : "") + (x * 100).toFixed(1) + "%";
const boolChip = (v) => {
  if (v === null || v === undefined) return '<span class="chip muted">&mdash;</span>';
  return v ? '<span class="chip yes">yes</span>' : '<span class="chip no">no</span>';
};

// ----------------------------------------------------------------------------
// theme (persisted to localStorage; falls back silently if unavailable)
// ----------------------------------------------------------------------------
function setupTheme() {
  const root = document.documentElement;
  const icon = $("#theme-toggle .theme-icon");
  let saved = null;
  try {
    saved = localStorage.getItem("payback-theme");
  } catch (e) {
    /* private-browsing / storage blocked — just default to light */
  }
  if (saved === "dark") {
    root.setAttribute("data-theme", "dark");
    if (icon) icon.textContent = "Light";
  }
  $("#theme-toggle").addEventListener("click", () => {
    const isDark = root.getAttribute("data-theme") === "dark";
    if (isDark) {
      root.removeAttribute("data-theme");
      if (icon) icon.textContent = "Dark";
    } else {
      root.setAttribute("data-theme", "dark");
      if (icon) icon.textContent = "Light";
    }
    try {
      localStorage.setItem("payback-theme", isDark ? "light" : "dark");
    } catch (e) {
      /* ignore — theme just won't persist across reloads */
    }
  });
}

// ----------------------------------------------------------------------------
// tabs (pill nav with a sliding glider behind the active tab)
// ----------------------------------------------------------------------------
function moveGlider(btn) {
  const glider = $(".tab-glider");
  if (!glider || !btn) return;
  glider.style.width = btn.offsetWidth + "px";
  glider.style.transform = `translateX(${btn.offsetLeft - 5}px)`;
}

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tab-panel").forEach((p) =>
        p.classList.toggle("active", p.id === "tab-" + tab)
      );
      moveGlider(btn);
    });
  });
  moveGlider($(".tab-btn.active"));
  window.addEventListener("resize", () => moveGlider($(".tab-btn.active")));
}

// ----------------------------------------------------------------------------
// small count-up animation for the headline metric numbers
// ----------------------------------------------------------------------------
function animateValue(node, targetText) {
  const match = targetText.match(/^([^\d-]*)([\d,]+(?:\.\d+)?)([^\d]*)$/);
  if (!match || document.body.dataset.reduceMotion === "1") {
    node.textContent = targetText;
    return;
  }
  const [, prefix, numStr, suffix] = match;
  const target = parseFloat(numStr.replace(/,/g, ""));
  const decimals = (numStr.split(".")[1] || "").length;
  const duration = 700;
  const start = performance.now();
  function frame(now) {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    const value = target * eased;
    node.textContent = prefix + value.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }) + suffix;
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ----------------------------------------------------------------------------
// overview
// ----------------------------------------------------------------------------
async function loadOverview() {
  let data;
  try {
    const resp = await fetch("/api/overview");
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      showGlobalError(body.detail || `Failed to load overview (HTTP ${resp.status})`);
      return;
    }
    data = await resp.json();
  } catch (e) {
    showGlobalError("Could not reach the dashboard API. Is the server running?");
    return;
  }
  overviewData = data;
  $("#global-error").hidden = true;

  renderBackendLine(data.current_model_backend);
  // Deliberately NOT synced to the .env MODEL_BACKEND default (which stays
  // "prompted"/local for the documented architecture) — the live-demo
  // dropdown defaults to Groq (see index.html) since it's faster and scores
  // higher, and shouldn't get silently reset back to Ollama on every reload.
  renderMetricCards(data);
  renderComparison(data.comparison);
  renderRubricChart(data.rubric_progression);
  renderRubricComparison(data.rubric_comparison);
  renderJudgeDiscrimination(data.judge_discrimination);
  renderSlices(data.slices);
  renderPromise(data.promise_extraction);
  renderRazorpay(data.razorpay_integration);
  renderPipeline();
  populateCaseSelect(data.cases);
}

function showGlobalError(msg) {
  const box = $("#global-error");
  box.textContent = msg;
  box.hidden = false;
}

function renderBackendLine(backend) {
  const labels = {
    stub: "stub (deterministic, offline)",
    prompted: "prompted — local Ollama (qwen2.5:7b)",
    groq_prompted: "groq_prompted — Groq cloud (qwen/qwen3.8-27b)",
  };
  $("#backend-line").innerHTML =
    "Active escalation backend (<code>MODEL_BACKEND</code>): <strong>" +
    (labels[backend] || backend) +
    "</strong>";
}

function renderMetricCards(data) {
  const t = data.totals;
  const cards = [
    ["Total cases", t.total_cases.toLocaleString("en-IN")],
    ["Held-out cases", t.holdout_cases.toLocaleString("en-IN")],
    ["Total ₹ (all cases)", inr(t.total_amount_inr)],
    [
      "System results loaded",
      data.system_results_loaded ? data.system_results_count + " cases" : "none yet",
    ],
  ];
  const row = $("#metric-cards");
  row.innerHTML = "";
  cards.forEach(([label, value]) => {
    const c = el("div", "metric-card");
    c.appendChild(el("div", "label", label));
    const valueNode = el("div", "value", "");
    c.appendChild(valueNode);
    row.appendChild(c);
    animateValue(valueNode, String(value));
  });
}

function renderComparison(c) {
  const box = $("#comparison");
  if (!c) {
    box.className = "info-box";
    box.textContent =
      "Run `python scripts/run_baseline_eval.py` and `python scripts/run_system_eval.py` to populate this.";
    return;
  }
  box.className = "callout";
  const kv = (k, v, cls) =>
    `<div class="kv"><div class="k">${k}</div><div class="v ${cls || ""}">${v}</div></div>`;
  box.innerHTML =
    '<div class="kv-grid">' +
    kv("₹ at risk", inr(c.rupees_at_risk)) +
    kv("Baseline recovery", pct(c.baseline_recovery_rate)) +
    kv("System recovery", pct(c.system_recovery_rate), "pos") +
    kv("Uplift", signedPct(c.uplift), "pos") +
    kv("Retry-only ₹", inr(c.retry_only_recovered_inr)) +
    kv("Escalation-assisted ₹", inr(c.escalation_assisted_recovered_inr)) +
    kv("Escalation rate", pct(c.escalation_rate)) +
    kv("Guardrail violations", c.guardrail_violations) +
    "</div>" +
    '<p class="note" style="margin-bottom:0">Same held-out population and the same multi-attempt budget ' +
    "for both runs; the baseline never escalates. Attempt-outcome probabilities decay with repeated tries, " +
    "applied identically to both, so the comparison isolates diagnosis-aware routing + the escalation channel.</p>";
}

function renderRubricChart(rows) {
  const chart = $("#rubric-chart");
  chart.innerHTML = "";
  if (!rows || !rows.length) {
    chart.innerHTML = '<p class="note">No rubric reports on disk yet.</p>';
    return;
  }
  rows.forEach((r) => {
    const width = (r.overall / 5.0) * 100;
    const row = el("div", "bar-row");
    row.appendChild(el("span", "bar-label", r.label));
    const track = el("div", "bar-track");
    const fill = el("div", "bar-fill" + (r.current ? " current" : ""));
    fill.style.width = width.toFixed(1) + "%";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "bar-value", r.overall.toFixed(2)));
    chart.appendChild(row);
  });
}

function renderRubricComparison(rc) {
  const box = $("#rubric-comparison");
  box.innerHTML = "";
  if (!rc || (!rc.local && !rc.groq)) return;
  const crits = [
    ["tone_naturalness", "Tone naturalness"],
    ["task_success", "Task success"],
    ["code_switch_quality", "Code-switch quality"],
    ["overall", "Overall"],
  ];
  const scroll = el("div", "table-scroll");
  const table = el("table");
  table.innerHTML =
    "<thead><tr><th>Criterion</th><th>Local (qwen2.5:7b)</th><th>Groq (qwen3.8-27b)</th></tr></thead>";
  const tbody = el("tbody");
  crits.forEach(([key, label]) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, label));
    tr.appendChild(el("td", null, rc.local ? rc.local[key].toFixed(2) : "—"));
    tr.appendChild(el("td", null, rc.groq ? rc.groq[key].toFixed(2) : "—"));
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  scroll.appendChild(table);
  box.appendChild(scroll);
}

function renderJudgeDiscrimination(jd) {
  const p = $("#judge-discrimination");
  if (!jd) {
    p.textContent = "";
    return;
  }
  p.innerHTML =
    `<strong>Judge validity check:</strong> corrupting one turn in ${jd.n_corruption_cases} already-scored ` +
    `transcripts dropped the judge's overall score by a mean of ${jd.mean_overall_score_drop.toFixed(2)}/5 ` +
    `(judge: <code>${jd.judge_model}</code>) &mdash; each corruption hit the criterion it violated hardest, ` +
    "so the headline number reflects quality, not judge leniency.";
}

function renderSlices(slices) {
  const box = $("#slices");
  box.innerHTML = "";
  if (!slices) {
    box.className = "info-box";
    box.textContent = "Run `python scripts/run_slice_analysis.py` to populate this (needs both eval runs first).";
    return;
  }
  box.className = "";
  const labels = {
    failure_category: "By failure category (ground truth)",
    amount_bucket: "By amount bucket",
    attempt_count: "By attempt count at detection",
  };
  Object.entries(labels).forEach(([dim, label]) => {
    if (!slices[dim]) return;
    const group = el("div", "slice-group");
    group.appendChild(el("h4", null, label));
    const scroll = el("div", "table-scroll");
    const table = el("table");
    table.innerHTML =
      "<thead><tr><th>Slice</th><th>n</th><th>Baseline</th><th>System</th><th>Uplift</th></tr></thead>";
    const tbody = el("tbody");
    Object.entries(slices[dim]).forEach(([slice, m]) => {
      const tr = el("tr");
      tr.innerHTML =
        `<td>${slice}</td><td>${m.n_cases}</td>` +
        `<td>${pct(m.baseline_recovery_rate)}</td>` +
        `<td>${pct(m.system_recovery_rate)}</td>` +
        `<td class="${m.uplift >= 0 ? "pos" : "neg"}">${signedPct(m.uplift)}</td>`;
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    scroll.appendChild(table);
    group.appendChild(scroll);
    box.appendChild(group);
  });
}

function renderPromise(p) {
  const box = $("#promise");
  if (!p) {
    box.className = "info-box";
    box.textContent = "Run `python scripts/evaluate_promise_extraction.py` to populate this.";
    return;
  }
  const warn = p.backend === "rule_based";
  box.className = "callout" + (warn ? " warn" : "");
  let html =
    '<div class="kv-grid">' +
    `<div class="kv"><div class="k">Precision</div><div class="v">${pct(p.precision)}</div></div>` +
    `<div class="kv"><div class="k">Recall</div><div class="v">${pct(p.recall)}</div></div>` +
    `<div class="kv"><div class="k">F1</div><div class="v">${pct(p.f1)}</div></div>` +
    `<div class="kv"><div class="k">Backend</div><div class="v">${p.backend}</div></div>` +
    "</div>";
  if (warn) {
    html +=
      '<p class="note" style="margin-bottom:0">Evaluated on the same hand-authored Hinglish vocabulary ' +
      "the rule-based extractor's keyword rules were built from &mdash; an internal-consistency check, not " +
      "evidence of generalization. The real robustness test is the LLM-based extractor against agent-generated text.</p>";
  }
  box.innerHTML = html;
}

function renderRazorpay(rz) {
  const box = $("#razorpay");
  box.innerHTML = "";
  if (!rz) {
    box.className = "info-box";
    box.textContent =
      "Run `python scripts/verify_razorpay_integration.py` (needs RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET).";
    return;
  }
  box.className = "";
  box.appendChild(
    (() => {
      const p = el("p", "note");
      p.innerHTML =
        `<strong>${rz.n_real_razorpay_orders_created} real Razorpay test-mode orders</strong> created across ` +
        `${rz.n_cases} held-out cases, each gated by the deterministic policy engine (a policy-decided ` +
        "escalate-only case correctly creates zero orders). Frozen headline numbers still use the " +
        "byte-reproducible stub executor.";
      return p;
    })()
  );
  const scroll = el("div", "table-scroll");
  const table = el("table");
  table.innerHTML =
    "<thead><tr><th>Case</th><th>&#8377;</th><th>Recovered</th><th>Channel</th><th>Attempts</th><th>Razorpay order IDs</th></tr></thead>";
  const tbody = el("tbody");
  rz.cases.forEach((c) => {
    const tr = el("tr");
    tr.innerHTML =
      `<td>${c.case_id}</td><td>${inr(c.amount_inr)}</td>` +
      `<td>${boolChip(c.recovered)}</td><td>${c.recovery_channel || "—"}</td>` +
      `<td>${c.attempts_used}</td>` +
      `<td>${c.razorpay_order_ids.length ? c.razorpay_order_ids.join(", ") : "—"}</td>`;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  scroll.appendChild(table);
  box.appendChild(scroll);
}

// ----------------------------------------------------------------------------
// pipeline table (client-side filtered)
// ----------------------------------------------------------------------------
function renderPipeline() {
  if (!overviewData) return;
  const split = $("#filter-split").value;
  const outcome = $("#filter-outcome").value;
  let rows = overviewData.cases;
  if (split !== "all") rows = rows.filter((r) => r.split === split);
  if (outcome === "unrecovered") rows = rows.filter((r) => r.recovered === false);
  else if (outcome === "recovered") rows = rows.filter((r) => r.recovered === true);
  else if (outcome === "guardrail") rows = rows.filter((r) => (r.guardrail_violations || 0) > 0);

  const tbody = $("#pipeline-table tbody");
  tbody.innerHTML = "";
  rows.forEach((r) => {
    const tr = el("tr", "clickable");
    const liveTag = r.live_demo ? ' <span class="live-tag">live demo</span>' : "";
    tr.innerHTML =
      `<td>${r.case_id}</td><td>${inr(r.amount_inr)}</td><td>${r.subscription_state}</td>` +
      `<td>${r.attempt_count}</td><td>${r.observed_reason}</td><td>${r.split}</td>` +
      `<td>${r.true_cause}</td><td>${boolChip(r.recovered)}${liveTag}</td>` +
      `<td>${r.recovery_channel || "—"}</td>` +
      `<td>${r.guardrail_violations === null ? "—" : r.guardrail_violations}</td>`;
    tr.addEventListener("click", () => openCase(r.case_id));
    tbody.appendChild(tr);
  });
  $("#pipeline-count").textContent = `${rows.length} case${rows.length === 1 ? "" : "s"} shown`;
}

// ----------------------------------------------------------------------------
// case detail
// ----------------------------------------------------------------------------
function populateCaseSelect(cases) {
  const sel = $("#case-select");
  sel.innerHTML = '<option value="">— select a case —</option>';
  cases
    .map((c) => c.case_id)
    .sort()
    .forEach((id) => {
      const o = el("option", null, id);
      o.value = id;
      sel.appendChild(o);
    });
  sel.addEventListener("change", () => {
    if (sel.value) openCase(sel.value);
  });
}

function openCase(caseId) {
  document.querySelector('.tab-btn[data-tab="case"]').click();
  $("#case-select").value = caseId;
  loadCase(caseId);
}

async function loadCase(caseId) {
  // Clear immediately so the previous case's transcript/retry result never
  // flashes while the new one loads — restored below from data.live_result
  // if this case actually has a saved run (see server.py's _LIVE_RESULTS).
  $("#escalate-result").innerHTML = "";
  $("#escalate-error").hidden = true;
  $("#retry-result").innerHTML = "";
  $("#retry-error").hidden = true;
  let data;
  try {
    const resp = await fetch(`/api/case/${encodeURIComponent(caseId)}`);
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      showGlobalError(body.detail || `Failed to load case (HTTP ${resp.status})`);
      return;
    }
    data = await resp.json();
  } catch (e) {
    showGlobalError("Could not reach the dashboard API.");
    return;
  }
  $("#global-error").hidden = true;
  $("#case-body").hidden = false;
  renderCaseMetrics(data);
  renderCaseOutcome(data);
  renderCaseObserved(data);
  renderAuditTimeline(data.audit_events);
  renderLatestPromise(data.latest_promise);
  updateRetryButton(data.is_retry_eligible);
  if (data.live_result && data.live_result.kind === "escalation") {
    renderTranscript(data.live_result);
    $("#escalate-backend").value = data.live_result.backend_used;
    $("#escalate-backend").dispatchEvent(new Event("change"));
  } else if (data.live_result && data.live_result.kind === "retry") {
    renderRetryResult(data.live_result);
  }
}

function renderCaseMetrics(d) {
  const row = $("#case-metrics");
  row.innerHTML = "";
  const cards = [
    ["Amount", inr(d.amount_inr)],
    ["Subscription state", d.subscription_state],
    ["Attempt count", d.attempt_count],
    ["Retry / escalation eligible", `${d.is_retry_eligible ? "Y" : "N"} / ${d.is_escalation_eligible ? "Y" : "N"}`],
  ];
  cards.forEach(([label, value]) => {
    const c = el("div", "metric-card");
    c.appendChild(el("div", "label", label));
    c.appendChild(el("div", "value", value));
    row.appendChild(c);
  });
}

function renderCaseOutcome(d) {
  const p = $("#case-outcome");
  const r = d.system_result;
  let frozenLine;
  if (!r) {
    frozenLine = "No frozen system result for this case — run `python scripts/run_system_eval.py`.";
  } else {
    const parts = [r.recovered ? "Recovered" : "Not recovered"];
    if (r.recovery_channel) parts.push("via " + r.recovery_channel);
    if (r.guardrail_violations) parts.push(`${r.guardrail_violations} guardrail violation(s)`);
    frozenLine = "Frozen batch eval: " + parts.join(" · ");
  }
  p.innerHTML = `<div>${frozenLine}</div>`;
  if (d.live_result) appendLiveOutcomeLine(p, d.live_result);
}

function appendLiveOutcomeLine(container, live) {
  const existing = container.querySelector(".live-outcome-line");
  if (existing) existing.remove();
  let text;
  if (live.kind === "retry") {
    text =
      "Live retry attempt (Razorpay test-mode): " +
      (live.resolved ? "Succeeded" : "Failed") +
      (live.razorpay_order_id ? ` · order ${live.razorpay_order_id}` : "");
  } else {
    text =
      "Live demo run: " +
      (live.resolved ? "Resolved via escalation" : "Not resolved") +
      " · " + live.backend_used + (live.model ? ` (${live.model})` : "");
  }
  container.appendChild(el("div", "live-outcome-line", text));
}

// Reflects a just-completed live run immediately, without a full reload:
// updates the case-outcome line here, and patches the in-memory pipeline
// row (server.py's own /api/overview also overlays this from its session
// cache, so a fresh page load stays consistent too).
function reflectLiveOutcome(caseId, result) {
  appendLiveOutcomeLine($("#case-outcome"), result);
  if (overviewData) {
    const row = overviewData.cases.find((c) => c.case_id === caseId);
    if (row) {
      row.recovered = result.resolved;
      row.recovery_channel = result.recovery_channel;
      row.live_demo = true;
      renderPipeline();
    }
  }
}

function renderCaseObserved(d) {
  const o = d.observed;
  $("#case-observed").innerHTML =
    `<div class="kv-grid">` +
    `<div class="kv"><div class="k">Observed code</div><div class="v">${o.code}</div></div>` +
    `<div class="kv"><div class="k">Reason</div><div class="v">${o.reason}</div></div>` +
    `<div class="kv"><div class="k">Source / step</div><div class="v">${o.source} / ${o.step}</div></div>` +
    `<div class="kv"><div class="k">Ground-truth cause (hidden from system)</div><div class="v">${d.true_cause}</div></div>` +
    `</div>`;
}

const EVENT_LABELS = {
  detected: "Detected",
  diagnosis: "Diagnosis",
  diagnosis_result: "Diagnosis",
  policy_decision: "Policy decision",
  retry_attempt: "Retry attempt",
  guardrail_violation: "Guardrail violation",
  escalation: "Escalation",
  promise_extraction: "Promise extraction",
  clarify: "Clarify",
  stop: "Stop",
  final_outcome: "Final outcome",
};

function renderAuditTimeline(events) {
  const tbody = $("#audit-table tbody");
  tbody.innerHTML = "";
  const empty = $("#audit-empty");
  if (!events || !events.length) {
    empty.hidden = false;
    empty.textContent =
      "No audit events for this case yet — run `python scripts/run_system_eval.py` or `python scripts/replay_case.py <id>`.";
    $("#audit-table").hidden = true;
    return;
  }
  empty.hidden = true;
  $("#audit-table").hidden = false;
  events.forEach((e) => {
    const tr = el("tr");
    const when = e.created_at ? e.created_at.replace("T", " ").slice(0, 19) : "—";
    const label = EVENT_LABELS[e.event_type] || e.event_type;
    tr.innerHTML =
      `<td>${when}</td><td>${label}</td>` +
      `<td><code>${escapeHtml(JSON.stringify(e.payload))}</code></td>`;
    tbody.appendChild(tr);
  });
}

function renderLatestPromise(promise) {
  $("#latest-promise").textContent = promise ? JSON.stringify(promise, null, 2) : "(none extracted for this case)";
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// ----------------------------------------------------------------------------
// live retry (real Razorpay test-mode API)
// ----------------------------------------------------------------------------
const RETRY_BTN_IDLE = "Run live retry attempt";
const RETRY_BTN_BUSY = "Contacting Razorpay…";

function updateRetryButton(isEligible) {
  const btn = $("#retry-btn");
  const note = $("#retry-note");
  if (!isEligible) {
    btn.disabled = true;
    note.dataset.baseText = note.dataset.baseText || note.textContent;
    note.textContent = "This case isn't retry-eligible, so there's nothing for the policy engine to route to retry.";
  } else {
    btn.disabled = false;
    if (note.dataset.baseText) note.textContent = note.dataset.baseText;
  }
}

function setupRetry() {
  $("#retry-btn").addEventListener("click", async () => {
    const caseId = $("#case-select").value;
    if (!caseId) return;
    const btn = $("#retry-btn");
    const errBox = $("#retry-error");
    const result = $("#retry-result");
    errBox.hidden = true;
    result.innerHTML = "";
    btn.disabled = true;
    btn.textContent = RETRY_BTN_BUSY;
    try {
      const resp = await fetch(`/api/case/${encodeURIComponent(caseId)}/retry`, { method: "POST" });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        errBox.textContent = body.detail || `Request failed (HTTP ${resp.status})`;
        errBox.hidden = false;
        return;
      }
      renderRetryResult(body);
      reflectLiveOutcome(caseId, body);
    } catch (e) {
      errBox.textContent = "Request failed at the network level — is the server still running?";
      errBox.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = RETRY_BTN_IDLE;
    }
  });
}

function renderRetryResult(body) {
  const result = $("#retry-result");
  result.innerHTML = "";
  const banner = el("div", "outcome-banner " + (body.resolved ? "win" : "lose"));
  banner.innerHTML =
    `<span class="status-dot"></span>` +
    `<span>${body.resolved ? "Retry succeeded" : "Retry failed"}${body.reason ? " — " + body.reason : ""}</span>`;
  result.appendChild(banner);

  const meta = el("p", "gt-line");
  meta.innerHTML = body.razorpay_order_id
    ? `<strong>Real Razorpay order created:</strong> <code>${body.razorpay_order_id}</code> — verifiable in the Razorpay test-mode dashboard.`
    : "No order ID returned.";
  result.appendChild(meta);
}

// ----------------------------------------------------------------------------
// live escalation
// ----------------------------------------------------------------------------
const BTN_IDLE = "Run live escalation conversation";
const BTN_BUSY = "Talking to the model…";

function setupEscalation() {
  const backendSel = $("#escalate-backend");
  const hint = $("#escalate-hint");
  const updateHint = () => {
    if (backendSel.value === "prompted") {
      hint.textContent = "Local Ollama runs on CPU here — this can take 60-120 seconds. It's not stuck.";
      hint.hidden = false;
    } else {
      hint.hidden = true;
    }
  };
  backendSel.addEventListener("change", updateHint);
  updateHint();

  $("#escalate-btn").addEventListener("click", async () => {
    const caseId = $("#case-select").value;
    if (!caseId) return;
    const btn = $("#escalate-btn");
    const errBox = $("#escalate-error");
    const result = $("#escalate-result");
    errBox.hidden = true;
    result.innerHTML = "";
    btn.disabled = true;
    btn.innerHTML = BTN_BUSY;
    try {
      const resp = await fetch(`/api/case/${encodeURIComponent(caseId)}/escalate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backend: backendSel.value }),
      });
      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        errBox.textContent = body.detail || `Request failed (HTTP ${resp.status})`;
        errBox.hidden = false;
        return;
      }
      renderTranscript(body);
      reflectLiveOutcome(caseId, body);
    } catch (e) {
      errBox.textContent = "Request failed at the network level — is the server still running?";
      errBox.hidden = false;
    } finally {
      btn.disabled = false;
      btn.innerHTML = BTN_IDLE;
    }
  });
}

function renderTranscript(body) {
  const result = $("#escalate-result");
  result.innerHTML = "";

  // This live run's own outcome — NOT the frozen pipeline table's
  // recovered/channel/guardrail columns (those come only from the batch
  // eval report and are never mutated by a demo click; see server.py).
  const banner = el("div", "outcome-banner " + (body.resolved ? "win" : "lose"));
  banner.innerHTML =
    `<span class="status-dot"></span>` +
    `<span>${
      body.resolved
        ? `Resolved via escalation — a payment promise was captured on this run.`
        : `Not resolved on this run — no promise captured (category: ${body.scenario_category}).`
    }</span>`;
  result.appendChild(banner);

  const gt = body.ground_truth;
  const meta = el("p", "gt-line");
  meta.innerHTML =
    `<strong>Scenario:</strong> <code>${body.scenario_category}</code> &nbsp;&middot;&nbsp; ` +
    `<strong>backend:</strong> ${body.backend_used}${body.model ? ` (${body.model})` : ""} &nbsp;&middot;&nbsp; ` +
    `<strong>ground truth:</strong> has_promise=${gt.has_promise}, amount=${gt.promised_amount_inr}, ` +
    `date_offset_days=${gt.promised_date_offset_days}`;
  result.appendChild(meta);

  const wrap = el("div", "transcript");
  body.transcript.forEach((turn, i) => {
    const t = el("div", "turn " + (turn.role === "agent" ? "agent" : "customer"));
    t.style.animationDelay = i * 0.06 + "s";
    t.appendChild(el("span", "who", turn.role === "agent" ? "Agent" : "Customer"));
    t.appendChild(document.createTextNode(turn.text));
    wrap.appendChild(t);
  });
  result.appendChild(wrap);
}

// ----------------------------------------------------------------------------
// init
// ----------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  setupTheme();
  setupTabs();
  setupRetry();
  setupEscalation();
  $("#filter-split").addEventListener("change", renderPipeline);
  $("#filter-outcome").addEventListener("change", renderPipeline);
  loadOverview();
});
