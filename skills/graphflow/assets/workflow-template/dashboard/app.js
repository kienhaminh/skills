"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const POLL_MS = 2000;
const STATUS_ORDER = ["complete", "active", "ready", "waiting_user", "waiting_approval", "waiting_external", "stale", "blocked", "failed", "pending", "expanded"];
const STATUS_COLORS = {
  complete: "#159447",
  active: "#1769e0",
  ready: "#e89b0c",
  waiting_user: "#7f56d9",
  waiting_approval: "#dc6803",
  waiting_external: "#0e9384",
  stale: "#b54708",
  blocked: "#d92d45",
  failed: "#d92d45",
  pending: "#98a2b3",
  expanded: "#667085",
};

const elements = {
  title: document.querySelector("#workflow-title"),
  workflowId: document.querySelector("#workflow-id"),
  connectionDot: document.querySelector("#connection-dot"),
  connectionLabel: document.querySelector("#connection-label"),
  lastRefresh: document.querySelector("#last-refresh"),
  refreshButton: document.querySelector("#refresh-button"),
  notice: document.querySelector("#notice"),
  goal: document.querySelector("#goal-statement"),
  goalBinding: document.querySelector("#goal-binding"),
  planSummary: document.querySelector("#plan-summary"),
  optionalSummary: document.querySelector("#optional-summary"),
  requirements: document.querySelector("#requirements"),
  requirementCount: document.querySelector("#requirement-count"),
  memoryRevision: document.querySelector("#memory-revision"),
  memorySummary: document.querySelector("#memory-summary"),
  memoryEntries: document.querySelector("#memory-entries"),
  requestCount: document.querySelector("#request-count"),
  requestSummary: document.querySelector("#request-summary"),
  requestEntries: document.querySelector("#request-entries"),
  workspaceCount: document.querySelector("#workspace-count"),
  progressSummary: document.querySelector("#progress-summary"),
  progressEntries: document.querySelector("#progress-entries"),
  search: document.querySelector("#node-search"),
  statusFilters: document.querySelector("#status-filters"),
  kindFilter: document.querySelector("#kind-filter"),
  clearFilters: document.querySelector("#clear-filters"),
  phase: document.querySelector("#phase-label"),
  readyFrontier: document.querySelector("#ready-frontier"),
  viewport: document.querySelector("#graph-viewport"),
  layers: document.querySelector("#graph-layers"),
  edges: document.querySelector("#edge-layer"),
  fitButton: document.querySelector("#fit-button"),
  inspector: document.querySelector("#inspector"),
  inspectorContent: document.querySelector("#inspector-content"),
  closeInspector: document.querySelector("#close-inspector"),
  metrics: {
    complete: document.querySelector("#metric-complete"),
    active: document.querySelector("#metric-active"),
    blocked: document.querySelector("#metric-blocked"),
    ready: document.querySelector("#metric-ready"),
    nodeLabel: document.querySelector("#node-progress-label"),
    nodeBar: document.querySelector("#node-progress-bar"),
    tokenLabel: document.querySelector("#token-progress-label"),
    tokenBar: document.querySelector("#token-progress-bar"),
  },
};

const state = {
  graph: null,
  runtime: null,
  runtimeError: null,
  memory: null,
  memoryError: null,
  requests: [],
  requestsError: null,
  progress: [],
  progressError: null,
  workspaces: [],
  workspacesError: null,
  checkout: null,
  checkoutError: null,
  analysis: null,
  selectedId: null,
  query: "",
  kind: "all",
  statuses: new Set(STATUS_ORDER),
  lastGoodAt: null,
  loading: false,
};

function createElement(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function createSvgElement(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  return node;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function percent(value, total) {
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)));
}

function formatTokens(value) {
  const numeric = Number(value) || 0;
  if (numeric >= 1000) return `${(numeric / 1000).toFixed(numeric >= 10000 ? 0 : 1)}k`;
  return String(numeric);
}

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function unique(values) {
  return [...new Set(values)];
}

function humanizeId(value) {
  const text = String(value || "workflow").replace(/[-_]+/g, " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : "Workflow";
}

function humanizeStatus(value) {
  return String(value || "pending").replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());
}

function analyzeGraph(graph) {
  const errors = [];
  const nodes = asArray(graph.nodes);
  const requirements = asArray(asObject(graph.objective).requirements);
  const nodeMap = new Map();
  const requirementMap = new Map();
  const coverage = new Map();
  const dependents = new Map();

  for (const requirement of requirements) {
    if (!requirement || typeof requirement.id !== "string") {
      errors.push("A requirement is missing a valid ID.");
      continue;
    }
    if (requirementMap.has(requirement.id)) errors.push(`Duplicate requirement ${requirement.id}.`);
    requirementMap.set(requirement.id, requirement);
    coverage.set(requirement.id, []);
  }

  for (const node of nodes) {
    if (!node || typeof node.id !== "string") {
      errors.push("A node is missing a valid ID.");
      continue;
    }
    if (nodeMap.has(node.id)) errors.push(`Duplicate node ${node.id}.`);
    nodeMap.set(node.id, node);
    dependents.set(node.id, []);
  }

  for (const node of nodes) {
    if (!nodeMap.has(node.id)) continue;
    for (const dependency of asArray(node.depends_on)) {
      if (!nodeMap.has(dependency)) errors.push(`${node.id} depends on unknown node ${dependency}.`);
      else dependents.get(dependency).push(node.id);
    }
    if (node.parent !== null && node.parent !== undefined && !nodeMap.has(node.parent)) {
      errors.push(`${node.id} has unknown parent ${node.parent}.`);
    }
    for (const requirementId of asArray(node.covers)) {
      if (!coverage.has(requirementId)) errors.push(`${node.id} covers unknown requirement ${requirementId}.`);
      else coverage.get(requirementId).push(node.id);
    }
  }

  for (const [requirementId, owners] of coverage) {
    if (owners.length === 0) errors.push(`Requirement ${requirementId} is uncovered.`);
    if (owners.length > 1) errors.push(`Requirement ${requirementId} is covered by ${owners.join(", ")}.`);
  }

  const adjacency = new Map([...nodeMap.keys()].map((id) => [id, []]));
  const indegree = new Map([...nodeMap.keys()].map((id) => [id, 0]));
  const edgeKeys = new Set();
  const edges = [];

  function addEdge(source, target, type) {
    if (!nodeMap.has(source) || !nodeMap.has(target)) return;
    const key = `${source}\u0000${target}`;
    if (edgeKeys.has(key)) return;
    edgeKeys.add(key);
    adjacency.get(source).push(target);
    indegree.set(target, indegree.get(target) + 1);
    edges.push({ source, target, type });
  }

  for (const node of nodes) {
    for (const dependency of asArray(node.depends_on)) addEdge(dependency, node.id, "dependency");
    if (node.parent !== null && node.parent !== undefined) addEdge(node.parent, node.id, "parent");
  }

  const queue = [...nodeMap.keys()].filter((id) => indegree.get(id) === 0).sort();
  const layerById = new Map([...nodeMap.keys()].map((id) => [id, 0]));
  let visited = 0;
  while (queue.length) {
    const id = queue.shift();
    visited += 1;
    for (const target of adjacency.get(id)) {
      layerById.set(target, Math.max(layerById.get(target), layerById.get(id) + 1));
      indegree.set(target, indegree.get(target) - 1);
      if (indegree.get(target) === 0) {
        queue.push(target);
        queue.sort();
      }
    }
  }
  if (visited !== nodeMap.size) {
    errors.push("The combined dependency and parent graph contains a cycle.");
    const fallbackLayer = Math.max(0, ...layerById.values()) + 1;
    for (const [id, degree] of indegree) if (degree > 0) layerById.set(id, fallbackLayer);
  }

  const ready = nodes.filter((node) => {
    if (node.kind === "expand" || node.status !== "pending") return false;
    return asArray(node.depends_on).every((dependency) => nodeMap.get(dependency)?.status === "complete");
  });
  const readyIds = new Set(ready.map((node) => node.id));
  const executable = nodes.filter((node) => node.kind !== "expand");
  const allExpanded = nodes.filter((node) => node.kind === "expand").every((node) => node.status === "expanded");
  const coverageExact = [...coverage.values()].every((owners) => owners.length === 1);
  const allComplete = executable.length > 0 && executable.every((node) => node.status === "complete");
  const completeNodes = executable.filter((node) => node.status === "complete");
  const intent = asObject(graph.intent_baseline);
  const questionGate = asObject(graph.question_gate);
  const integrity = asObject(graph.integrity);
  const verification = asObject(graph.verification);
  const intentReady = intent.required === false ? intent.status === "not_required" : intent.status === "approved";
  const questionsReady = questionGate.status === "clear" && asArray(questionGate.unresolved_pivotal).length === 0 && asObject(questionGate.review).status === "locked";
  const integrityReady = integrity.status === "locked" && typeof integrity.plan_digest === "string" && typeof integrity.runner_digest === "string";
  const evidenceReady = ["verified", "complete_with_limits"].includes(verification.outcome);
  const lifecycleComplete = asObject(graph.lifecycle).status === "complete";
  const phase = errors.length
    ? "invalid"
    : allExpanded && allComplete && evidenceReady && lifecycleComplete
      ? "complete"
      : allExpanded && coverageExact && intentReady && questionsReady && integrityReady
        ? "executable"
        : "draft";
  const plannedTokens = executable.reduce((sum, node) => sum + (Number(asObject(node.budget).tokens) || 0), 0);
  const completeTokens = completeNodes.reduce((sum, node) => sum + (Number(asObject(node.budget).tokens) || 0), 0);
  const usedTokens = executable.reduce((sum, node) => sum + (Number(asObject(node.runtime).tokens_used) || 0), 0);

  return {
    errors,
    nodes,
    requirements,
    nodeMap,
    coverage,
    dependents,
    edges,
    layerById,
    ready,
    readyIds,
    executable,
    phase,
    nodeProgress: percent(completeNodes.length, executable.length),
    tokenProgress: percent(completeTokens, plannedTokens),
    plannedTokens,
    usedTokens,
  };
}

function displayStatus(node, analysis) {
  return analysis.readyIds.has(node.id) ? "ready" : node.status || "pending";
}

function setConnection(mode, label) {
  elements.connectionDot.className = `connection-dot ${mode}`.trim();
  elements.connectionLabel.textContent = label;
}

function showNotice(messages) {
  if (!messages.length) {
    elements.notice.hidden = true;
    elements.notice.textContent = "";
    return;
  }
  elements.notice.hidden = false;
  elements.notice.textContent = messages.join(" ");
}

function renderHeader() {
  const graph = state.graph;
  const goal = asObject(graph.objective);
  elements.title.textContent = humanizeId(graph.workflow_id);
  elements.workflowId.textContent = `${graph.workflow_id || "unnamed-workflow"} · workflow DAG`;
  document.title = `${graph.workflow_id || "Workflow"} · dashboard`;
  elements.goal.textContent = goal.statement || "No objective statement.";
  const lifecycle = asObject(graph.lifecycle);
  const intent = asObject(graph.intent_baseline);
  const questionGate = asObject(graph.question_gate);
  const questionReview = asObject(questionGate.review);
  const verification = asObject(graph.verification);
  const integrity = asObject(graph.integrity);
  const scheduler = asObject(asObject(state.runtime).scheduler);
  const intentLabel = intent.required === false ? "not required" : intent.status || "missing";
  const integrityLabel = `${integrity.level || "missing"}/${integrity.status || "missing"}`;
  elements.goalBinding.textContent = `Lifecycle: ${lifecycle.status || "unknown"} · Runner: ${scheduler.status || "unknown"} · Caller: optional · Questions: ${questionGate.status || "missing"}/${questionReview.status || "missing"} · Intent: ${intentLabel} · Integrity: ${integrityLabel} · Evidence: ${verification.outcome || "missing"}`;
  elements.planSummary.textContent = state.runtimeError
    ? `Runtime unavailable: ${state.runtimeError}`
    : `Persistent DAG runner · caller-independent · ${scheduler.blocker || "no workflow-wide blocker"}`;
  const optional = asArray(graph.optional_work);
  const deferred = optional.filter((item) => asObject(item).status === "deferred").length;
  elements.optionalSummary.textContent = `${optional.length} captured · ${deferred} deferred`;
  elements.lastRefresh.textContent = state.lastGoodAt ? `Refreshed ${state.lastGoodAt.toLocaleTimeString()}` : "Not refreshed";
}

function renderMetrics() {
  const { nodes, ready, nodeProgress, tokenProgress, usedTokens, plannedTokens } = state.analysis;
  const count = (status) => nodes.filter((node) => node.status === status).length;
  elements.metrics.complete.textContent = count("complete");
  elements.metrics.active.textContent = count("active");
  elements.metrics.blocked.textContent = count("blocked") + count("failed") + count("stale") + count("waiting_user") + count("waiting_approval") + count("waiting_external");
  elements.metrics.ready.textContent = ready.length;
  elements.metrics.nodeLabel.textContent = `${nodeProgress}%`;
  elements.metrics.nodeBar.style.width = `${nodeProgress}%`;
  elements.metrics.tokenLabel.textContent = `${tokenProgress}% · ${formatTokens(usedTokens)} / ${formatTokens(plannedTokens)}`;
  elements.metrics.tokenBar.style.width = `${tokenProgress}%`;
}

function renderRequirements() {
  const { requirements, coverage, nodeMap } = state.analysis;
  elements.requirements.replaceChildren();
  elements.requirementCount.textContent = String(requirements.length);
  for (const requirement of requirements) {
    const owners = coverage.get(requirement.id) || [];
    const complete = owners.length === 1 && nodeMap.get(owners[0])?.status === "complete";
    const invalid = owners.length !== 1;
    const item = createElement("li", `requirement${complete ? " done" : ""}${invalid ? " invalid" : ""}`);
    const mark = createElement("span", "requirement-mark", complete ? "✓" : invalid ? "!" : "");
    const copy = createElement("span", "", requirement.text || requirement.id);
    item.append(mark, copy);
    elements.requirements.append(item);
  }
}

function renderMemory() {
  const memory = asObject(state.memory);
  const entries = asArray(memory.entries).filter((entry) => asObject(entry).status === "active");
  elements.memoryRevision.textContent = Number.isInteger(memory.revision) ? `r${memory.revision}` : "r—";
  elements.memorySummary.textContent = state.memoryError
    ? `Unavailable: ${state.memoryError}`
    : `${entries.length} active · selective node capsules`;
  elements.memoryEntries.replaceChildren();
  const visible = entries
    .filter((entry) => entry.pivotal || ["decision", "risk", "question", "handoff"].includes(entry.kind))
    .slice(0, 8);
  for (const entry of visible) {
    const item = createElement("li", `requirement${entry.kind === "risk" || entry.kind === "question" ? " invalid" : ""}`);
    item.append(
      createElement("span", "requirement-mark", entry.pivotal ? "!" : "·"),
      createElement("span", "", `${entry.kind || "entry"}: ${entry.summary || entry.id}`),
    );
    elements.memoryEntries.append(item);
  }
  if (!visible.length) elements.memoryEntries.append(createElement("li", "", "No active pivotal memory."));
}

function renderRequests() {
  const requests = asArray(state.requests);
  const pending = requests.filter((request) => ["pending", "approved"].includes(asObject(request).status));
  elements.requestCount.textContent = String(pending.length);
  elements.requestSummary.textContent = state.requestsError
    ? `Unavailable: ${state.requestsError}`
    : `${pending.length} awaiting action · ${requests.length} retained`;
  elements.requestEntries.replaceChildren();
  for (const request of pending.slice(0, 8)) {
    const triage = asObject(request.triage);
    const item = createElement("li", "requirement invalid");
    item.append(
      createElement("span", "requirement-mark", "!"),
      createElement("span", "", `${request.node_id || request.broker || "workflow"}: ${request.question || request.request_id} · ${triage.blocking_scope || "unknown"}/${triage.resolution_mode || "unknown"}`),
    );
    if (request.broker === "delivery") {
      item.append(createElement(
        "span",
        "request-detail",
        `Commit\n${triage.commit_subject || ""}\n\n${triage.commit_body || ""}\n\nPull request\n${triage.pull_request_title || ""}\n\n${triage.pull_request_body || ""}`,
      ));
    }
    elements.requestEntries.append(item);
  }
  if (!pending.length) elements.requestEntries.append(createElement("li", "", "No pending confirmation."));
}

function progressFor(nodeId) {
  return asArray(state.progress).find((item) => asObject(item).node_id === nodeId) || {};
}

function workspaceFor(nodeId) {
  return asArray(state.workspaces).find((item) => asObject(item).node_id === nodeId) || {};
}

function renderExecutionTrust() {
  const workspaces = asArray(state.workspaces);
  const progress = asArray(state.progress);
  const runtime = asObject(state.runtime);
  const delivery = asObject(runtime.delivery);
  const decomposition = asObject(runtime.decomposition);
  const checkout = asObject(state.checkout);
  const errors = [state.workspacesError, state.progressError, state.checkoutError].filter(Boolean);
  elements.workspaceCount.textContent = String(workspaces.length);
  elements.progressSummary.textContent = errors.length
    ? `Unavailable: ${errors.join("; ")}`
    : `${progress.filter((item) => ["running", "executor_exited", "scope_checking", "evidence_running", "verifier_running"].includes(asObject(item).phase)).length} active · ${workspaces.length} registered · checkout ${checkout.status || "unknown"} · decomposition ${decomposition.status || "unknown"} · delivery ${delivery.status || "unknown"}`;
  elements.progressEntries.replaceChildren();
  const checkoutControls = [checkout.branch_changed ? "branch" : null, checkout.head_changed ? "HEAD" : null, checkout.git_metadata_changed ? "Git metadata" : null].filter(Boolean);
  elements.progressEntries.append(createElement("li", `requirement${checkout.status !== "clear" ? " invalid" : ""}`, `Primary checkout: ${checkout.status || "unknown"} · baseline dirty ${checkout.baseline_dirty_paths ?? "?"} · current dirty ${checkout.current_dirty_paths ?? "?"}${checkoutControls.length ? ` · changed ${checkoutControls.join(", ")}` : ""}`));
  for (const change of asArray(checkout.changes).slice(0, 8)) {
    const value = asObject(change);
    elements.progressEntries.append(createElement("li", "requirement invalid", `Checkout drift: ${value.path || "unknown"} · ${value.change || "changed"} · owners ${asArray(value.declared_owners).join(", ") || "none"}`));
  }
  elements.progressEntries.append(createElement("li", `requirement${["blocked", "waiting_external"].includes(delivery.status) ? " invalid" : ""}`, `Ship: ${delivery.adapter || "unconfigured"} · ${delivery.status || "unknown"}${delivery.head_branch ? ` · ${delivery.head_branch} → ${delivery.base_branch}` : ""}`));
  elements.progressEntries.append(createElement(
    "li",
    `requirement${decomposition.status === "blocked" ? " invalid" : decomposition.status === "waiting_rebase" ? " warning" : ""}`,
    `Structural decomposition: ${decomposition.status || "unknown"} · revision ${decomposition.revision ?? 0}${decomposition.active_node ? ` · node ${decomposition.active_node}` : ""}`,
  ));
  for (const item of progress.slice(0, 10)) {
    const progressValue = asObject(item);
    const workspace = workspaceFor(progressValue.node_id);
    const label = `${progressValue.node_id}: ${progressValue.phase || "unknown"} · ${workspace.mode || "workspace?"} · ${workspace.branch || "unbound"}`;
    elements.progressEntries.append(createElement("li", `requirement${progressValue.phase === "rejected" ? " invalid" : ""}`, label));
  }
  if (!progress.length) elements.progressEntries.append(createElement("li", "", "No live node progress yet."));
}

function renderFilters() {
  const counts = new Map(STATUS_ORDER.map((status) => [status, 0]));
  for (const node of state.analysis.nodes) {
    const status = displayStatus(node, state.analysis);
    counts.set(status, (counts.get(status) || 0) + 1);
  }
  elements.statusFilters.replaceChildren();
  for (const status of STATUS_ORDER.filter((value) => counts.get(value))) {
    const label = createElement("label", "filter-row");
    const input = createElement("input");
    input.type = "checkbox";
    input.checked = state.statuses.has(status);
    input.addEventListener("change", () => {
      if (input.checked) state.statuses.add(status);
      else state.statuses.delete(status);
      renderGraph();
    });
    const dot = createElement("i", `dot ${status}`);
    const text = createElement("span", "", humanizeStatus(status));
    const output = createElement("output", "", counts.get(status));
    label.append(input, dot, text, output);
    elements.statusFilters.append(label);
  }

  const kinds = unique(state.analysis.nodes.map((node) => node.kind).filter(Boolean)).sort();
  const current = state.kind;
  elements.kindFilter.replaceChildren(createOption("all", "All kinds"), ...kinds.map((kind) => createOption(kind, kind)));
  elements.kindFilter.value = kinds.includes(current) ? current : "all";
  state.kind = elements.kindFilter.value;
}

function createOption(value, label) {
  const option = createElement("option", "", label[0].toUpperCase() + label.slice(1));
  option.value = value;
  return option;
}

function nodeMatchesFilters(node) {
  const status = displayStatus(node, state.analysis);
  if (!state.statuses.has(status)) return false;
  if (state.kind !== "all" && node.kind !== state.kind) return false;
  const query = state.query.trim().toLowerCase();
  if (!query) return true;
  const runtime = asObject(node.runtime);
  const executor = asObject(node.executor);
  const searchable = [node.id, node.title, node.kind, node.status, node.isolation, executor.type, executor.spec, runtime.agent, runtime.model, runtime.reasoning_effort, ...asArray(node.methods), ...asArray(node.skills), ...asArray(node.covers)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return searchable.includes(query);
}

function renderPhase() {
  const { phase, ready, errors } = state.analysis;
  elements.phase.textContent = phase;
  elements.phase.className = `phase${phase === "invalid" ? " invalid" : ""}`;
  elements.readyFrontier.textContent = `Ready: ${ready.length ? ready.map((node) => node.id).join(", ") : "none"}`;
  showNotice(state.memoryError ? [...errors, `Shared memory: ${state.memoryError}`] : errors);
}

function renderGraph() {
  const visibleNodes = state.analysis.nodes.filter(nodeMatchesFilters);
  const visibleIds = new Set(visibleNodes.map((node) => node.id));
  if (state.selectedId && !visibleIds.has(state.selectedId)) state.selectedId = visibleNodes[0]?.id || null;
  const layerGroups = new Map();
  for (const node of visibleNodes) {
    const layer = state.analysis.layerById.get(node.id) || 0;
    if (!layerGroups.has(layer)) layerGroups.set(layer, []);
    layerGroups.get(layer).push(node);
  }

  elements.layers.replaceChildren();
  for (const layer of [...layerGroups.keys()].sort((left, right) => left - right)) {
    const column = createElement("section", "graph-layer");
    column.dataset.layer = String(layer);
    column.append(createElement("div", "layer-label", `Stage ${layer}`));
    for (const node of layerGroups.get(layer).sort((left, right) => left.id.localeCompare(right.id))) {
      column.append(createNodeCard(node));
    }
    elements.layers.append(column);
  }

  if (!visibleNodes.length) {
    const empty = createElement("p", "empty-state", "No nodes match the current filters.");
    elements.layers.append(empty);
  }

  requestAnimationFrame(() => drawEdges(visibleIds));
  renderInspector();
}

function createNodeCard(node) {
  const status = displayStatus(node, state.analysis);
  const runtime = asObject(node.runtime);
  const executor = asObject(node.executor);
  const liveProgress = progressFor(node.id);
  const workspace = workspaceFor(node.id);
  const card = createElement("button", `node-card${state.selectedId === node.id ? " selected" : ""}${status === "ready" ? " ready-node" : ""}`);
  card.type = "button";
  card.dataset.nodeId = node.id;
  card.style.setProperty("--status-color", STATUS_COLORS[status] || STATUS_COLORS.pending);
  card.setAttribute("aria-label", `${node.id} ${node.title}, ${status}`);
  card.append(createElement("span", "node-id", `${node.id} · ${node.kind}`));
  card.append(createElement("strong", "node-title", node.title || "Untitled node"));
  card.append(createElement("div", "node-meta", `executor: ${executor.type || "none"} · ${liveProgress.phase || "no live phase"} · ${workspace.branch || "workspace unbound"}`));
  const footer = createElement("div", "node-footer");
  const statusLabel = createElement("span", "node-status");
  statusLabel.append(createElement("i", `dot ${status}`), createElement("span", "", humanizeStatus(status)));
  footer.append(statusLabel, createElement("span", "", `${formatTokens(runtime.tokens_used)} / ${formatTokens(asObject(node.budget).tokens)} tokens`));
  card.append(footer);
  card.addEventListener("click", () => {
    state.selectedId = node.id;
    renderGraph();
    elements.inspector.classList.add("open");
  });
  return card;
}

function drawEdges(visibleIds) {
  const viewportRect = elements.viewport.getBoundingClientRect();
  const width = Math.max(elements.viewport.clientWidth, elements.viewport.scrollWidth);
  const height = Math.max(elements.viewport.clientHeight, elements.viewport.scrollHeight);
  elements.edges.setAttribute("width", String(width));
  elements.edges.setAttribute("height", String(height));
  elements.edges.setAttribute("viewBox", `0 0 ${width} ${height}`);
  elements.edges.replaceChildren();

  const definitions = createSvgElement("defs");
  const marker = createSvgElement("marker", {
    id: "arrowhead",
    viewBox: "0 0 8 8",
    refX: "7",
    refY: "4",
    markerWidth: "6",
    markerHeight: "6",
    orient: "auto-start-reverse",
  });
  marker.append(createSvgElement("path", { d: "M 0 0 L 8 4 L 0 8 z", fill: "#98a2b3" }));
  definitions.append(marker);
  elements.edges.append(definitions);

  for (const edge of state.analysis.edges) {
    if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue;
    const source = elements.layers.querySelector(`[data-node-id="${CSS.escape(edge.source)}"]`);
    const target = elements.layers.querySelector(`[data-node-id="${CSS.escape(edge.target)}"]`);
    if (!source || !target) continue;
    const sourceRect = source.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const startX = sourceRect.right - viewportRect.left + elements.viewport.scrollLeft;
    const startY = sourceRect.top + sourceRect.height / 2 - viewportRect.top + elements.viewport.scrollTop;
    const endX = targetRect.left - viewportRect.left + elements.viewport.scrollLeft;
    const endY = targetRect.top + targetRect.height / 2 - viewportRect.top + elements.viewport.scrollTop;
    const control = Math.max(34, (endX - startX) * 0.48);
    const path = createSvgElement("path", {
      d: `M ${startX} ${startY} C ${startX + control} ${startY}, ${endX - control} ${endY}, ${endX} ${endY}`,
      class: `edge-path${edge.type === "parent" ? " parent-edge" : ""}`,
      "marker-end": "url(#arrowhead)",
    });
    elements.edges.append(path);
  }
}

function renderInspector() {
  const node = state.analysis.nodeMap.get(state.selectedId);
  elements.inspectorContent.replaceChildren();
  if (!node) {
    elements.inspectorContent.append(createElement("p", "empty-state", "Select a node to inspect its contract."));
    return;
  }

  const status = displayStatus(node, state.analysis);
  const runtime = asObject(node.runtime);
  const liveProgress = progressFor(node.id);
  const workspace = workspaceFor(node.id);
  const heading = createElement("header", "selected-title");
  heading.append(createElement("small", "", `${node.id} · ${node.kind}`), createElement("h2", "", node.title || "Untitled node"));
  const statusLabel = createElement("span", "node-status");
  statusLabel.append(createElement("i", `dot ${status}`), createElement("span", "", humanizeStatus(status)));
  heading.append(statusLabel);
  elements.inspectorContent.append(heading);

  const facts = createElement("dl", "key-values");
  appendFact(facts, "Owner agent", runtime.agent || "Unassigned");
  appendFact(facts, "Executor", asObject(node.executor).type || "None");
  appendFact(facts, "Executor spec", asObject(node.executor).spec || "None");
  appendFact(facts, "Model", runtime.model || "Unassigned");
  appendFact(facts, "Reasoning", runtime.reasoning_effort || "—");
  appendFact(facts, "Isolation", node.isolation || "Unspecified");
  appendFact(facts, "Trust phase", liveProgress.phase || "No live phase");
  appendFact(facts, "Workspace", workspace.workspace_id || "Unbound");
  appendFact(facts, "Branch / HEAD", `${workspace.branch || "—"} @ ${(workspace.head_sha || "—").slice(0, 12)}`);
  appendFact(facts, "Started", formatTime(runtime.started_at));
  appendFact(facts, "Updated", formatTime(runtime.updated_at));
  appendFact(facts, "Heartbeat", formatTime(runtime.heartbeat_at));
  appendFact(facts, "Routing", runtime.routing_reason || "No routing reason recorded.");
  appendFact(facts, "Summary", runtime.summary || "No handoff yet.");
  appendFact(facts, "Blocker", runtime.blocker || "None");
  elements.inspectorContent.append(createDetailSection("Runtime", facts));

  const dependencies = asArray(node.depends_on);
  const dependents = state.analysis.dependents.get(node.id) || [];
  const relationshipList = createElement("ul", "detail-list");
  for (const dependency of dependencies) {
    const dependencyNode = state.analysis.nodeMap.get(dependency);
    const item = createElement("li");
    item.append(createElement("span", "check-mark", dependencyNode?.status === "complete" ? "✓" : "○"), createElement("span", "", `Depends on ${dependency} · ${dependencyNode?.status || "unknown"}`));
    relationshipList.append(item);
  }
  for (const dependent of dependents) {
    const item = createElement("li");
    item.append(createElement("span", "", "→"), createElement("span", "", `Unlocks ${dependent}`));
    relationshipList.append(item);
  }
  if (!relationshipList.childNodes.length) relationshipList.append(createElement("li", "", "No dependencies or dependents."));
  elements.inspectorContent.append(createDetailSection("Graph relationships", relationshipList));

  elements.inspectorContent.append(createDetailSection("Methods", createTagList(asArray(node.methods), "No named methods.")));
  elements.inspectorContent.append(createDetailSection("Skills", createTagList(asArray(node.skills), "No selected skills.")));

  const acceptance = createElement("ul", "detail-list");
  for (const criterion of asArray(node.acceptance)) {
    const item = createElement("li");
    item.append(createElement("span", "check-mark", node.status === "complete" ? "✓" : "○"), createElement("span", "", criterion));
    acceptance.append(item);
  }
  if (!acceptance.childNodes.length) acceptance.append(createElement("li", "", "No acceptance checks declared."));
  elements.inspectorContent.append(createDetailSection("Acceptance checks", acceptance));

  const scopeContainer = createElement("div");
  const scope = asObject(node.scope);
  for (const key of ["read", "write", "artifacts", "decisions", "forbidden"]) {
    const group = createElement("div", "scope-group");
    group.append(createElement("span", "", key), createTagList(asArray(scope[key]), "None"));
    scopeContainer.append(group);
  }
  elements.inspectorContent.append(createDetailSection("Scopes", scopeContainer));

  const outputs = createElement("ul", "detail-list");
  for (const output of asArray(node.outputs)) {
    const item = createElement("li");
    item.append(createElement("span", "", "↳"), createElement("span", "", `${output.id}: ${output.artifact || output.description || "declared output"}`));
    outputs.append(item);
  }
  if (!outputs.childNodes.length) outputs.append(createElement("li", "", "No outputs declared."));
  elements.inspectorContent.append(createDetailSection("Outputs", outputs));

  const budget = Number(asObject(node.budget).tokens) || 0;
  const used = Number(runtime.tokens_used) || 0;
  const tokenBox = createElement("div");
  const tokenLine = createElement("div", "token-line");
  tokenLine.append(createElement("span", "", `${formatTokens(used)} used`), createElement("strong", "", `${formatTokens(budget)} planned`));
  const track = createElement("div", "progress-track");
  const bar = createElement("span");
  bar.style.width = `${percent(used, budget)}%`;
  track.append(bar);
  tokenBox.append(tokenLine, track);
  elements.inspectorContent.append(createDetailSection("Token budget", tokenBox));

  const retry = asObject(node.retry);
  const retryFacts = createElement("dl", "key-values");
  appendFact(retryFacts, "Attempts", `${Number(retry.attempts) || 0} / ${Number(retry.max_attempts) || 0}`);
  appendFact(retryFacts, "Last failure", retry.last_failure_class || "None");
  elements.inspectorContent.append(createDetailSection("Retry policy", retryFacts));
}

function appendFact(list, term, description) {
  list.append(createElement("dt", "", term), createElement("dd", "", description));
}

function createDetailSection(title, content) {
  const section = createElement("section", "detail-section");
  section.append(createElement("h3", "", title), content);
  return section;
}

function createTagList(values, fallback) {
  const list = createElement("div", "tag-list");
  if (!values.length) list.append(createElement("span", "tag", fallback));
  else for (const value of values) list.append(createElement("span", "tag", value));
  return list;
}

function renderAll() {
  renderHeader();
  renderMetrics();
  renderRequirements();
  renderMemory();
  renderRequests();
  renderExecutionTrust();
  renderFilters();
  renderPhase();
  renderGraph();
}

async function loadGraph() {
  if (state.loading) return;
  state.loading = true;
  elements.refreshButton.disabled = true;
  try {
    const timestamp = Date.now();
    const [response, memoryResponse, runtimeResponse, requestsResponse, progressResponse, workspacesResponse, checkoutResponse] = await Promise.all([
      fetch(`../graph.json?ts=${timestamp}`, { cache: "no-store" }),
      fetch(`../memory/state.json?ts=${timestamp}`, { cache: "no-store" }),
      fetch(`../runtime.json?ts=${timestamp}`, { cache: "no-store" }),
      fetch(`../requests.json?ts=${timestamp}`, { cache: "no-store" }),
      fetch(`../progress.json?ts=${timestamp}`, { cache: "no-store" }),
      fetch(`../workspaces.json?ts=${timestamp}`, { cache: "no-store" }),
      fetch(`../checkout.json?ts=${timestamp}`, { cache: "no-store" }),
    ]);
    if (!response.ok) throw new Error(`Graph request returned HTTP ${response.status}.`);
    const graph = await response.json();
    if (memoryResponse.ok) {
      try {
        state.memory = await memoryResponse.json();
        state.memoryError = state.memory?.workflow_id === graph.workflow_id ? null : "workflow_id does not match graph";
      } catch (error) {
        state.memoryError = `invalid JSON: ${error instanceof Error ? error.message : String(error)}`;
      }
    } else {
      state.memoryError = `HTTP ${memoryResponse.status}`;
    }
    if (runtimeResponse.ok) {
      try {
        state.runtime = await runtimeResponse.json();
        state.runtimeError = state.runtime?.workflow_id === graph.workflow_id ? null : "workflow_id does not match graph";
      } catch (error) {
        state.runtimeError = `invalid JSON: ${error instanceof Error ? error.message : String(error)}`;
      }
    } else {
      state.runtimeError = `HTTP ${runtimeResponse.status}`;
    }
    if (requestsResponse.ok) {
      try {
        const payload = await requestsResponse.json();
        state.requests = asArray(payload.requests);
        state.requestsError = null;
      } catch (error) {
        state.requestsError = `invalid JSON: ${error instanceof Error ? error.message : String(error)}`;
      }
    } else {
      state.requestsError = `HTTP ${requestsResponse.status}`;
    }
    if (progressResponse.ok) {
      try {
        state.progress = asArray((await progressResponse.json()).progress);
        state.progressError = null;
      } catch (error) {
        state.progressError = `invalid JSON: ${error instanceof Error ? error.message : String(error)}`;
      }
    } else state.progressError = `HTTP ${progressResponse.status}`;
    if (workspacesResponse.ok) {
      try {
        state.workspaces = asArray((await workspacesResponse.json()).workspaces);
        state.workspacesError = null;
      } catch (error) {
        state.workspacesError = `invalid JSON: ${error instanceof Error ? error.message : String(error)}`;
      }
    } else state.workspacesError = `HTTP ${workspacesResponse.status}`;
    if (checkoutResponse.ok) {
      try {
        state.checkout = await checkoutResponse.json();
        state.checkoutError = null;
      } catch (error) {
        state.checkoutError = `invalid JSON: ${error instanceof Error ? error.message : String(error)}`;
      }
    } else state.checkoutError = `HTTP ${checkoutResponse.status}`;
    state.graph = graph;
    state.analysis = analyzeGraph(graph);
    state.lastGoodAt = new Date();
    if (!state.selectedId || !state.analysis.nodeMap.has(state.selectedId)) {
      state.selectedId = state.analysis.nodes.find((node) => node.status === "active")?.id
        || state.analysis.nodes.find((node) => String(node.status).startsWith("waiting_") || node.status === "stale")?.id
        || state.analysis.ready[0]?.id
        || state.analysis.nodes[0]?.id
        || null;
    }
    setConnection("online", "Live");
    renderAll();
  } catch (error) {
    setConnection("stale", "Stale");
    showNotice([`Refresh failed: ${error instanceof Error ? error.message : String(error)} Last valid graph remains visible.`]);
  } finally {
    state.loading = false;
    elements.refreshButton.disabled = false;
  }
}

elements.refreshButton.addEventListener("click", loadGraph);
elements.search.addEventListener("input", () => {
  state.query = elements.search.value;
  renderGraph();
});
elements.kindFilter.addEventListener("change", () => {
  state.kind = elements.kindFilter.value;
  renderGraph();
});
elements.clearFilters.addEventListener("click", () => {
  state.query = "";
  state.kind = "all";
  state.statuses = new Set(STATUS_ORDER);
  elements.search.value = "";
  renderFilters();
  renderGraph();
});
elements.fitButton.addEventListener("click", () => elements.viewport.scrollTo({ top: 0, left: 0, behavior: "smooth" }));
elements.closeInspector.addEventListener("click", () => {
  state.selectedId = null;
  elements.inspector.classList.remove("open");
  renderGraph();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) loadGraph();
});
window.addEventListener("resize", () => state.analysis && requestAnimationFrame(() => drawEdges(new Set(state.analysis.nodes.filter(nodeMatchesFilters).map((node) => node.id)))));
new ResizeObserver(() => state.analysis && requestAnimationFrame(() => drawEdges(new Set(state.analysis.nodes.filter(nodeMatchesFilters).map((node) => node.id))))).observe(elements.layers);

loadGraph();
setInterval(() => {
  if (!document.hidden) loadGraph();
}, POLL_MS);
