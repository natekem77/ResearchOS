const state = {
  documents: [],
  papers: [],
  assets: [],
  spreadsheets: [],
  images: [],
  statistics: [],
  experiments: [],
  workflows: [],
  protocols: [],
  inventory: [],
  purchases: [],
  purchaseRequests: [],
  receiving: [],
  experimentDesigns: [],
  experimentDesignTemplates: [],
  plateLayouts: [],
  visualBuilders: [],
  visualBuilderDraft: null,
  visualBuilderUndo: [],
  visualBuilderRedo: [],
  designDueToday: null,
  designUpcoming: null,
  designImportPreview: null,
  inventoryStatus: null,
  purchaseSummary: null,
  purchaseImportTemplates: [],
  purchaseImportPreview: null,
  sessions: [],
  selectedExperimentIds: new Set(),
  health: null,
  auth: null,
  currentUser: null,
  currentPermissions: null,
  currentWorkspace: null,
  authReadiness: null,
  dailyDashboard: null,
  whiteboard: null,
  whiteboardRotationIndex: 0,
  intelligenceFilter: null,
  providerStatus: null,
  agentStatus: null,
  deploymentStatus: null,
  oneNoteReadiness: null,
  productionReadiness: null,
  extensions: null,
  ontology: {},
  graphStats: null,
  entryTemplates: [],
  pendingEntries: [],
  lastSync: null,
  searchTerms: [],
  activity: [],
  currentEntryDraft: null,
  currentSavedEntryId: null,
  assistantMode: "search",
  currentExperimentPlan: null,
  compactSummaries: {},
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const views = {
  dashboard: $("#dashboardView"),
  whiteboard: $("#whiteboardView"),
  "new-experiment": $("#newExperimentView"),
  sessions: $("#sessionsView"),
  "saved-drafts": $("#savedDraftsView"),
  savedDraftDetail: $("#savedDraftDetailView"),
  experiments: $("#experimentsView"),
  workflows: $("#workflowsView"),
  experimentDetail: $("#experimentDetailView"),
  protocols: $("#protocolsView"),
  protocolDetail: $("#protocolDetailView"),
  inventory: $("#inventoryView"),
  purchases: $("#purchasesView"),
  receiving: $("#receivingView"),
  documents: $("#documentsView"),
  assets: $("#assetsView"),
  assetDetail: $("#assetDetailView"),
  data: $("#dataView"),
  images: $("#imagesView"),
  statistics: $("#statisticsView"),
  literature: $("#literatureView"),
  graph: $("#graphView"),
  graphDetail: $("#graphDetailView"),
  entityList: $("#entityListView"),
  entityDetail: $("#entityDetailView"),
  search: $("#searchView"),
  chat: $("#chatView"),
  reasoning: $("#reasoningView"),
  planner: $("#plannerView"),
  "visual-builder": $("#visualBuilderView"),
  "design-planner": $("#designPlannerView"),
  "design-templates": $("#designTemplatesView"),
  "plate-layouts": $("#plateLayoutsView"),
  extensions: $("#extensionsView"),
  settings: $("#settingsView"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortText(value, length = 220) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= length ? text : `${text.slice(0, length).trim()}...`;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => undefined);
  });
}

function formatDate(value) {
  if (!value) return "No date";
  if (/^\d+$/.test(String(value))) {
    return new Date(Number(value) * 1000).toLocaleDateString();
  }
  return String(value);
}

function pathForDocument(documentId) {
  return state.documents.find((document) => document.id === documentId);
}

function graphEntityLink(type, name, label = name) {
  if (!name) return "";
  return `#/graph/${encodeURIComponent(type)}/${encodeURIComponent(name)}`;
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (error) {
      detail = `${response.status} ${response.statusText}`;
    }
    throw new Error(detail);
  }
  return response.json();
}

function highlightText(value) {
  let html = escapeHtml(value);
  const terms = unique([
    ...state.searchTerms,
    ...state.experiments.flatMap((experiment) => [
      experiment.experiment_id,
      ...(experiment.compounds || []),
      ...(experiment.markers || []),
    ]),
  ]).filter((term) => String(term).length > 1);

  for (const term of terms) {
    const escaped = escapeHtml(term).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    html = html.replace(new RegExp(`(${escaped})`, "gi"), "<mark>$1</mark>");
  }
  return html;
}

function setHeader(viewName, title) {
  $("#viewEyebrow").textContent = viewName;
  $("#viewTitle").textContent = title;
}

function setStatus() {
  const oneNoteStatus = state.providerStatus?.onenote_auth?.status;
  const providerText = oneNoteStatus === "connected" ? "OneNote connected" : "Markdown local";
  $("#providerStatus").textContent = `Provider: ${providerText}`;
  $("#providerStatus").className = `status-pill ${state.health ? "ok" : "warn"}`;
  const syncStatus = state.providerStatus?.onenote_sync?.status;
  $("#syncStatus").textContent = syncStatus === "available"
    ? "Sync: OneNote ready"
    : state.lastSync
    ? `Sync: ${state.lastSync.toLocaleTimeString()}`
    : "Sync: not loaded";
  renderWorkspaceSwitcher();
}

function renderWorkspaceSwitcher() {
  const target = $("#workspaceSwitcher");
  if (!target) return;
  const workspace = state.currentWorkspace || state.currentUser?.current_workspace || state.dailyDashboard?.workspace || {};
  const name = workspace.name || "Demo Lab Workspace";
  const workspaceId = workspace.workspace_id || "workspace:demo-lab";
  target.innerHTML = `<option value="${escapeHtml(workspaceId)}">${escapeHtml(name)}</option>`;
  target.disabled = true;
  target.title = "Workspace switching is scaffolded; strict workspace isolation is not enforced yet.";
}

function recordActivity(title, meta) {
  state.activity = [
    { title, meta, timestamp: new Date() },
    ...state.activity,
  ].slice(0, 8);
  renderTimeline();
}

function oneNoteDisplayStatus() {
  const auth = state.providerStatus?.onenote_auth;
  if (auth?.status === "connected" || auth?.authenticated) {
    return {
      label: "Connected",
      status: "ok",
      message: "OneNote delegated login is active. Read-only sync can run when notebook access is available.",
    };
  }
  if (auth?.status === "pending_ucsd_approval") {
    return {
      label: "Waiting for IT approval",
      status: "warn",
      message: "UCSD tenant approval is needed before lab OneNote notebooks can sync.",
    };
  }
  return {
    label: "Not connected",
    status: "warn",
    message: "Markdown demo mode is active. OneNote remains ready for login after app approval.",
  };
}

function newestPaper() {
  return [...state.papers].sort((a, b) => String(b.ingested_at).localeCompare(String(a.ingested_at)))[0];
}

function activateNav(name) {
  $$(`[data-nav='${name}']`).forEach((node) => node.classList.add("active"));
}

function route() {
  const pathView = window.location.pathname.replace(/^\//, "");
  const raw = window.location.hash.replace(/^#\/?/, "") || pathView || "dashboard";
  const [view, id, ...rest] = raw.split("/");

  $$(".view").forEach((node) => node.classList.remove("active"));
  $$(".side-nav a, .mobile-bottom-nav a").forEach((node) => node.classList.remove("active"));

  if (view === "experiments" && id) {
    views.experimentDetail.classList.add("active");
    activateNav("experiments");
    if (rest[0] === "workspace") {
      renderExperimentWorkspace(decodeURIComponent(id));
      setHeader("Experiment Workspace", "Unified research record");
    } else {
      renderExperimentDetail(decodeURIComponent(id));
      setHeader("Experiment Detail", "Experiment record");
    }
    return;
  }

  if (view === "protocols" && id) {
    views.protocolDetail.classList.add("active");
    activateNav("protocols");
    renderProtocolWorkspace(decodeURIComponent(id));
    setHeader("Protocol Workspace", "Protocol Intelligence");
    return;
  }

  if (view === "saved-drafts" && id) {
    views.savedDraftDetail.classList.add("active");
    activateNav("saved-drafts");
    renderSavedDraftDetail(decodeURIComponent(id));
    setHeader("Saved Drafts", "Draft Export");
    return;
  }

  if (view === "assets" && id) {
    views.assetDetail.classList.add("active");
    activateNav("assets");
    renderAssetDetail(decodeURIComponent(id));
    setHeader("Assets", "Asset Detail");
    return;
  }

  if (view === "graph") {
    if (id && rest.length) {
      views.graphDetail.classList.add("active");
      activateNav("graph");
      const entityName = decodeURIComponent(rest.join("/"));
      renderGraphEntity(decodeURIComponent(id), entityName);
      setHeader("Knowledge Graph", entityName);
      return;
    }
    views.graph.classList.add("active");
    activateNav("graph");
    renderGraphExplorer();
    setHeader("Knowledge Graph", "Graph Explorer");
    return;
  }

  if (["compounds", "markers", "cell-lines", "organoid-batches"].includes(view)) {
    const entityType = view;
    if (id) {
      views.entityDetail.classList.add("active");
      activateNav(entityType);
      renderEntityDetail(entityType, decodeURIComponent(id));
      setHeader("Retinal Ontology", decodeURIComponent(id));
      return;
    }
    views.entityList.classList.add("active");
    activateNav(entityType);
    renderEntityList(entityType);
    setHeader("Retinal Ontology", entityTitle(entityType));
    return;
  }

  const target = views[view] ? view : "dashboard";
  views[target].classList.add("active");
  activateNav(target);

  const titles = {
    dashboard: ["Dashboard", "ResearchOS Dashboard"],
    whiteboard: ["Whiteboard", "Laboratory situational awareness"],
    "new-experiment": ["New Experiment", "Dictation Draft"],
    sessions: ["Sessions", "Experiment Sessions"],
    "saved-drafts": ["Saved Drafts", "Pending Notebook Entries"],
    experiments: ["Experiments", "Experiment Index"],
    workflows: ["Workflows", "Research Workflow Engine"],
    protocols: ["Protocols", "Protocol Signals"],
    inventory: ["Inventory", "Lab Inventory"],
    purchases: ["Purchasing", "Oracle-ready Records"],
    receiving: ["Receiving", "Inventory Intake"],
    documents: ["Documents", "Document Library"],
    assets: ["Assets", "Research Asset Graph"],
    data: ["Data", "Quantitative Spreadsheets"],
    images: ["Images", "Microscopy Assets"],
    statistics: ["Statistics", "GraphPad Statistics"],
    literature: ["Literature", "Paper Library"],
    graph: ["Knowledge Graph", "Graph Explorer"],
    search: ["Search", "Search Research Notes"],
    chat: ["AI Chat", "Ask ResearchOS"],
    reasoning: ["Scientific Reasoning", "Evidence-Based Reasoning"],
    planner: ["Experiment Planner", "Plan Follow-up Experiment"],
    "design-planner": ["Design Planner", "Multi-condition Experiment Design"],
    extensions: ["Extensions", "Extension SDK"],
    settings: ["Settings", "Workspace Settings"],
  };
  setHeader(...titles[target]);
}

function allCompounds() {
  return (state.ontology.compounds || []).map((entity) => entity.name);
}

function allMarkers() {
  return (state.ontology.markers || []).map((entity) => entity.name);
}

function activeSession() {
  return state.sessions.find((session) => session.status === "active") || null;
}

function todaysSessions() {
  const today = new Date().toISOString().slice(0, 10);
  return state.sessions.filter((session) => String(session.start_time || "").startsWith(today));
}

function graphPadAssets() {
  return state.assets.filter((asset) => asset.provider === "graphpad");
}

function statisticsAssets() {
  return state.statistics.length
    ? state.statistics
    : state.assets.filter((asset) => asset.metadata?.statistics);
}

function microscopyImageAssets() {
  return state.images.length
    ? state.images
    : state.assets.filter((asset) => asset.provider === "microscopy" || ["image", "microscopy"].includes(asset.asset_type));
}

function renderMetrics() {
  $("#metricExperiments").textContent = state.experiments.length;
  $("#metricDocuments").textContent = state.documents.length;
  $("#metricPapers").textContent = state.papers.length;
  $("#metricAssets").textContent = state.assets.length;
  $("#metricGraphPadAssets").textContent = graphPadAssets().length;
  $("#metricCompounds").textContent = allCompounds().length;
  $("#metricMarkers").textContent = allMarkers().length;
  $("#metricCellLines").textContent = (state.ontology["cell-lines"] || []).length;
  $("#metricOrganoidBatches").textContent = (state.ontology["organoid-batches"] || []).length;
  $("#metricReadyDrafts").textContent = state.pendingEntries.filter((entry) => entry.status === "ready_for_onenote").length;
  $("#metricSessionsToday").textContent = todaysSessions().length;
}

function renderDailyDashboard() {
  const target = $("#dailyDashboardCards");
  const summary = $("#dailyDashboardSummary");
  if (!target || !summary) return;
  const dashboard = state.dailyDashboard;
  if (!dashboard) {
    summary.textContent = "Daily dashboard is loading local ResearchOS state.";
    target.innerHTML = `<div class="empty-state">Daily dashboard unavailable.</div>`;
    return;
  }
  summary.textContent = dashboard.assistant_summary?.text || "Daily dashboard generated from local ResearchOS records.";
  const workspace = state.currentWorkspace || dashboard.workspace || {};
  if (workspace.name) {
    summary.textContent = `${workspace.name}: ${summary.textContent}`;
  }
  const feed = dashboard.laboratory_intelligence_feed;
  if (feed && Array.isArray(feed.items)) {
    const items = state.intelligenceFilter
      ? feed.items.filter((item) => item.item_type === state.intelligenceFilter)
      : feed.items;
    const filters = feed.filters || [];
    target.innerHTML = `
      <div class="intelligence-toolbar">
        <button class="secondary-button ${state.intelligenceFilter ? "" : "active"}" type="button" data-intelligence-filter="">All</button>
        ${filters.map((filter) => `
          <button class="secondary-button ${state.intelligenceFilter === filter.item_type ? "active" : ""}" type="button" data-intelligence-filter="${escapeHtml(filter.item_type)}">
            ${escapeHtml(filter.item_type)} <span>${escapeHtml(filter.count)}</span>
          </button>
        `).join("")}
      </div>
      <div class="intelligence-feed">
        ${items.length ? items.map(renderIntelligenceFeedItem).join("") : `<div class="empty-state">No Laboratory Intelligence items match this filter.</div>`}
      </div>
      ${renderDashboardDesignReminders()}
    `;
    bindIntelligenceFeedControls();
    return;
  }
  target.innerHTML = (dashboard.sections || []).length
    ? dashboard.sections.map(renderDailyDashboardCard).join("") + renderDashboardDesignReminders()
    : `<div class="empty-state">No dashboard sections available.</div>`;
  bindDailyDashboardReorder();
}

function renderDashboardDesignReminders() {
  const due = state.designDueToday?.reminders || state.designDueToday?.events || [];
  const upcoming = state.designUpcoming?.reminders || state.designUpcoming?.events || [];
  return `
    <details class="daily-card" open>
      <summary><span>Experiment design reminders</span><small>${escapeHtml(due.length)} due today / ${escapeHtml(upcoming.length)} upcoming</small></summary>
      <div class="daily-card-items">
        ${[...due, ...upcoming].slice(0, 6).map((item) => `
          <article class="daily-card-item">
            <strong>${escapeHtml(item.event?.title || "Design event")}</strong>
            <span>${escapeHtml(item.design_title || item.design?.title || "Experiment design")} · ${escapeHtml(item.day || item.event?.day || "")} · ${escapeHtml(item.calendar_date || item.due_date || "relative day")}</span>
            <small>${escapeHtml(item.condition_name || "all conditions")} · ${escapeHtml(item.event_type || item.event?.event_type || "custom")} · ${escapeHtml(item.reminder_status || "pending")}</small>
            <div class="entry-actions compact-actions">
              <a class="secondary-link-button" href="#/design-planner">Open</a>
              <button type="button" class="secondary-button" data-design-reminder-complete="${escapeHtml(item.event_id || item.event?.event_id || "")}">Complete</button>
              <button type="button" class="secondary-button" data-design-reminder-dismiss="${escapeHtml(item.event_id || item.event?.event_id || "")}">Dismiss</button>
            </div>
          </article>
        `).join("") || `<div class="empty-state">No planned design reminders due soon.</div>`}
      </div>
    </details>
  `;
}

function renderMorningBrief() {
  const summary = $("#morningBriefSummary");
  const target = $("#morningBriefCards");
  if (!summary || !target) return;
  const brief = state.dailyDashboard?.morning_brief;
  if (!brief) {
    summary.textContent = "Morning Brief is loading local ResearchOS state.";
    target.innerHTML = `<div class="empty-state">Morning Brief unavailable.</div>`;
    return;
  }
  summary.textContent = brief.summary || "No observed ResearchOS changes were detected.";
  const sections = brief.sections || {};
  const sectionLabels = {
    new_experiments: "New experiments",
    updated_experiments: "Updated experiments",
    completed_workflows: "Completed workflows",
    missing_analyses: "Missing analyses",
    new_literature: "New literature",
    knowledge_graph_changes: "Knowledge Graph changes",
    protocol_updates: "Protocol updates",
    resource_alerts: "Resource alerts",
    research_copilot_insights: "Research Copilot insights",
    suggested_priorities: "Suggested priorities",
  };
  const cards = Object.entries(sectionLabels)
    .map(([key, label]) => renderMorningBriefSection(label, sections[key] || []))
    .join("");
  target.innerHTML = cards || `<div class="empty-state">No Morning Brief sections available.</div>`;
}

function renderMorningBriefSection(label, items) {
  return `
    <details class="daily-card morning-brief-card" ${items.length ? "open" : ""}>
      <summary>
        <span>${escapeHtml(label)}</span>
        <small>${items.length}</small>
      </summary>
      <div class="daily-card-items">
        ${items.length ? items.slice(0, 5).map(renderMorningBriefItem).join("") : `<div class="empty-state">No observed updates.</div>`}
      </div>
    </details>
  `;
}

function renderMorningBriefItem(item) {
  const href = feedItemHref(item);
  const provenance = (item.provenance || [])
    .map((prov) => [prov.fact, prov.source, prov.provider, prov.experiment_id, prov.asset_id, prov.document_id, prov.resource_id, prov.workflow_id].filter(Boolean).join(" / "))
    .filter(Boolean)
    .join(" | ") || "ResearchOS provenance";
  const content = `
    <strong>${escapeHtml(item.title || "Morning Brief item")}</strong>
    <span>${escapeHtml(item.summary || "")}</span>
    <small><b>${escapeHtml(item.priority || "low")}</b> · ${escapeHtml(item.suggested_action || "Review source records.")}</small>
    <small>${escapeHtml(provenance)}</small>
  `;
  return href
    ? `<a class="daily-card-item" href="${escapeHtml(href)}">${content}</a>`
    : `<article class="daily-card-item">${content}</article>`;
}

function renderIntelligenceFeedItem(item) {
  const href = feedItemHref(item);
  const provenance = (item.provenance || [])
    .map((prov) => [prov.fact, prov.source, prov.provider, prov.experiment_id, prov.asset_id, prov.document_id, prov.resource_id, prov.session_id].filter(Boolean).join(" / "))
    .filter(Boolean)
    .join(" | ") || "ResearchOS provenance";
  const content = `
    <div class="intelligence-feed-header">
      <span class="status-pill ${priorityClass(item.priority)}">${escapeHtml(item.priority || "low")}</span>
      <span>${escapeHtml(item.item_type || "Laboratory Intelligence")}</span>
      ${item.pinned ? `<span class="status-pill ok">Pinned</span>` : ""}
    </div>
    <strong>${escapeHtml(item.title || "Feed item")}</strong>
    <span>${escapeHtml(item.summary || "")}</span>
    <small><b>Suggested action:</b> ${escapeHtml(item.suggested_action || "Review source records.")}</small>
    <small>${escapeHtml(provenance)}</small>
  `;
  return `
    <article class="daily-card-item intelligence-item" data-intelligence-item="${escapeHtml(item.item_id)}">
      ${href ? `<a href="${escapeHtml(href)}">${content}</a>` : content}
      <div class="intelligence-actions">
        <button class="secondary-button" type="button" data-intelligence-pin="${escapeHtml(item.item_id)}">${item.pinned ? "Unpin" : "Pin"}</button>
        <button class="secondary-button" type="button" data-intelligence-dismiss="${escapeHtml(item.item_id)}">Dismiss</button>
      </div>
    </article>
  `;
}

function feedItemHref(item) {
  const route = String(item.route || "");
  if (route.startsWith("#/")) return route;
  const mobileExperiment = route.match(/^\/mobile\/experiments\/([^/]+)\/workspace$/);
  if (mobileExperiment) return `#/experiments/${mobileExperiment[1]}/workspace`;
  return "";
}

function priorityClass(priority) {
  if (priority === "critical" || priority === "high") return "warning";
  if (priority === "medium") return "pending";
  return "ok";
}

function bindIntelligenceFeedControls() {
  $$("[data-intelligence-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.dataset.intelligenceFilter || null;
      state.intelligenceFilter = value || null;
      renderDailyDashboard();
    });
  });
  $$("[data-intelligence-dismiss]").forEach((button) => {
    button.addEventListener("click", async () => {
      await requestJson(`/intelligence/feed/${encodeURIComponent(button.dataset.intelligenceDismiss)}/dismiss`, { method: "POST" });
      await refreshData();
    });
  });
  $$("[data-intelligence-pin]").forEach((button) => {
    button.addEventListener("click", async () => {
      const item = (state.dailyDashboard?.laboratory_intelligence_feed?.items || []).find((candidate) => candidate.item_id === button.dataset.intelligencePin);
      await requestJson(`/intelligence/feed/${encodeURIComponent(button.dataset.intelligencePin)}/pin`, {
        method: "POST",
        body: JSON.stringify({ pinned: !item?.pinned }),
      });
      await refreshData();
    });
  });
}

function renderDailyDashboardCard(section) {
  return `
    <details class="daily-card" open draggable="true" data-dashboard-card="${escapeHtml(section.id)}">
      <summary>
        <span>${escapeHtml(section.title)}</span>
        <small>drag to reorder</small>
      </summary>
      <div class="daily-card-items">
        ${(section.items || []).map(renderDailyDashboardItem).join("") || `<div class="empty-state">No items in this section.</div>`}
      </div>
    </details>
  `;
}

function renderDailyDashboardItem(item) {
  const content = `
    <strong>${escapeHtml(item.title || "Dashboard item")}</strong>
    <span>${escapeHtml(item.summary || "")}</span>
    <small>${escapeHtml(item.category || "observed")} · ${escapeHtml((item.provenance || []).map((prov) => [prov.fact, prov.source, prov.provider, prov.id, prov.experiment_id, prov.asset_id, prov.document_id].filter(Boolean).join(" / ")).join(" | ") || "ResearchOS provenance")}</small>
  `;
  return item.href
    ? `<a class="daily-card-item" href="${escapeHtml(item.href)}">${content}</a>`
    : `<article class="daily-card-item">${content}</article>`;
}

function renderWhiteboard() {
  const board = state.whiteboard;
  const metricsTarget = $("#whiteboardMetrics");
  const sectionsTarget = $("#whiteboardSections");
  const rotationTarget = $("#whiteboardRotation");
  const controlsTarget = $("#whiteboardRotationControls");
  const generatedTarget = $("#whiteboardGenerated");
  if (!metricsTarget || !sectionsTarget || !rotationTarget || !controlsTarget) return;
  if (!board) {
    generatedTarget.textContent = "Whiteboard is loading local ResearchOS state.";
    metricsTarget.innerHTML = "";
    rotationTarget.innerHTML = `<div class="empty-state">Whiteboard unavailable.</div>`;
    sectionsTarget.innerHTML = "";
    return;
  }

  generatedTarget.textContent = `Updated ${formatDisplayTime(board.generated_at)} · auto-refresh every ${board.display?.refresh_seconds || 60}s`;
  const metrics = board.metrics || {};
  metricsTarget.innerHTML = Object.entries(metrics)
    .map(([label, value]) => `
      <article class="whiteboard-metric">
        <span>${escapeHtml(label.replaceAll("_", " "))}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `)
    .join("");

  const rotation = board.rotation || [];
  const activeIndex = Math.min(state.whiteboardRotationIndex, Math.max(rotation.length - 1, 0));
  const activePanel = rotation[activeIndex] || rotation[0] || {};
  controlsTarget.innerHTML = rotation
    .map((panel, index) => `<button type="button" class="secondary-button ${index === activeIndex ? "active" : ""}" data-whiteboard-rotation="${index}">${escapeHtml(panel.title || panel.id)}</button>`)
    .join("");
  rotationTarget.innerHTML = renderWhiteboardRotationPanel(activePanel, board);
  sectionsTarget.innerHTML = (board.sections || []).map(renderWhiteboardSection).join("") || `<div class="empty-state">${escapeHtml(board.empty_state || "No whiteboard data yet.")}</div>`;

  $$("[data-whiteboard-rotation]").forEach((button) => {
    button.addEventListener("click", () => {
      state.whiteboardRotationIndex = Number(button.dataset.whiteboardRotation || 0);
      renderWhiteboard();
    });
  });
}

function renderWhiteboardRotationPanel(panel, board) {
  if (panel.events) {
    return `
      <article class="whiteboard-panel featured">
        <div class="panel-heading"><h2>${escapeHtml(panel.title || "Timeline")}</h2><span class="status-pill ok">Live</span></div>
        <div class="whiteboard-card-grid">${(panel.events || []).map(renderWhiteboardCard).join("") || `<div class="empty-state">No recent timeline events.</div>`}</div>
      </article>
    `;
  }
  if (panel.items) {
    return `
      <article class="whiteboard-panel featured">
        <div class="panel-heading"><h2>${escapeHtml(panel.title || "Morning Brief")}</h2><span class="status-pill ok">Observed</span></div>
        <p>${escapeHtml(panel.summary || "")}</p>
        <div class="whiteboard-card-grid">${(panel.items || []).map(renderWhiteboardCard).join("") || `<div class="empty-state">No morning brief items.</div>`}</div>
      </article>
    `;
  }
  const sections = (panel.sections || [])
    .map((sectionId) => (board.sections || []).find((section) => section.id === sectionId))
    .filter(Boolean);
  return `
    <article class="whiteboard-panel featured">
      <div class="panel-heading"><h2>${escapeHtml(panel.title || "Whiteboard")}</h2><span class="status-pill ok">Rotating</span></div>
      <div class="whiteboard-feature-grid">${sections.map(renderWhiteboardSection).join("")}</div>
    </article>
  `;
}

function renderWhiteboardSection(section) {
  const cards = section.cards || [];
  return `
    <article class="whiteboard-panel">
      <div class="whiteboard-panel-title">
        <h3>${escapeHtml(section.title)}</h3>
        <span>${escapeHtml(section.count || cards.length)}</span>
      </div>
      <div class="whiteboard-card-grid">
        ${cards.length ? cards.map(renderWhiteboardCard).join("") : `<div class="empty-state">${escapeHtml(section.empty_message || "No items.")}</div>`}
      </div>
    </article>
  `;
}

function renderWhiteboardCard(card) {
  const body = `
    <strong>${escapeHtml(card.title || "Whiteboard item")}</strong>
    <span>${escapeHtml(card.subtitle || "")}</span>
    <small class="status-pill ${priorityClass(card.priority)}">${escapeHtml(card.status || card.priority || "observed")}</small>
  `;
  return card.route
    ? `<a class="whiteboard-card priority-${escapeHtml(card.priority || "normal")}" href="${escapeHtml(card.route)}">${body}</a>`
    : `<article class="whiteboard-card priority-${escapeHtml(card.priority || "normal")}">${body}</article>`;
}

function formatDisplayTime(value) {
  if (!value) return "recently";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function bindDailyDashboardReorder() {
  const cards = $$("#dailyDashboardCards [data-dashboard-card]");
  let dragged = null;
  cards.forEach((card) => {
    card.addEventListener("dragstart", () => {
      dragged = card;
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      dragged = null;
    });
    card.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (!dragged || dragged === card) return;
      const parent = card.parentElement;
      const after = event.clientY > card.getBoundingClientRect().top + card.offsetHeight / 2;
      parent.insertBefore(dragged, after ? card.nextSibling : card);
    });
  });
}

function renderCurrentSessionCard() {
  const target = $("#currentSessionCard");
  if (!target) return;
  const session = activeSession();
  if (!session) {
    target.innerHTML = `
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Current session</p>
          <h2>No active experiment session</h2>
        </div>
        <a class="secondary-link-button" href="#/sessions">Start Session</a>
      </div>
      <p class="card-copy">Sessions become the live container for notes, observations, treatments, media changes, files, images, and notebook drafts while an experiment is running.</p>
    `;
    return;
  }
  target.innerHTML = `
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Current session</p>
        <h2>${escapeHtml(session.experiment_id || session.session_id)}</h2>
      </div>
      <a class="secondary-link-button" href="#/sessions">Open Sessions</a>
    </div>
    <div class="detail-grid">
      ${detailField("Started", formatDate(session.start_time))}
      ${detailField("Timer", sessionDuration(session))}
      ${detailField("Timeline events", (session.timeline || []).length)}
      ${detailField("Files/images", (session.assets || []).length)}
    </div>
  `;
}

function renderSessions() {
  renderSessionExperimentOptions();
  renderSessionTimer();
  renderActiveSessionWorkspace();
  const list = $("#sessionsList");
  if (!list) return;
  const sessions = todaysSessions().length ? todaysSessions() : state.sessions;
  list.innerHTML = sessions.length
    ? sessions.map(renderSessionListItem).join("")
    : `<div class="empty-state">No experiment sessions yet.</div>`;
}

function renderSessionExperimentOptions() {
  const select = $("#sessionExperimentSelect");
  if (!select) return;
  const current = select.value;
  select.innerHTML = `
    <option value="">Unlinked session</option>
    ${state.experiments
      .map((experiment) => `<option value="${escapeHtml(experiment.experiment_id || experiment.id)}">${escapeHtml(experiment.experiment_id || experiment.title || experiment.id)}</option>`)
      .join("")}
  `;
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function renderSessionListItem(session) {
  return `
    <article class="record-card">
      <h3>${escapeHtml(session.experiment_id || session.session_id)}</h3>
      <p>${escapeHtml(session.notes || "No session notes.")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(session.status)}</span>
        <span class="tag">${escapeHtml(formatDate(session.start_time))}</span>
        <span class="tag">${escapeHtml((session.timeline || []).length)} events</span>
      </div>
    </article>
  `;
}

function renderActiveSessionWorkspace() {
  const target = $("#activeSessionWorkspace");
  if (!target) return;
  const session = activeSession();
  if (!session) {
    target.innerHTML = `
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Workspace</p>
          <h2>No active session</h2>
        </div>
      </div>
      <div class="empty-state">Start a session to capture notes, observations, treatments, media changes, files, and images.</div>
    `;
    return;
  }
  const timeline = session.timeline || [];
  const noteEvents = timeline.filter((event) => ["voice_note", "manual_note", "observation", "treatment", "media_change", "notebook_draft_updated"].includes(event.event_type));
  const fileEvents = timeline.filter((event) => ["file_imported", "graphpad_imported", "spreadsheet_imported"].includes(event.event_type));
  const imageEvents = timeline.filter((event) => event.event_type === "image_imported");
  target.innerHTML = `
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Active Session</p>
        <h2>${escapeHtml(session.experiment_id || session.session_id)}</h2>
      </div>
      <span class="status-pill ok">${escapeHtml(sessionDuration(session))}</span>
    </div>
    <form class="entry-draft-form" id="sessionEventForm">
      <label for="sessionEventType">Append to session</label>
      <select id="sessionEventType">
        <option value="manual_note">Manual note</option>
        <option value="voice_note">Voice note transcript</option>
        <option value="observation">Observation</option>
        <option value="treatment">Treatment</option>
        <option value="media_change">Media change</option>
        <option value="image_imported">Image imported</option>
        <option value="file_imported">File imported</option>
        <option value="graphpad_imported">GraphPad imported</option>
        <option value="spreadsheet_imported">Spreadsheet imported</option>
        <option value="notebook_draft_updated">Notebook draft updated</option>
      </select>
      <label for="sessionEventTitle">Title</label>
      <input id="sessionEventTitle" type="text" placeholder="D32 SIX6/BRN3B image captured" />
      <label for="sessionEventContent">Details</label>
      <textarea id="sessionEventContent" rows="3" placeholder="Observation, treatment, media change, transcript, or file note..."></textarea>
      <label for="sessionEventAsset">Asset ID (optional)</label>
      <input id="sessionEventAsset" type="text" placeholder="asset:..." />
      <div class="entry-actions">
        <button type="submit">Append Event</button>
      </div>
    </form>
    <div class="detail-grid">
      ${detailField("Status", session.status)}
      ${detailField("Started", formatDate(session.start_time))}
      ${detailField("Voice transcripts", (session.voice_transcripts || []).length)}
      ${detailField("Timeline events", timeline.length)}
    </div>
    ${workspaceSection("Timeline", timeline, renderSessionTimelineEvent)}
    ${workspaceSection("Recent Notes", noteEvents.slice(-8).reverse(), renderSessionTimelineEvent)}
    ${workspaceSection("Files", fileEvents.slice(-8).reverse(), renderSessionTimelineEvent)}
    ${workspaceSection("Images", imageEvents.slice(-8).reverse(), renderSessionTimelineEvent)}
  `;
  $("#sessionEventForm").addEventListener("submit", (event) => {
    event.preventDefault();
    appendSessionEvent(session.session_id).catch((error) => {
      $("#sessionStatus").textContent = `Could not append event: ${error.message}`;
    });
  });
}

function renderSessionTimelineEvent(event) {
  return `
    <article class="timeline-item">
      <div class="timeline-item-header">${timelineBadge(event.event_type)}<strong>${escapeHtml(event.title)}</strong></div>
      <span>${escapeHtml(formatDate(event.created_at))}${event.asset_id ? ` · ${escapeHtml(event.asset_id)}` : ""}</span>
      <p>${escapeHtml(event.content || "")}</p>
    </article>
  `;
}

function sessionDuration(session) {
  if (!session?.start_time) return "No timer";
  const start = new Date(String(session.start_time).replace(" ", "T"));
  const end = session.end_time ? new Date(String(session.end_time).replace(" ", "T")) : new Date();
  const seconds = Math.max(0, Math.floor((end.getTime() - start.getTime()) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${String(minutes).padStart(2, "0")}m`;
}

function renderSessionTimer() {
  const timer = $("#sessionTimer");
  if (!timer) return;
  const session = activeSession();
  timer.textContent = session ? `Active: ${sessionDuration(session)}` : "No active session";
  timer.className = `status-pill ${session ? "ok" : ""}`;
}

async function startExperimentSession() {
  const experimentId = $("#sessionExperimentSelect").value || null;
  const notes = $("#sessionStartNotes").value.trim() || null;
  $("#sessionStatus").textContent = "Starting session...";
  await requestJson("/sessions/start", {
    method: "POST",
    body: JSON.stringify({ experiment_id: experimentId, notes }),
  });
  $("#sessionStartNotes").value = "";
  await refreshData();
  $("#sessionStatus").textContent = "Session started.";
  recordActivity("Session started", experimentId || "Unlinked session");
}

async function endActiveSession() {
  const session = activeSession();
  if (!session) {
    $("#sessionStatus").textContent = "No active session to end.";
    return;
  }
  await requestJson(`/sessions/${encodeURIComponent(session.session_id)}/end`, {
    method: "POST",
    body: JSON.stringify({ notes: "Session ended from ResearchOS UI." }),
  });
  await refreshData();
  $("#sessionStatus").textContent = "Session ended.";
  recordActivity("Session ended", session.experiment_id || session.session_id);
}

async function appendSessionEvent(sessionId) {
  const title = $("#sessionEventTitle").value.trim();
  if (!title) {
    $("#sessionStatus").textContent = "Add a title before appending a session event.";
    return;
  }
  await requestJson(`/sessions/${encodeURIComponent(sessionId)}/events`, {
    method: "POST",
    body: JSON.stringify({
      event_type: $("#sessionEventType").value,
      title,
      content: $("#sessionEventContent").value.trim() || null,
      asset_id: $("#sessionEventAsset").value.trim() || null,
    }),
  });
  await refreshData();
  $("#sessionStatus").textContent = "Session event appended.";
  recordActivity("Session event", title);
}

function renderTimeline() {
  const oneNote = oneNoteDisplayStatus();
  const systemItems = [
    {
      title: `OneNote status: ${oneNote.label}`,
      meta: oneNote.message,
    },
    state.lastSync
      ? {
          title: "Workspace data refreshed",
          meta: state.lastSync.toLocaleTimeString(),
        }
      : null,
  ].filter(Boolean);

  const items = [
    ...state.activity.map((item) => ({
      title: item.title,
      meta: `${item.meta} · ${item.timestamp.toLocaleTimeString()}`,
    })),
    ...systemItems,
    ...state.experiments.slice(0, 3).map((experiment) => ({
      title: `Extracted ${experiment.title}`,
      meta: `${formatDate(experiment.date)} · ${experiment.source_provider}`,
    })),
    ...state.documents.slice(0, 3).map((document) => ({
      title: `Indexed ${document.title}`,
      meta: `${formatDate(document.updated_at)} · ${document.provider}`,
    })),
  ].slice(0, 5);

  $("#activityTimeline").innerHTML = items.length
    ? items.map((item) => `<div class="timeline-item"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.meta)}</span></div>`).join("")
    : `<div class="empty-state">No recent activity. Load demo notes to begin.</div>`;
}

function renderRecentExperimentTimeline() {
  const target = $("#recentExperimentTimeline");
  if (!target) return;
  const events = [
    ...state.assets.map((asset) => ({
      timestamp: asset.updated_at || asset.created_at,
      title: asset.metadata?.statistics ? `Statistics linked: ${asset.title}` : `Asset linked: ${asset.title}`,
      meta: `${asset.asset_type} · ${asset.provider}${asset.experiment_id ? ` · ${asset.experiment_id}` : ""}`,
      href: `#/assets/${encodeURIComponent(asset.asset_id)}`,
    })),
    ...state.experiments.map((experiment) => ({
      timestamp: experiment.date || experiment.extracted_at,
      title: `Experiment extracted: ${experiment.experiment_id || experiment.title}`,
      meta: `${formatDate(experiment.date)} · ${experiment.source_provider}`,
      href: `#/experiments/${encodeURIComponent(experiment.id)}`,
    })),
    ...state.documents.slice(0, 6).map((document) => ({
      timestamp: document.updated_at || document.created_at || document.ingested_at,
      title: `Document indexed: ${document.title}`,
      meta: `${formatDate(document.updated_at || document.ingested_at)} · ${document.provider}`,
      href: "#/documents",
    })),
  ]
    .filter((event) => event.timestamp)
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)))
    .slice(0, 6);

  target.innerHTML = events.length
    ? events.map((event) => `
      <a class="timeline-item" href="${event.href}">
        <strong>${escapeHtml(event.title)}</strong>
        <span>${escapeHtml(formatDate(event.timestamp))} · ${escapeHtml(event.meta)}</span>
      </a>
    `).join("")
    : `<div class="empty-state">No experiment timeline events yet.</div>`;
}

function timelineBadge(eventType) {
  const type = String(eventType || "event");
  const label = {
    notebook_entry: "Notebook",
    extracted_experiment: "Experiment",
    graphpad_analysis: "GraphPad",
    statistics_result: "Statistics",
    image_asset: "Image",
    literature_reference: "Literature",
    pending_entry: "Draft",
    pdf_asset: "PDF",
  }[type] || type.replaceAll("_", " ");
  return `<span class="event-badge event-${escapeHtml(type)}">${escapeHtml(label)}</span>`;
}

function renderRecentExperiments() {
  $("#recentExperiments").innerHTML = state.experiments.length
    ? state.experiments
        .slice(0, 4)
        .map(
          (experiment) => `
            <a class="item-link" href="#/experiments/${encodeURIComponent(experiment.id)}">
              <strong>${escapeHtml(experiment.title)}</strong>
              <span>${escapeHtml(formatDate(experiment.date))}</span>
            </a>
          `,
        )
        .join("")
    : `<div class="empty-state">No experiments available.</div>`;
}

function renderPopularCompounds() {
  const compounds = (state.ontology.compounds || []).map((entity) => [
    entity.name,
    entity.experiments.length + entity.protocols.length,
  ]);
  $("#popularCompounds").innerHTML = compounds.length
    ? compounds
        .map(
          ([name, count]) =>
            `<a class="compound-chip" href="${graphEntityLink("compounds", name)}">${escapeHtml(name)} <small>${count}</small></a>`,
        )
        .join("")
    : `<div class="empty-state">No compounds detected.</div>`;
}

function renderOneNoteStatusCard() {
  const oneNote = oneNoteDisplayStatus();
  $("#oneNoteStatusCard").innerHTML = `
    <div class="panel-heading">
      <div>
        <p class="eyebrow">OneNote</p>
        <h2>Status</h2>
      </div>
      <span class="status-pill ${oneNote.status === "ok" ? "ok" : ""}">${escapeHtml(oneNote.label)}</span>
    </div>
    <p class="card-copy">${escapeHtml(oneNote.message)}</p>
  `;
}

function renderLiteratureStatusCard() {
  const paper = newestPaper();
  $("#literatureStatusCard").innerHTML = `
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Literature</p>
        <h2>${state.papers.length} paper${state.papers.length === 1 ? "" : "s"}</h2>
      </div>
      <span class="status-pill ${state.papers.length ? "ok" : ""}">${state.papers.length ? "Literature ready" : "Not imported"}</span>
    </div>
    <div class="detail-grid compact-detail-grid">
      ${detailField("Papers", state.papers.length)}
      ${detailField("Newest paper", paper?.title || "No papers have been imported.")}
    </div>
  `;
}

function assetTypeCounts() {
  return state.assets.reduce((counts, asset) => {
    const type = asset.asset_type || "other";
    counts[type] = (counts[type] || 0) + 1;
    return counts;
  }, {});
}

function renderAssetStatusCard() {
  const counts = assetTypeCounts();
  const grouped = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const graphpadCount = graphPadAssets().length;
  $("#assetStatusCard").innerHTML = `
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Research Assets</p>
        <h2>${state.assets.length} total</h2>
      </div>
      <a class="status-pill ${state.assets.length ? "ok" : ""}" href="#/assets">Open assets</a>
    </div>
    <p class="card-copy">${graphpadCount} GraphPad provider asset${graphpadCount === 1 ? "" : "s"} registered.</p>
    <div class="tag-row">
      ${grouped.length
        ? grouped.map(([type, count]) => `<span class="tag">${escapeHtml(type)}: ${count}</span>`).join("")
        : `<span class="muted">No assets registered yet.</span>`}
    </div>
  `;
}

function renderDocuments() {
  $("#documentsList").innerHTML = state.documents.length
    ? state.documents
        .map(
          (document) => `
            <article class="record-card">
              <h3>${escapeHtml(document.title)}</h3>
              <p>${escapeHtml(document.source_path || document.source_id)}</p>
              <div class="meta">
                <span class="tag">${escapeHtml(document.provider)}</span>
                <span class="tag">${escapeHtml(formatDate(document.updated_at))}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No documents have been indexed.</div>`;
}

function renderAssets() {
  const type = $("#assetTypeFilter")?.value || "";
  const query = ($("#assetSearchInput")?.value || "").trim().toLowerCase();
  const assets = state.assets.filter((asset) => {
    const matchesType = !type || asset.asset_type === type;
    const haystack = [
      asset.title,
      asset.filename,
      asset.provider,
      asset.path,
      asset.experiment_id,
    ].join(" ").toLowerCase();
    return matchesType && (!query || haystack.includes(query));
  });

  $("#assetsList").innerHTML = assets.length
    ? assets
        .map((asset) => {
          const experiment = asset.linked_experiment;
          return `
            <article class="record-card asset-card">
              <div>
                <h3><a href="#/assets/${encodeURIComponent(asset.asset_id)}">${escapeHtml(asset.title)}</a></h3>
                <p>${escapeHtml(asset.filename)} · ${escapeHtml(asset.provider)} · ${escapeHtml(asset.path)}</p>
                <div class="meta">
                  <span class="tag">${escapeHtml(asset.asset_type)}</span>
                  <span class="tag">${escapeHtml(asset.link_status || "unlinked")}</span>
                  ${asset.metadata?.statistics ? `<a class="mini-chip" href="#/statistics">parsed statistics</a>` : ""}
                  <span class="tag">updated ${escapeHtml(formatDate(asset.updated_at))}</span>
                  ${experiment ? `<a class="mini-chip" href="#/experiments/${encodeURIComponent(experiment.id)}">${escapeHtml(experiment.experiment_id || experiment.title)}</a>` : asset.experiment_id ? `<span class="tag">ref ${escapeHtml(asset.experiment_id)}</span>` : ""}
                </div>
              </div>
            </article>
          `;
        })
        .join("")
    : `<div class="empty-state">No assets match this filter.</div>`;
}

function renderImages() {
  const target = $("#imagesList");
  if (!target) return;
  const images = microscopyImageAssets();
  const markerFilter = $("#imageMarkerFilter");
  const selectedMarker = markerFilter?.value || "";
  if (markerFilter) {
    const markers = [...new Set(images.flatMap((asset) => asset.metadata?.markers || []))].sort();
    const previous = markerFilter.value;
    markerFilter.innerHTML = `<option value="">All markers</option>${markers
      .map((marker) => `<option value="${escapeHtml(marker)}">${escapeHtml(marker)}</option>`)
      .join("")}`;
    markerFilter.value = markers.includes(previous) ? previous : selectedMarker;
  }
  const filteredImages = selectedMarker
    ? images.filter((asset) => (asset.metadata?.markers || []).some((marker) => marker.toLowerCase() === selectedMarker.toLowerCase()))
    : images;
  target.innerHTML = images.length
    ? filteredImages.length
      ? filteredImages.map(renderImageAssetCard).join("")
      : `<div class="empty-state">No images match this marker filter.</div>`
    : `<div class="empty-state">No microscopy/image assets registered yet. Scan image folders to import sample image metadata.</div>`;
}

function renderSpreadsheets() {
  const target = $("#spreadsheetsList");
  if (!target) return;
  target.innerHTML = state.spreadsheets.length
    ? state.spreadsheets.map((asset) => {
      const metadata = asset.metadata || {};
      const entities = metadata.entities || {};
      const entityCount = Object.values(entities).flat().length;
      return `
        <article class="record-card">
          <h3><a href="#/assets/${encodeURIComponent(asset.asset_id)}">${escapeHtml(asset.title || asset.filename)}</a></h3>
          <p>${escapeHtml(asset.filename)} · ${escapeHtml(asset.experiment_id || "No experiment link")} · ${escapeHtml(asset.path)}</p>
          <div class="meta">
            <span class="tag">${escapeHtml((metadata.sheet_names || []).join(", ") || "No sheets")}</span>
            <span class="tag">${escapeHtml(metadata.row_count ?? 0)} rows</span>
            <span class="tag">${escapeHtml(metadata.column_count ?? 0)} columns</span>
            <span class="tag">${escapeHtml(entityCount)} entities</span>
            ${asset.linked_experiment ? `<a class="mini-chip" href="#/experiments/${encodeURIComponent(asset.linked_experiment.id)}">${escapeHtml(asset.linked_experiment.experiment_id || asset.linked_experiment.title)}</a>` : ""}
            <a class="mini-chip" href="/spreadsheets/${encodeURIComponent(asset.asset_id)}/download">Download file</a>
          </div>
          ${spreadsheetEntitySummary(entities)}
          ${compactSummaryFromMetadata(asset)}
          <p class="card-copy">Compact summary API: /spreadsheets/${escapeHtml(asset.asset_id)}/compact-summary</p>
        </article>
      `;
    }).join("")
    : `<div class="empty-state">No spreadsheets imported. Scan spreadsheet folders to register quantitative data files.</div>`;
}

function compactSummaryFromMetadata(asset) {
  const metadata = asset.metadata || {};
  const table = (metadata.detected_tables || [])[0] || {};
  const groups = Object.keys(table.grouped_summaries || {}).flatMap((groupColumn) => Object.keys(table.grouped_summaries[groupColumn] || {}));
  const numeric = Object.entries(table.numeric_summaries || {}).slice(0, 4);
  if (!groups.length && !numeric.length) return "";
  return `
    <section class="compact-summary-card">
      <h4>Compact summary</h4>
      <p>${escapeHtml(asset.title)} has ${escapeHtml(metadata.row_count ?? 0)} row(s), ${escapeHtml(metadata.column_count ?? 0)} column(s), and ${escapeHtml(numeric.length)} key numeric measurement(s).</p>
      <div class="meta">
        ${groups.slice(0, 8).map((group) => `<span class="tag">${escapeHtml(group)}</span>`).join("")}
        ${numeric.map(([name, values]) => `<span class="tag">${escapeHtml(name)} mean ${escapeHtml(roundNumber(values.mean))}</span>`).join("")}
      </div>
    </section>
  `;
}

function spreadsheetEntitySummary(entities) {
  const chips = Object.entries(entities || {})
    .flatMap(([category, values]) => (values || []).slice(0, 6).map((value) => `<span class="tag">${escapeHtml(category)}: ${escapeHtml(value)}</span>`))
    .slice(0, 18);
  return chips.length ? `<div class="meta">${chips.join("")}</div>` : "";
}

function roundNumber(value) {
  return typeof value === "number" ? Math.round(value * 1000) / 1000 : value ?? "n/a";
}

function renderImageAssetCard(asset) {
  return `
    <article class="record-card">
      <h3><a href="#/assets/${encodeURIComponent(asset.asset_id)}">${escapeHtml(asset.title || asset.filename || "Image")}</a></h3>
      <p>${escapeHtml(asset.filename)} · ${escapeHtml(asset.experiment_id || "No experiment reference")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(asset.provider || "microscopy")}</span>
        <span class="tag">${escapeHtml(asset.asset_type || "image")}</span>
        <span class="tag">${escapeHtml(asset.metadata?.timepoint || asset.timepoint || "No timepoint")}</span>
        ${(asset.metadata?.markers || asset.markers || []).map((marker) => `<a class="mini-chip" href="#/markers/${encodeURIComponent(marker)}">${escapeHtml(marker)}</a>`).join("")}
      </div>
    </article>
  `;
}

function renderAssetDetail(assetId) {
  const asset = state.assets.find((item) => item.asset_id === assetId);
  if (!asset) {
    $("#assetDetail").innerHTML = `<div class="empty-state">Asset not found.</div>`;
    return;
  }
  const experiment = asset.linked_experiment;
  const metadata = Object.entries(asset.metadata || {});
  const statistics = asset.metadata?.statistics;
  $("#assetDetail").innerHTML = `
    <a class="inline-link" href="#/assets">Back to assets</a>
    <div class="detail-header">
      <div>
        <p class="eyebrow">${escapeHtml(asset.asset_type)}</p>
        <h2>${escapeHtml(asset.title)}</h2>
      </div>
      <span class="status-pill ${asset.link_status === "resolved" ? "ok" : ""}">${escapeHtml(asset.link_status || "unlinked")}</span>
    </div>
    <div class="detail-grid">
      ${detailField("Asset ID", asset.asset_id)}
      ${detailField("Filename", asset.filename)}
      ${detailField("Provider", asset.provider)}
      ${detailField("Path", asset.path)}
      ${detailField("Experiment reference", asset.experiment_id)}
      ${detailField("Link status", asset.link_status)}
      ${detailField("Created", formatDate(asset.created_at))}
      ${detailField("Updated", formatDate(asset.updated_at))}
    </div>
    <section class="detail-section">
      <h3>Link asset to experiment</h3>
      <form class="asset-link-form" id="assetLinkForm">
        <label class="sr-only" for="assetExperimentInput">Experiment ID</label>
        <input id="assetExperimentInput" list="assetExperimentOptions" type="text" placeholder="experiment:... or NK_Expt_31" value="${escapeHtml(asset.experiment_id || "")}" />
        <datalist id="assetExperimentOptions">
          ${state.experiments
            .map((item) => `
              <option value="${escapeHtml(item.id)}">${escapeHtml(item.experiment_id || item.title)}</option>
              ${item.experiment_id ? `<option value="${escapeHtml(item.experiment_id)}">${escapeHtml(item.title)}</option>` : ""}
            `)
            .join("")}
        </datalist>
        <button type="submit">Link asset</button>
        <button type="button" class="secondary-button" id="unlinkAssetButton">Unlink</button>
      </form>
      <p class="demo-status" id="assetLinkStatus">${asset.link_status === "unresolved" ? "This reference is saved but does not match an extracted experiment yet." : ""}</p>
    </section>
    <section class="detail-section">
      <h3>Linked experiment</h3>
      <div class="item-list">
        ${experiment
          ? `<a class="item-link" href="#/experiments/${encodeURIComponent(experiment.id)}"><strong>${escapeHtml(experiment.experiment_id || experiment.title)}</strong><span>${escapeHtml(formatDate(experiment.date))} · ${escapeHtml(experiment.source_provider)}</span></a>`
          : asset.experiment_id
          ? `<div class="empty-state">Unresolved reference: ${escapeHtml(asset.experiment_id)}. It will resolve automatically when a matching experiment is ingested.</div>`
          : `<div class="empty-state">This asset is not linked to an experiment yet.</div>`}
      </div>
    </section>
    ${asset.provider === "spreadsheet" || statistics ? `<section class="detail-section" id="assetCompactSummary"><div class="empty-state">Loading compact quantitative summary...</div></section>` : ""}
    ${statistics ? statisticsSummarySection(statistics, asset.asset_id) : ""}
    <details class="detail-section">
      <summary>Raw metadata</summary>
      <div class="detail-grid raw-metadata-grid">
        ${metadata.length
          ? metadata.map(([key, value]) => detailField(key, formatComparisonValue(value))).join("")
          : `<div class="empty-state">No metadata registered.</div>`}
      </div>
    </details>
  `;

  $("#assetLinkForm").addEventListener("submit", (event) => {
    event.preventDefault();
    linkAssetToExperiment(asset.asset_id, $("#assetExperimentInput").value.trim()).catch((error) => {
      $("#assetLinkStatus").textContent = `Link failed: ${error.message}`;
    });
  });
  $("#unlinkAssetButton").addEventListener("click", () => {
    linkAssetToExperiment(asset.asset_id, null).catch((error) => {
      $("#assetLinkStatus").textContent = `Unlink failed: ${error.message}`;
    });
  });
  loadAssetCompactSummary(asset).catch(() => {
    const target = $("#assetCompactSummary");
    if (target) target.innerHTML = `<div class="empty-state">Compact summary unavailable.</div>`;
  });
}

async function loadAssetCompactSummary(asset) {
  const target = $("#assetCompactSummary");
  if (!target) return;
  let path = "";
  if (asset.provider === "spreadsheet") {
    path = `/spreadsheets/${encodeURIComponent(asset.asset_id)}/compact-summary`;
  } else if (asset.metadata?.statistics) {
    path = `/statistics/${encodeURIComponent(asset.asset_id)}/compact-summary`;
  }
  if (!path) return;
  const summary = await requestJson(path);
  state.compactSummaries[asset.asset_id] = summary;
  target.innerHTML = compactSummarySection(summary);
}

function compactSummarySection(summary) {
  const statisticalResults = summary.statistical_results || [];
  return `
    <h3>Compact quantitative summary</h3>
    <p>${escapeHtml(summary.short_interpretation)}</p>
    <div class="meta">
      ${(summary.detected_markers_entities || []).slice(0, 12).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
      ${(summary.detected_treatments_groups || []).slice(0, 12).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
      ${(summary.p_values || []).slice(0, 6).map((value) => `<span class="tag">p=${escapeHtml(value)}</span>`).join("")}
      ${statisticalResults.slice(0, 6).map((result) => `<span class="tag">${escapeHtml(result.significance || "unavailable")}</span>`).join("")}
    </div>
    ${statisticalResults.length ? `
      <div class="source-list">
        ${statisticalResults.slice(0, 6).map((result) => `
          <article class="result">
            <h3>${escapeHtml(result.variable || "Statistical result")}</h3>
            <p>${escapeHtml(result.interpretation || result.notes || "")}</p>
            <div class="meta">
              <span class="tag">${escapeHtml(result.test_used || "test unavailable")}</span>
              <span class="tag">${escapeHtml(result.significance || "unavailable")}</span>
            </div>
          </article>
        `).join("")}
      </div>
    ` : ""}
    <div class="detail-grid">
      ${detailField("Experiment ID", summary.experiment_id)}
      ${detailField("Source", summary.source)}
      ${detailField("Key measurements", (summary.key_numeric_measurements || []).map((item) => `${item.measurement}: mean ${roundNumber(item.mean)}`).join("; "))}
      ${detailField("Limitations", (summary.limitations || []).join(" "))}
    </div>
  `;
}

function statisticsSummarySection(statistics, assetId = "") {
  return `
    <section class="detail-section">
      <h3>Parsed statistics</h3>
      <div class="detail-grid">
        ${detailField("Groups", (statistics.group_names || []).join(", "))}
        ${detailField("Variables", (statistics.variables || []).join(", "))}
        ${detailField("Tests", (statistics.statistical_tests || []).join(", "))}
        ${detailField("Comparisons", (statistics.comparison_labels || []).join(", "))}
      </div>
      <div class="table-wrap">
        <table class="comparison-table">
          <thead>
            <tr>
              <th>Group</th>
              <th>Variable</th>
              <th>n</th>
              <th>Mean</th>
              <th>SEM</th>
              <th>p-value</th>
              <th>Test</th>
            </tr>
          </thead>
          <tbody>
            ${(statistics.rows || []).length
              ? statistics.rows.map((row) => `
                <tr>
                  <td>${escapeHtml(row.group || "")}</td>
                  <td>${escapeHtml(row.variable || "")}</td>
                  <td>${escapeHtml(row.n ?? "")}</td>
                  <td>${escapeHtml(row.mean ?? "")}</td>
                  <td>${escapeHtml(row.sem ?? "")}</td>
                  <td>${escapeHtml(row.p_value ?? "")}</td>
                  <td>${escapeHtml(row.test || "")}</td>
                </tr>
              `).join("")
              : `<tr><td colspan="7">No parsed rows available.</td></tr>`}
          </tbody>
        </table>
      </div>
      ${assetId ? `<p class="card-copy">API summary: /providers/graphpad/assets/${escapeHtml(assetId)}/summary</p>` : ""}
    </section>
  `;
}

async function linkAssetToExperiment(assetId, experimentReference) {
  const target = $("#assetLinkStatus");
  if (target) {
    target.textContent = experimentReference ? "Linking asset..." : "Removing experiment link...";
  }
  const payload = await requestJson("/assets/link", {
    method: "POST",
    body: JSON.stringify({
      asset_id: assetId,
      experiment_id: experimentReference || null,
    }),
  });
  await refreshData();
  renderAssetDetail(assetId);
  const refreshedTarget = $("#assetLinkStatus");
  if (refreshedTarget) {
    refreshedTarget.textContent = payload.link_status === "unresolved"
      ? `Saved unresolved reference: ${payload.experiment_id}. It will resolve after a matching experiment is ingested.`
      : payload.link_status === "resolved"
      ? "Asset linked to an extracted experiment."
      : "Asset unlinked.";
  }
  recordActivity("Asset link updated", `${payload.title} · ${payload.link_status}`);
}

async function scanGraphPadAssets() {
  const target = $("#graphPadScanStatus");
  if (target) {
    target.textContent = "Scanning configured GraphPad folders...";
  }
  const result = await requestJson("/providers/graphpad/scan", { method: "POST" });
  await refreshData();
  if (target) {
    target.textContent = `GraphPad scan found ${result.files_found} file(s), registered ${result.assets_registered}, skipped ${result.assets_skipped}.`;
  }
  const statisticsTarget = $("#statisticsStatus");
  if (statisticsTarget) {
    statisticsTarget.textContent = `GraphPad scan found ${result.files_found} file(s), registered ${result.assets_registered}, skipped ${result.assets_skipped}.`;
  }
  recordActivity("GraphPad scan", `${result.assets_registered} registered · ${result.assets_skipped} skipped`);
}

async function scanImageAssets() {
  const target = $("#imagesScanStatus");
  if (target) {
    target.textContent = "Scanning configured image folders...";
  }
  const result = await requestJson("/providers/images/scan", { method: "POST" });
  await refreshData();
  if (target) {
    target.textContent = `Image scan found ${result.files_found} file(s), registered ${result.assets_registered}, skipped ${result.assets_skipped}.`;
  }
  recordActivity("Image scan", `${result.assets_registered} registered · ${result.assets_skipped} skipped`);
}

async function scanSpreadsheetAssets() {
  const target = $("#spreadsheetsStatus");
  if (target) {
    target.textContent = "Scanning configured spreadsheet folders...";
  }
  const result = await requestJson("/providers/spreadsheets/scan", { method: "POST" });
  await refreshData();
  if (target) {
    target.textContent = `Spreadsheet scan found ${result.files_found} file(s), registered ${result.assets_registered}, skipped ${result.assets_skipped}.`;
  }
  recordActivity("Spreadsheet scan", `${result.assets_registered} registered · ${result.assets_skipped} skipped`);
}

function renderStatistics() {
  const target = $("#statisticsList");
  if (!target) return;
  const assets = statisticsAssets();
  target.innerHTML = assets.length
    ? assets.map((asset) => {
        const stats = asset.metadata?.statistics || {};
        return `
          <article class="record-card">
            <h3><a href="#/assets/${encodeURIComponent(asset.asset_id)}">${escapeHtml(asset.title)}</a></h3>
            <p>${escapeHtml(asset.filename)} · ${escapeHtml(asset.experiment_id || "No experiment reference")}</p>
            <div class="meta">
              ${(stats.group_names || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
              ${(stats.variables || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
              ${(stats.statistical_tests || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
            </div>
            ${statisticsCompactCard(asset)}
            <p class="card-copy">Compact summary API: /statistics/${escapeHtml(asset.asset_id)}/compact-summary</p>
          </article>
        `;
      }).join("")
    : `<div class="empty-state">No parsed GraphPad CSV statistics yet. Scan the GraphPad folder to import sample statistics.</div>`;
}

function statisticsCompactCard(asset) {
  const stats = asset.metadata?.statistics || {};
  const rows = stats.rows || [];
  const variables = stats.variables || [];
  const groups = stats.group_names || [];
  const pValues = stats.p_values || [];
  const significantCount = pValues.filter((value) => Number(value) < 0.05).length;
  const means = rows
    .filter((row) => row.mean !== undefined && row.mean !== null)
    .slice(0, 6)
    .map((row) => `${row.group || "group"} ${row.variable || "value"} mean ${roundNumber(row.mean)}`);
  return `
    <section class="compact-summary-card">
      <h4>Compact summary</h4>
      <p>${escapeHtml(asset.title)} reports ${escapeHtml(variables.length)} variable(s) across ${escapeHtml(groups.length)} group(s). ${escapeHtml(significantCount)} parsed result(s) are statistically significant at p &lt; 0.05.</p>
      <div class="meta">
        ${means.map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
        ${pValues.slice(0, 6).map((value) => `<span class="tag">p=${escapeHtml(value)}</span>`).join("")}
        <span class="tag">${escapeHtml(significantCount)} significant</span>
      </div>
    </section>
  `;
}

function renderPapers() {
  $("#papersList").innerHTML = state.papers.length
    ? state.papers
        .map(
          (paper) => `
            <article class="record-card">
              <h3><a href="${graphEntityLink("papers", paper.id, paper.title)}">${escapeHtml(paper.title)}</a></h3>
              <p>${escapeHtml(shortText(paper.abstract || paper.source_path || "No abstract detected.", 260))}</p>
              <div class="meta">
                ${paper.year ? `<span class="tag">${escapeHtml(paper.year)}</span>` : ""}
                ${paper.journal ? `<span class="tag">${escapeHtml(paper.journal)}</span>` : ""}
                ${paper.doi ? `<span class="tag">${escapeHtml(paper.doi)}</span>` : ""}
              </div>
              <div class="meta">
                ${(paper.compounds || []).map((value) => graphChip("compounds", value)).join("")}
                ${(paper.markers || []).map((value) => graphChip("markers", value)).join("")}
                ${(paper.genes || []).slice(0, 6).map((value) => graphChip("genes", value)).join("")}
                ${(paper.methods || []).map((value) => `<span class="mini-chip">${escapeHtml(value)}</span>`).join("")}
              </div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No papers have been imported.</div>`;
}

function renderProtocols() {
  const protocols = state.protocols || [];
  $("#protocolsList").innerHTML = protocols.length
    ? protocols
        .map(
          (protocol) => `
            <article class="record-card">
              <h3><a href="#/protocols/${encodeURIComponent(protocol.id)}">${escapeHtml(protocol.title)}</a></h3>
              <p>${escapeHtml(protocol.source_path || protocol.source_document_id || "Protocol detected from local records.")}</p>
              <div class="meta">
                <span class="tag">${escapeHtml(protocol.version)}</span>
                <span class="tag">${escapeHtml(protocol.provider)}</span>
                <span class="tag">${escapeHtml(protocol.linked_experiment_count || 0)} experiments</span>
              </div>
              <p>${escapeHtml(protocol.success_metrics?.method || "Protocol metrics are derived from linked local evidence.")}</p>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No protocols detected.</div>`;
}

function renderInventory() {
  renderInventoryStatusCards();
  const target = $("#inventoryList");
  if (!target) return;
  const query = ($("#inventorySearchInput")?.value || "").trim().toLowerCase();
  const category = ($("#inventoryCategoryFilter")?.value || "").trim().toLowerCase();
  const vendor = ($("#inventoryVendorFilter")?.value || "").trim().toLowerCase();
  const location = ($("#inventoryLocationFilter")?.value || "").trim().toLowerCase();
  const sourceItems = state.inventoryStatus?.items || state.inventory || [];
  const items = sourceItems.filter((item) => {
    const haystack = [item.name, item.category, item.vendor, item.catalog_number, item.lot_number, item.rrid, item.storage_location, item.barcode, item.qr_code, item.internal_label, item.freezer_box, item.freezer_position, item.shelf, item.room].join(" ").toLowerCase();
    return (!query || haystack.includes(query))
      && (!category || String(item.category || "").toLowerCase().includes(category))
      && (!vendor || String(item.vendor || "").toLowerCase().includes(vendor))
      && (!location || String(item.storage_location || "").toLowerCase().includes(location));
  });
  target.innerHTML = items.length
    ? items.map(renderInventoryItem).join("")
    : `<div class="empty-state">No inventory items match this filter.</div>`;
}

function renderInventoryStatusCards() {
  const target = $("#inventoryStatusCards");
  if (!target) return;
  const status = state.inventoryStatus || {};
  const cards = [
    ["Low stock", status.low_stock_count ?? 0, "Items at or below threshold"],
    ["Expiring soon", status.expiring_soon_count ?? 0, "Within 90 days"],
    ["Reorder needed", status.reorder_needed_count ?? 0, "Ready for purchasing review"],
    ["Expired", status.expired_count ?? 0, "Do not use without review"],
  ];
  target.innerHTML = cards.map(([title, value, subtitle]) => `
    <article class="provider-card">
      <div class="provider-card-header">
        <span>${escapeHtml(title)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
      <p>${escapeHtml(subtitle)}</p>
    </article>
  `).join("");
}

function renderInventoryItem(item) {
  const lowStock = item.low_stock ?? (item.quantity != null && item.reorder_threshold != null && Number(item.quantity) <= Number(item.reorder_threshold));
  return `
    <article class="record-card">
      <h3>${escapeHtml(item.name)}</h3>
      <p>${escapeHtml([item.vendor, item.catalog_number, item.lot_number, item.rrid].filter(Boolean).join(" · ") || "No vendor/catalog metadata.")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(item.category || "uncategorized")}</span>
        <span class="tag">${escapeHtml(item.storage_location || "no location")}</span>
        ${item.internal_label ? `<span class="tag">${escapeHtml(item.internal_label)}</span>` : ""}
        ${item.freezer_box || item.freezer_position ? `<span class="tag">${escapeHtml([item.freezer_box, item.freezer_position].filter(Boolean).join(" "))}</span>` : ""}
        ${item.barcode ? `<span class="tag">barcode ${escapeHtml(item.barcode)}</span>` : ""}
        <span class="tag">${escapeHtml(item.quantity ?? "no quantity")} ${escapeHtml(item.unit || "")}</span>
        ${lowStock ? `<span class="tag warning">reorder</span>` : ""}
        ${item.expired ? `<span class="tag warning">expired</span>` : ""}
        ${item.expiring_soon ? `<span class="tag">expiring soon</span>` : ""}
        ${item.expiration_date ? `<span class="tag">expires ${escapeHtml(item.expiration_date)}</span>` : ""}
        ${item.linked_resource_id ? `<a class="mini-chip" href="#/resources">${escapeHtml(item.linked_resource_id)}</a>` : ""}
      </div>
      <button type="button" class="secondary-button methods-citation-button" data-inventory-citation="${escapeHtml(item.item_id)}">Methods citation</button>
      <button type="button" class="secondary-button" data-inventory-copy-citation="${escapeHtml(item.item_id)}">Copy Methods Citation</button>
      <button type="button" class="secondary-button" data-inventory-usage="${escapeHtml(item.item_id)}">Usage History</button>
      <button type="button" class="secondary-button" data-inventory-assign-code="${escapeHtml(item.item_id)}">Assign Barcode/QR</button>
      <button type="button" class="secondary-button" data-inventory-label="${escapeHtml(item.item_id)}">Printable Label</button>
      <button type="button" class="secondary-button" data-inventory-request-reorder="${escapeHtml(item.item_id)}">Request Reorder</button>
      <p class="card-copy" id="citation-${escapeHtml(item.item_id)}"></p>
      <div class="item-list" id="label-${escapeHtml(item.item_id)}"></div>
      <div class="item-list" id="usage-${escapeHtml(item.item_id)}"></div>
    </article>
  `;
}

function renderPurchases() {
  renderPurchaseSummaryCards();
  renderPurchaseRequests();
  const target = $("#purchasesList");
  if (!target) return;
  renderPurchaseImportTemplates();
  renderPurchaseImportPreview();
  const query = ($("#purchaseSearchInput")?.value || "").trim().toLowerCase();
  const vendor = ($("#purchaseVendorFilter")?.value || "").trim().toLowerCase();
  const grant = ($("#purchaseGrantFilter")?.value || "").trim().toLowerCase();
  const status = ($("#purchaseStatusFilter")?.value || "").trim().toLowerCase();
  const purchases = (state.purchases || []).filter((record) => {
    const haystack = [record.item_name, record.vendor, record.catalog_number, record.oracle_po_number, record.invoice_number, record.grant_or_funding_source, record.status].join(" ").toLowerCase();
    return (!query || haystack.includes(query))
      && (!vendor || String(record.vendor || "").toLowerCase().includes(vendor))
      && (!grant || String(record.grant_or_funding_source || "").toLowerCase().includes(grant))
      && (!status || String(record.status || "").toLowerCase().includes(status));
  });
  target.innerHTML = purchases.length
    ? purchases.map(renderPurchaseRecord).join("")
    : `<div class="empty-state">No purchase records match this filter.</div>`;
}

function renderPurchaseRequests() {
  const target = $("#purchaseRequestsList");
  if (!target) return;
  const requests = state.purchaseRequests || [];
  target.innerHTML = requests.length
    ? requests.map(renderPurchaseRequest).join("")
    : `<div class="empty-state">No purchase requests yet. Create one from the form or use Request Reorder on an inventory item.</div>`;
}

const purchaseMappingInputs = {
  item_name: "#mapItemName",
  vendor: "#mapVendor",
  catalog_number: "#mapCatalog",
  purchase_date: "#mapPurchaseDate",
  cost: "#mapCost",
  quantity: "#mapQuantity",
  grant_or_funding_source: "#mapGrant",
  purchaser: "#mapPurchaser",
  oracle_po_number: "#mapPo",
  invoice_number: "#mapInvoice",
  status: "#mapStatus",
};

function currentPurchaseMapping() {
  const mapping = {};
  Object.entries(purchaseMappingInputs).forEach(([field, selector]) => {
    const value = $(selector)?.value.trim();
    if (value) mapping[field] = value;
  });
  return mapping;
}

function applyPurchaseMappingToForm(mapping = {}) {
  Object.entries(purchaseMappingInputs).forEach(([field, selector]) => {
    const input = $(selector);
    if (input) input.value = mapping[field] || "";
  });
}

function renderPurchaseImportTemplates() {
  const select = $("#purchaseTemplateSelect");
  if (!select) return;
  const selected = select.value;
  select.innerHTML = `<option value="">Suggested mapping</option>${(state.purchaseImportTemplates || []).map((template) => `
    <option value="${escapeHtml(template.template_id)}">${escapeHtml(template.name)}${template.is_default ? " (default)" : ""}</option>
  `).join("")}`;
  select.value = selected;
}

function renderPurchaseImportPreview() {
  const target = $("#purchaseImportPreview");
  if (!target) return;
  const preview = state.purchaseImportPreview;
  if (!preview) {
    target.innerHTML = `<div class="empty-state">Paste CSV text and preview it to review detected columns before mapped import.</div>`;
    return;
  }
  target.innerHTML = `
    <article class="record-card">
      <h3>Import preview</h3>
      <p>${escapeHtml(preview.row_count || 0)} row(s) detected.</p>
      <div class="meta">
        ${(preview.detected_columns || []).map((column) => `<span class="tag">${escapeHtml(column)}</span>`).join("")}
      </div>
      ${(preview.warnings || []).length ? `<p class="warning-copy">${escapeHtml(preview.warnings.join(" "))}</p>` : ""}
      <div class="table-wrap">
        <table>
          <thead>
            <tr>${(preview.detected_columns || []).slice(0, 8).map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${(preview.rows_preview || []).map((row) => `
              <tr>${(preview.detected_columns || []).slice(0, 8).map((column) => `<td>${escapeHtml(row[column] || "")}</td>`).join("")}</tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </article>
  `;
}

function renderPurchaseSummaryCards() {
  const target = $("#purchaseSummaryCards");
  if (!target) return;
  const summary = state.purchaseSummary || {};
  const topGrant = (summary.spend_by_grant || [])[0];
  const topVendor = (summary.spend_by_vendor || [])[0];
  target.innerHTML = `
    <article class="provider-card">
      <div class="provider-card-header"><span>Total spend</span><strong>$${escapeHtml(summary.total_spend ?? 0)}</strong></div>
      <p>${escapeHtml(summary.purchase_count ?? 0)} purchase record(s)</p>
    </article>
    <article class="provider-card">
      <div class="provider-card-header"><span>Top grant</span><strong>$${escapeHtml(topGrant?.total_spend ?? 0)}</strong></div>
      <p>${escapeHtml(topGrant?.name || "No grant data")}</p>
    </article>
    <article class="provider-card">
      <div class="provider-card-header"><span>Top vendor</span><strong>$${escapeHtml(topVendor?.total_spend ?? 0)}</strong></div>
      <p>${escapeHtml(topVendor?.name || "No vendor data")}</p>
    </article>
    <article class="provider-card">
      <div class="provider-card-header"><span>Recent purchases</span><strong>${escapeHtml((summary.recent_purchases || []).length)}</strong></div>
      <p>${escapeHtml((summary.recent_purchases || [])[0]?.item_name || "No recent purchases")}</p>
    </article>
  `;
}

function renderPurchaseRecord(record) {
  return `
    <article class="record-card">
      <h3>${escapeHtml(record.item_name)}</h3>
      <p>${escapeHtml([record.vendor, record.catalog_number, record.oracle_po_number, record.invoice_number].filter(Boolean).join(" · ") || "No purchasing identifiers.")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(record.status || "planned")}</span>
        <span class="tag">${escapeHtml(formatDate(record.purchase_date))}</span>
        <span class="tag">${escapeHtml(record.quantity ?? "no quantity")} item(s)</span>
        <span class="tag">$${escapeHtml(record.cost ?? "0")}</span>
        <span class="tag">${escapeHtml(record.grant_or_funding_source || "no grant")}</span>
      </div>
      <p>${escapeHtml(record.notes || "")}</p>
      <a class="secondary-link-button" href="#/receiving">Receive item</a>
    </article>
  `;
}

function renderPurchaseRequest(record) {
  const status = record.status || "draft";
  return `
    <article class="record-card">
      <h3>${escapeHtml(record.item_name)}</h3>
      <p>${escapeHtml([record.vendor, record.catalog_number, record.grant_or_funding_source].filter(Boolean).join(" · ") || "New reagent or reorder request.")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(status)}</span>
        <span class="tag">${escapeHtml(formatDate(record.request_date))}</span>
        <span class="tag">${escapeHtml(record.quantity_requested ?? "no quantity")} requested</span>
        <span class="tag">$${escapeHtml(record.estimated_cost ?? "0")}</span>
        ${record.linked_inventory_item_id ? `<span class="tag">${escapeHtml(record.linked_inventory_item_id)}</span>` : ""}
      </div>
      <p>${escapeHtml(record.notes || "")}</p>
      <div class="entry-actions compact-actions">
        <a class="secondary-link-button" href="#/receiving">Receive item</a>
        ${status === "draft" ? `<button type="button" class="secondary-button" data-purchase-request-action="submit" data-purchase-request-id="${escapeHtml(record.request_id)}">Submit</button>` : ""}
        ${status === "submitted" ? `<button type="button" class="secondary-button" data-purchase-request-action="approve" data-purchase-request-id="${escapeHtml(record.request_id)}">Approve</button>` : ""}
        ${["submitted", "approved"].includes(status) ? `<button type="button" class="secondary-button" data-purchase-request-action="mark-ordered" data-purchase-request-id="${escapeHtml(record.request_id)}">Mark Ordered</button>` : ""}
        ${status === "ordered" ? `<button type="button" class="secondary-button" data-purchase-request-action="mark-received" data-purchase-request-id="${escapeHtml(record.request_id)}">Mark Received</button>` : ""}
      </div>
    </article>
  `;
}

function renderReceiving() {
  const target = $("#receivingList");
  if (!target) return;
  const records = state.receiving || [];
  target.innerHTML = records.length
    ? records.map(renderReceivingRecord).join("")
    : `<div class="empty-state">No receiving records yet. Receive items after Oracle/manual ordering.</div>`;
}

function renderReceivingRecord(record) {
  return `
    <article class="record-card">
      <h3>${escapeHtml(record.item_name)}</h3>
      <p>${escapeHtml([record.vendor, record.catalog_number, record.lot_number].filter(Boolean).join(" · ") || "No vendor/catalog metadata.")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(formatDate(record.received_date))}</span>
        <span class="tag">${escapeHtml(record.quantity_received ?? "no quantity")} ${escapeHtml(record.units || "")}</span>
        <span class="tag">${escapeHtml(record.storage_location || "no storage")}</span>
        ${record.barcode_or_label ? `<span class="tag">${escapeHtml(record.barcode_or_label)}</span>` : ""}
        ${record.purchase_request_id ? `<span class="tag">${escapeHtml(record.purchase_request_id)}</span>` : ""}
        ${record.purchase_record_id ? `<span class="tag">${escapeHtml(record.purchase_record_id)}</span>` : ""}
        ${record.inventory_item_id ? `<span class="tag">${escapeHtml(record.inventory_item_id)}</span>` : ""}
      </div>
      <p>${escapeHtml(record.notes || "")}</p>
      <button type="button" class="secondary-button" data-receiving-intake="${escapeHtml(record.receiving_id)}">Create/update inventory</button>
    </article>
  `;
}

function renderDesignPlanner() {
  renderDesignReminderCards();
  renderDesignSelect();
  renderDesignImportPreview();
  renderDesignTemplates();
  const target = $("#designList");
  if (!target) return;
  const designs = state.experimentDesigns || [];
  target.innerHTML = designs.length
    ? designs.map(renderExperimentDesign).join("")
    : `<div class="empty-state">No experiment designs yet. Create a design or import a CSV plan.</div>`;
}

function renderDesignReminderCards() {
  const target = $("#designReminderCards");
  if (!target) return;
  const due = state.designDueToday?.reminders || state.designDueToday?.events || [];
  const upcoming = state.designUpcoming?.reminders || state.designUpcoming?.events || [];
  target.innerHTML = `
    <article class="provider-card">
      <div class="provider-card-header"><span>Due today</span><strong>${escapeHtml(state.designDueToday?.count ?? 0)}</strong></div>
      <p>${escapeHtml(due[0]?.title || due[0]?.event?.title || "No design reminders due today")}</p>
    </article>
    <article class="provider-card">
      <div class="provider-card-header"><span>Upcoming</span><strong>${escapeHtml(state.designUpcoming?.count ?? 0)}</strong></div>
      <p>Next 7 days</p>
    </article>
    <article class="provider-card">
      <div class="provider-card-header"><span>Calendar export</span><strong>.ics</strong></div>
      <p>Download reminders for Outlook, Google Calendar, or Apple Calendar. This is a file export, not live sync.</p>
      <a class="secondary-link-button" href="/experiment-designs/reminders/export-ics">Export All Reminders</a>
    </article>
  `;
}

function renderDesignSelect() {
  const select = $("#designSelect");
  if (!select) return;
  const selected = select.value;
  select.innerHTML = (state.experimentDesigns || []).map((design) => `
    <option value="${escapeHtml(design.design_id)}">${escapeHtml(design.title)}</option>
  `).join("");
  if (selected) select.value = selected;
}

function renderExperimentDesign(design) {
  const timeline = groupDesignEvents(design);
  return `
    <article class="record-card">
      <h3>${escapeHtml(design.title)}</h3>
      <p>${escapeHtml([design.experiment_type, design.cell_line_or_model, (design.reporters || []).join("; ")].filter(Boolean).join(" · ") || "Generic experiment design")}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(design.status || "draft")}</span>
        <span class="tag">${escapeHtml((design.conditions || []).length)} condition(s)</span>
        <span class="tag">${escapeHtml((design.events || []).length)} event(s)</span>
        ${design.linked_experiment_id ? `<span class="tag">${escapeHtml(design.linked_experiment_id)}</span>` : ""}
      </div>
      <p>${escapeHtml(design.description || "")}</p>
      <div class="entry-actions compact-actions">
        <a class="secondary-link-button" href="/experiment-designs/${encodeURIComponent(design.design_id)}/export-csv">Export CSV</a>
        <a class="secondary-link-button" href="/experiment-designs/${encodeURIComponent(design.design_id)}/export-ics">Export Calendar</a>
        <button type="button" class="secondary-button" data-save-design-template="${escapeHtml(design.design_id)}">Save as Template</button>
        <button type="button" class="secondary-button" data-generate-plate-layout="${escapeHtml(design.design_id)}">Generate Plate Layout</button>
      </div>
      <p class="muted-note">${design.start_date ? "Calendar export creates an importable .ics file; it does not sync live." : "Calendar export requires a start date so relative days can become real dates."}</p>
      <div class="item-list">
        ${(design.conditions || []).map((condition) => `
          <div class="item-link"><strong>${escapeHtml(condition.condition_name)}</strong><span>${escapeHtml([condition.treatment, condition.dose, condition.units, condition.start_day].filter(Boolean).join(" · "))}</span></div>
        `).join("") || `<div class="empty-state">No conditions yet.</div>`}
      </div>
      <details>
        <summary>Timeline</summary>
        <div class="item-list">
          ${timeline.map((day) => `
            <div class="item-link"><strong>${escapeHtml(day.day)}</strong><span>${escapeHtml(day.events.map((event) => `${event.event_type}: ${event.title}`).join("; "))}</span></div>
          `).join("") || `<div class="empty-state">No timeline events yet.</div>`}
        </div>
      </details>
    </article>
  `;
}

function conditionColor(condition) {
  if (!condition) return "#f4f6f8";
  let hash = 0;
  String(condition).split("").forEach((char) => {
    hash = (hash * 31 + char.charCodeAt(0)) % 360;
  });
  return `hsl(${hash} 68% 88%)`;
}

function renderPlateLayouts() {
  const target = $("#plateLayoutList");
  if (!target) return;
  const layouts = state.plateLayouts || [];
  target.innerHTML = layouts.length
    ? layouts.map(renderPlateLayoutCard).join("")
    : `<div class="empty-state">No plate layouts yet. Generate one from an experiment design.</div>`;
}

function renderPlateLayoutCard(layout) {
  const wells = layout.wells || [];
  return `
    <article class="record-card">
      <div class="panel-heading compact-heading">
        <div>
          <p class="eyebrow">${escapeHtml(layout.format)} · ${escapeHtml(layout.rows)} x ${escapeHtml(layout.columns)}</p>
          <h3>${escapeHtml(layout.title)}</h3>
        </div>
        <div class="entry-actions compact-actions">
          <a class="secondary-link-button" href="/plate-layouts/${encodeURIComponent(layout.layout_id)}/export-csv">Export CSV</a>
          <button type="button" class="secondary-button" onclick="window.print()">Print</button>
        </div>
      </div>
      <div class="meta">
        <span class="tag">${escapeHtml(layout.design_id)}</span>
        <span class="tag">${escapeHtml(wells.filter((well) => well.condition).length)} assigned</span>
      </div>
      ${(layout.warnings || []).map((warning) => `<p class="warning-text">${escapeHtml(warning)}</p>`).join("")}
      <div class="plate-grid" style="display:grid;grid-template-columns:repeat(${Number(layout.columns) || 1}, minmax(54px, 1fr));gap:6px;">
        ${wells.map((well) => `
          <button type="button" class="plate-well" data-edit-well="${escapeHtml(layout.layout_id)}" data-position="${escapeHtml(well.position)}" style="min-height:54px;border:1px solid #d9e2e7;border-radius:8px;background:${escapeHtml(conditionColor(well.condition))};padding:6px;text-align:left;font-size:12px;">
            <strong>${escapeHtml(well.position)}</strong><br />
            <span>${escapeHtml(well.condition || "Empty")}</span><br />
            <small>${escapeHtml([well.sample_id, well.treatment].filter(Boolean).join(" · "))}</small>
          </button>
        `).join("")}
      </div>
    </article>
  `;
}

function seedVisualBuilderDraft() {
  state.visualBuilderDraft = {
    title: "D1 SAG branch design",
    description: "Visual builder demo canvas.",
    nodes: [
      { node_id: "experiment", type: "experiment", label: "D1 SAG retinal organoid design", properties: { experiment_type: "retinal organoid" }, x: 40, y: 40 },
      { node_id: "cell_line", type: "cell_line", label: "SIX6 reporter iPSC", properties: {}, x: 40, y: 150 },
      { node_id: "reporter_six6", type: "reporter", label: "SIX6", properties: {}, x: 40, y: 260 },
      { node_id: "dmso", type: "treatment", label: "DMSO control", properties: { replicate_count: 3, sample_count: 6, start_day: "D1" }, x: 310, y: 80 },
      { node_id: "sag", type: "compound", label: "SAG", properties: { dose: "100", units: "nM", replicate_count: 3, sample_count: 6, start_day: "D1" }, x: 310, y: 200 },
      { node_id: "d32", type: "timepoint", label: "D32", properties: {}, x: 560, y: 130 },
      { node_id: "imaging", type: "imaging", label: "Image SIX6/BRN3B", properties: { reminder_enabled: true }, x: 790, y: 130 },
      { node_id: "analysis", type: "analysis", label: "Quantify marker expression", properties: { reminder_enabled: true }, x: 1020, y: 130 },
    ],
    connections: [
      { source: "experiment", target: "cell_line", relationship: "uses" },
      { source: "experiment", target: "reporter_six6", relationship: "reports" },
      { source: "experiment", target: "dmso", relationship: "branch" },
      { source: "experiment", target: "sag", relationship: "branch" },
      { source: "dmso", target: "d32", relationship: "sequential" },
      { source: "sag", target: "d32", relationship: "sequential" },
      { source: "d32", target: "imaging", relationship: "sequential" },
      { source: "imaging", target: "analysis", relationship: "sequential" },
    ],
  };
  $("#visualBuilderTitle") && ($("#visualBuilderTitle").value = state.visualBuilderDraft.title);
}

function visualBuilderDraft() {
  if (!state.visualBuilderDraft) seedVisualBuilderDraft();
  return state.visualBuilderDraft;
}

function snapshotVisualBuilder() {
  state.visualBuilderUndo.push(JSON.stringify(visualBuilderDraft()));
  state.visualBuilderRedo = [];
}

function renderVisualBuilder() {
  const canvas = $("#visualBuilderCanvas");
  const list = $("#visualBuilderList");
  if (!canvas) return;
  const draft = visualBuilderDraft();
  $("#visualBuilderTitle") && ($("#visualBuilderTitle").value ||= draft.title || "");
  $("#visualBuilderNodeCount") && ($("#visualBuilderNodeCount").textContent = `${draft.nodes.length} nodes`);
  canvas.innerHTML = `
    <div style="min-width:1180px;min-height:360px;position:relative;">
      ${(draft.connections || []).map((connection) => {
        const source = draft.nodes.find((node) => node.node_id === connection.source) || {};
        const target = draft.nodes.find((node) => node.node_id === connection.target) || {};
        return `<div style="position:absolute;left:${Math.min(source.x || 0, target.x || 0) + 120}px;top:${Math.min(source.y || 0, target.y || 0) + 44}px;width:${Math.abs((target.x || 0) - (source.x || 0)) || 80}px;border-top:2px solid #9fb6c3;"></div>`;
      }).join("")}
      ${(draft.nodes || []).map((node) => `
        <button type="button" class="provider-card visual-node" data-visual-node="${escapeHtml(node.node_id)}" style="position:absolute;left:${Number(node.x) || 0}px;top:${Number(node.y) || 0}px;width:190px;text-align:left;">
          <div class="provider-card-header"><span>${escapeHtml(node.type)}</span><strong>${escapeHtml(node.node_id)}</strong></div>
          <p>${escapeHtml(node.label)}</p>
        </button>
      `).join("")}
    </div>
  `;
  $("#visualBuilderMiniMap") && ($("#visualBuilderMiniMap").innerHTML = (draft.nodes || []).map((node) => `<span class="tag">${escapeHtml(node.label)}</span>`).join(" "));
  if (list) {
    list.innerHTML = (state.visualBuilders || []).map((builder) => `
      <button type="button" class="item-link" data-load-visual-builder="${escapeHtml(builder.builder_id)}">
        <strong>${escapeHtml(builder.title)}</strong><span>${escapeHtml(builder.generated_design_id || "canvas saved")}</span>
      </button>
    `).join("") || `<div class="empty-state">No saved visual builders yet.</div>`;
  }
}

function visualBuilderPayload() {
  const draft = visualBuilderDraft();
  return {
    title: $("#visualBuilderTitle")?.value.trim() || draft.title || "Visual experiment design",
    description: draft.description || null,
    nodes: draft.nodes || [],
    connections: draft.connections || [],
  };
}

async function saveVisualBuilder() {
  const saved = await requestJson("/visual-experiment-builders", {
    method: "POST",
    body: JSON.stringify(visualBuilderPayload()),
  });
  $("#visualBuilderStatus").textContent = `Saved visual builder: ${saved.title}`;
  await refreshData();
}

async function generateVisualBuilderDesign() {
  let builder = state.visualBuilders?.[0];
  if (!builder || builder.title !== ($("#visualBuilderTitle")?.value.trim() || visualBuilderDraft().title)) {
    builder = await requestJson("/visual-experiment-builders", {
      method: "POST",
      body: JSON.stringify(visualBuilderPayload()),
    });
  }
  const result = await requestJson(`/visual-experiment-builders/${encodeURIComponent(builder.builder_id)}/generate-design`, {
    method: "POST",
    body: JSON.stringify({
      title: $("#visualBuilderTitle")?.value.trim() || null,
      start_date: $("#visualBuilderStartDate")?.value || null,
      generate_plate_layout: true,
      plate_format: $("#visualBuilderPlateFormat")?.value.trim() || "96-well",
    }),
  });
  $("#visualBuilderStatus").textContent = `Generated design: ${result.design?.title || "visual design"}`;
  $("#visualBuilderPreview").innerHTML = `
    <article class="record-card">
      <h3>${escapeHtml(result.design?.title || "Generated design")}</h3>
      <p>${escapeHtml((result.compiled?.warnings || []).join(" ") || "No builder warnings.")}</p>
      <div class="entry-actions compact-actions">
        <a class="secondary-link-button" href="#/design-planner">Open Designs</a>
        ${result.plate_layout ? `<a class="secondary-link-button" href="#/plate-layouts">Open Plate Layout</a>` : ""}
        <a class="secondary-link-button" href="/experiment-designs/${encodeURIComponent(result.design.design_id)}/export-csv">Export CSV</a>
      </div>
    </article>
  `;
  await refreshData();
}

function duplicateVisualBranch() {
  snapshotVisualBuilder();
  const draft = visualBuilderDraft();
  const source = draft.nodes.find((node) => ["treatment", "compound"].includes(node.type));
  if (!source) return;
  const clone = { ...source, node_id: `${source.node_id}_copy_${Date.now()}`, label: `${source.label} copy`, y: Number(source.y || 0) + 110 };
  draft.nodes.push(clone);
  draft.connections.push({ source: "experiment", target: clone.node_id, relationship: "branch" });
  renderVisualBuilder();
}

function renderDesignTemplates() {
  const target = $("#designTemplateList");
  if (!target) return;
  const templates = state.experimentDesignTemplates || [];
  target.innerHTML = templates.length
    ? templates.map((template) => `
      <article class="record-card">
        <div class="panel-heading compact-heading">
          <div>
            <p class="eyebrow">${escapeHtml(template.is_builtin ? "Built-in" : "Saved template")}</p>
            <h3>${escapeHtml(template.name)}</h3>
          </div>
          <button type="button" data-create-design-template="${escapeHtml(template.template_id)}">Create from Template</button>
        </div>
        <p>${escapeHtml(template.description || "Reusable experiment design template.")}</p>
        <div class="meta">
          ${template.experiment_type ? `<span class="tag">${escapeHtml(template.experiment_type)}</span>` : ""}
          ${(template.tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          <span class="tag">${escapeHtml((template.default_conditions || []).length)} condition(s)</span>
          <span class="tag">${escapeHtml((template.default_events || []).length)} event(s)</span>
        </div>
        <details>
          <summary>Template preview</summary>
          <div class="item-list">
            ${(template.default_conditions || []).map((condition) => `
              <div class="item-link"><strong>${escapeHtml(condition.condition_name || condition.name || "Condition")}</strong><span>${escapeHtml([condition.treatment, condition.start_day, condition.end_day].filter(Boolean).join(" · "))}</span></div>
            `).join("") || `<div class="empty-state">No default conditions.</div>`}
            ${(template.default_events || []).map((event) => `
              <div class="item-link"><strong>${escapeHtml(event.day || "D0")} ${escapeHtml(event.title || "Event")}</strong><span>${escapeHtml(event.event_type || "custom")}</span></div>
            `).join("") || `<div class="empty-state">No default events.</div>`}
          </div>
        </details>
        ${template.is_builtin ? "" : `<button type="button" class="secondary-button" data-delete-design-template="${escapeHtml(template.template_id)}">Delete Template</button>`}
      </article>
    `).join("")
    : `<div class="empty-state">No experiment design templates available.</div>`;
}

function groupDesignEvents(design) {
  const grouped = {};
  (design.events || []).forEach((event) => {
    const day = event.day || "D0";
    grouped[day] = grouped[day] || [];
    grouped[day].push(event);
  });
  return Object.entries(grouped)
    .map(([day, events]) => ({ day, events }))
    .sort((a, b) => Number(String(a.day).match(/-?\d+/)?.[0] || 0) - Number(String(b.day).match(/-?\d+/)?.[0] || 0));
}

function renderDesignImportPreview() {
  const target = $("#designImportPreview");
  if (!target) return;
  const preview = state.designImportPreview;
  if (!preview) {
    target.innerHTML = `<div class="empty-state">Paste CSV text and preview it before importing a design.</div>`;
    return;
  }
  target.innerHTML = `
    <article class="record-card">
      <h3>Design import preview</h3>
      <p>${escapeHtml(preview.row_count || 0)} row(s). Conditions: ${escapeHtml((preview.inferred_conditions || []).join(", ") || "none detected")}</p>
      <div class="meta">${(preview.inferred_event_days || preview.inferred_days || []).map((day) => `<span class="tag">${escapeHtml(day)}</span>`).join("")}</div>
      ${(preview.warnings || []).length ? `<p class="warning-text">${escapeHtml(preview.warnings.join(" "))}</p>` : ""}
      <h4>Suggested mappings</h4>
      <div class="form-grid">
        ${Object.entries(preview.suggested_mappings || {}).map(([field, column]) => `
          <div>
            <label for="designMap_${escapeHtml(field)}">${escapeHtml(field)}</label>
            <input id="designMap_${escapeHtml(field)}" data-design-map-field="${escapeHtml(field)}" type="text" value="${escapeHtml(column)}" />
          </div>
        `).join("") || `<div class="empty-state">No mappings suggested. Add headers such as Condition, Day, Event, Treatment, or Replicate.</div>`}
      </div>
      <details>
        <summary>Preview rows</summary>
        <pre>${escapeHtml(JSON.stringify(preview.preview_rows || preview.rows_preview || [], null, 2))}</pre>
      </details>
      <details>
        <summary>Saved templates</summary>
        <div class="item-list">
          ${(state.designImportTemplates || []).map((template) => `
            <button type="button" class="item-link" data-design-template='${escapeHtml(JSON.stringify(template.mapping || {}))}'>
              <strong>${escapeHtml(template.name)}</strong><span>${escapeHtml(template.provider || "experiment_designs")}</span>
            </button>
          `).join("") || `<div class="empty-state">No saved templates yet.</div>`}
        </div>
      </details>
    </article>
  `;
}

function numberOrNull(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function saveInventoryItem() {
  const payload = {
    name: $("#inventoryName").value.trim(),
    category: $("#inventoryCategory").value.trim() || null,
    vendor: $("#inventoryVendor").value.trim() || null,
    catalog_number: $("#inventoryCatalog").value.trim() || null,
    lot_number: $("#inventoryLot").value.trim() || null,
    rrid: $("#inventoryRrid").value.trim() || null,
    price: numberOrNull($("#inventoryPrice").value),
    unit: $("#inventoryUnit").value.trim() || null,
    storage_location: $("#inventoryLocation").value.trim() || null,
    quantity: numberOrNull($("#inventoryQuantity").value),
    reorder_threshold: numberOrNull($("#inventoryThreshold").value),
    expiration_date: $("#inventoryExpiration").value || null,
    barcode: $("#inventoryBarcode").value.trim() || null,
    qr_code: $("#inventoryQrCode").value.trim() || null,
    internal_label: $("#inventoryInternalLabel").value.trim() || null,
    freezer_box: $("#inventoryFreezerBox").value.trim() || null,
    freezer_position: $("#inventoryFreezerPosition").value.trim() || null,
    shelf: $("#inventoryShelf").value.trim() || null,
    room: $("#inventoryRoom").value.trim() || null,
    notes: $("#inventoryNotes").value.trim() || null,
    linked_resource_id: $("#inventoryResource").value.trim() || null,
  };
  const saved = await requestJson("/inventory", { method: "POST", body: JSON.stringify(payload) });
  $("#inventoryForm").reset();
  $("#inventoryStatus").textContent = `Saved inventory item: ${saved.name}`;
  await refreshData();
}

async function savePurchaseRecord() {
  const payload = {
    item_name: $("#purchaseItemName").value.trim(),
    vendor: $("#purchaseVendor").value.trim() || null,
    catalog_number: $("#purchaseCatalog").value.trim() || null,
    purchase_date: $("#purchaseDate").value || null,
    cost: numberOrNull($("#purchaseCost").value),
    quantity: numberOrNull($("#purchaseQuantity").value),
    grant_or_funding_source: $("#purchaseGrant").value.trim() || null,
    purchaser: $("#purchasePurchaser").value.trim() || null,
    oracle_po_number: $("#purchasePo").value.trim() || null,
    invoice_number: $("#purchaseInvoice").value.trim() || null,
    status: $("#purchaseStatus").value.trim() || "planned",
    notes: $("#purchaseNotes").value.trim() || null,
  };
  const saved = await requestJson("/purchases", { method: "POST", body: JSON.stringify(payload) });
  $("#purchaseForm").reset();
  $("#purchaseStatusMessage").textContent = `Saved purchase record: ${saved.item_name}`;
  await refreshData();
}

async function savePurchaseRequest() {
  const payload = {
    item_name: $("#purchaseRequestItemName").value.trim(),
    vendor: $("#purchaseRequestVendor").value.trim() || null,
    catalog_number: $("#purchaseRequestCatalog").value.trim() || null,
    quantity_requested: numberOrNull($("#purchaseRequestQuantity").value),
    estimated_cost: numberOrNull($("#purchaseRequestCost").value),
    grant_or_funding_source: $("#purchaseRequestGrant").value.trim() || null,
    requested_by: $("#purchaseRequestBy").value.trim() || null,
    status: $("#purchaseRequestStatus").value || "draft",
    notes: $("#purchaseRequestNotes").value.trim() || null,
    linked_inventory_item_id: $("#purchaseRequestInventoryItem").value.trim() || null,
  };
  const saved = await requestJson("/purchase-requests", { method: "POST", body: JSON.stringify(payload) });
  $("#purchaseRequestForm").reset();
  $("#purchaseStatusMessage").textContent = `Saved purchase request: ${saved.item_name}`;
  await refreshData();
}

async function saveReceivingRecord() {
  const payload = {
    item_name: $("#receivingItemName").value.trim(),
    vendor: $("#receivingVendor").value.trim() || null,
    catalog_number: $("#receivingCatalog").value.trim() || null,
    lot_number: $("#receivingLot").value.trim() || null,
    quantity_received: numberOrNull($("#receivingQuantity").value),
    units: $("#receivingUnits").value.trim() || null,
    received_by: $("#receivingBy").value.trim() || null,
    received_date: $("#receivingDate").value || null,
    expiration_date: $("#receivingExpiration").value || null,
    storage_location: $("#receivingLocation").value.trim() || null,
    barcode_or_label: $("#receivingBarcode").value.trim() || null,
    purchase_request_id: $("#receivingPurchaseRequest").value.trim() || null,
    purchase_record_id: $("#receivingPurchaseRecord").value.trim() || null,
    inventory_item_id: $("#receivingInventoryItem").value.trim() || null,
    notes: $("#receivingNotes").value.trim() || null,
  };
  const saved = await requestJson("/receiving", { method: "POST", body: JSON.stringify(payload) });
  $("#receivingForm").reset();
  $("#receivingStatus").textContent = `Saved receiving record: ${saved.item_name}`;
  await refreshData();
}

async function intakeReceivingRecord(receivingId) {
  const result = await requestJson(`/receiving/${encodeURIComponent(receivingId)}/create-or-update-inventory`, {
    method: "POST",
    body: JSON.stringify({ update_existing: true }),
  });
  $("#receivingStatus").textContent = `Inventory updated: ${result.inventory_item?.name || result.inventory_item?.item_id || "item"}`;
  await refreshData();
}

async function saveExperimentDesign() {
  const payload = {
    title: $("#designTitle").value.trim(),
    experiment_type: $("#designType").value.trim() || null,
    cell_line_or_model: $("#designModel").value.trim() || null,
    reporters: $("#designReporters").value.split(/[;,]/).map((item) => item.trim()).filter(Boolean),
    description: $("#designDescription").value.trim() || null,
    start_date: $("#designStartDate").value || null,
    status: $("#designStatusSelect").value || "draft",
  };
  const saved = await requestJson("/experiment-designs", { method: "POST", body: JSON.stringify(payload) });
  $("#designForm").reset();
  $("#designPlannerStatus").textContent = `Created design: ${saved.title}`;
  await refreshData();
}

async function addDesignCondition() {
  const designId = $("#designSelect").value;
  if (!designId) {
    $("#designPlannerStatus").textContent = "Create or select a design before adding conditions.";
    return;
  }
  const payload = {
    condition_name: $("#conditionName").value.trim(),
    treatment: $("#conditionTreatment").value.trim() || null,
    dose: $("#conditionDose").value.trim() || null,
    units: $("#conditionUnits").value.trim() || null,
    start_day: $("#conditionStart").value.trim() || null,
    end_day: $("#conditionEnd").value.trim() || null,
    notes: $("#conditionNotes").value.trim() || null,
    replicate_count: numberOrNull($("#conditionReplicates").value),
    sample_count: numberOrNull($("#conditionSamples").value),
  };
  await requestJson(`/experiment-designs/${encodeURIComponent(designId)}/conditions`, { method: "POST", body: JSON.stringify(payload) });
  $("#designConditionForm").reset();
  $("#designPlannerStatus").textContent = "Added condition.";
  await refreshData();
}

async function addDesignEvent() {
  const designId = $("#designSelect").value;
  if (!designId) {
    $("#designPlannerStatus").textContent = "Create or select a design before adding events.";
    return;
  }
  const payload = {
    day: $("#eventDay").value.trim(),
    event_type: $("#eventType").value.trim() || "custom",
    title: $("#eventTitle").value.trim(),
    description: $("#eventDescription").value.trim() || null,
    alert_enabled: $("#eventAlert").value === "true",
    reminder_enabled: $("#eventAlert").value === "true",
  };
  await requestJson(`/experiment-designs/${encodeURIComponent(designId)}/events`, { method: "POST", body: JSON.stringify(payload) });
  $("#designEventForm").reset();
  $("#designPlannerStatus").textContent = "Added timeline event.";
  await refreshData();
}

async function previewDesignImport() {
  const csvText = $("#designCsvText").value.trim();
  if (!csvText) {
    $("#designPlannerStatus").textContent = "Paste CSV text before previewing.";
    return;
  }
  state.designImportPreview = await requestJson("/experiment-designs/import-preview", {
    method: "POST",
    body: JSON.stringify({ csv_text: csvText }),
  });
  renderDesignImportPreview();
}

async function importDesignCsv() {
  const csvText = $("#designCsvText").value.trim();
  if (!csvText) {
    $("#designPlannerStatus").textContent = "Paste CSV text before importing.";
    return;
  }
  const mapping = collectDesignImportMapping();
  const endpoint = Object.keys(mapping).length ? "/experiment-designs/import-mapped-csv" : "/experiment-designs/import-csv";
  const saved = await requestJson(endpoint, {
    method: "POST",
    body: JSON.stringify(Object.keys(mapping).length ? { csv_text: csvText, mapping } : { csv_text: csvText }),
  });
  $("#designCsvText").value = "";
  state.designImportPreview = null;
  $("#designPlannerStatus").textContent = `Imported design: ${saved.title}`;
  await refreshData();
}

function collectDesignImportMapping() {
  const mapping = {};
  document.querySelectorAll("[data-design-map-field]").forEach((input) => {
    const field = input.dataset.designMapField;
    const column = input.value.trim();
    if (field && column) mapping[field] = column;
  });
  return mapping;
}

async function saveDesignImportTemplate() {
  const mapping = collectDesignImportMapping();
  const name = $("#designTemplateName").value.trim() || "Experiment Design Import";
  if (!Object.keys(mapping).length) {
    $("#designPlannerStatus").textContent = "Preview a CSV or enter mappings before saving a template.";
    return;
  }
  await requestJson("/experiment-designs/import-templates", {
    method: "POST",
    body: JSON.stringify({ name, mapping, provider: "experiment_designs" }),
  });
  $("#designPlannerStatus").textContent = `Saved design import template: ${name}`;
  await refreshData();
}

async function createDesignFromTemplate(templateId) {
  const template = (state.experimentDesignTemplates || []).find((item) => item.template_id === templateId);
  const title = window.prompt("New design title", template ? `${template.name} design` : "New experiment design");
  if (title === null) return;
  const startDate = window.prompt("Start date (YYYY-MM-DD, optional)", "");
  const saved = await requestJson(`/experiment-design-templates/${encodeURIComponent(templateId)}/create-design`, {
    method: "POST",
    body: JSON.stringify({ title: title.trim() || null, start_date: startDate.trim() || null, status: "draft" }),
  });
  $("#designPlannerStatus") && ($("#designPlannerStatus").textContent = `Created design from template: ${saved.title}`);
  await refreshData();
  window.location.hash = "#/design-planner";
}

async function saveCurrentDesignAsTemplate(designId) {
  const design = (state.experimentDesigns || []).find((item) => item.design_id === designId);
  const name = window.prompt("Template name", design ? `${design.title} template` : "Experiment design template");
  if (name === null) return;
  await requestJson(`/experiment-designs/${encodeURIComponent(designId)}/save-template`, {
    method: "POST",
    body: JSON.stringify({ name: name.trim() || null }),
  });
  $("#designPlannerStatus").textContent = `Saved template: ${name || "Experiment design template"}`;
  await refreshData();
}

async function deleteDesignTemplate(templateId) {
  if (!window.confirm("Delete this saved design template?")) return;
  await requestJson(`/experiment-design-templates/${encodeURIComponent(templateId)}`, { method: "DELETE" });
  await refreshData();
}

async function generatePlateLayout(designId) {
  const format = window.prompt("Plate format: 6-well, 12-well, 24-well, 48-well, 96-well, 384-well, tube_rack, custom", "96-well");
  if (format === null) return;
  const randomized = window.confirm("Randomize assignments?");
  const saved = await requestJson(`/experiment-designs/${encodeURIComponent(designId)}/generate-plate-layout`, {
    method: "POST",
    body: JSON.stringify({ format: format.trim() || "96-well", randomized, grouped_by_condition: !randomized, balanced: !randomized }),
  });
  $("#designPlannerStatus").textContent = `Generated plate layout: ${saved.title}`;
  await refreshData();
  window.location.hash = "#/plate-layouts";
}

async function editPlateWell(layoutId, position) {
  const layout = (state.plateLayouts || []).find((item) => item.layout_id === layoutId);
  if (!layout) return;
  const well = (layout.wells || []).find((item) => item.position === position);
  if (!well) return;
  const condition = window.prompt(`Condition for ${position}`, well.condition || "");
  if (condition === null) return;
  const sampleId = window.prompt(`Sample ID for ${position}`, well.sample_id || "");
  if (sampleId === null) return;
  const treatment = window.prompt(`Treatment for ${position}`, well.treatment || "");
  if (treatment === null) return;
  const updatedWells = (layout.wells || []).map((item) => item.position === position
    ? { ...item, condition: condition || null, sample_id: sampleId || null, treatment: treatment || null }
    : item);
  await requestJson(`/plate-layouts/${encodeURIComponent(layoutId)}`, {
    method: "PUT",
    body: JSON.stringify({
      design_id: layout.design_id,
      title: layout.title,
      format: layout.format,
      rows: layout.rows,
      columns: layout.columns,
      wells: updatedWells,
      warnings: layout.warnings || [],
    }),
  });
  await refreshData();
}

async function checkSelectedDesignBalance() {
  const design = (state.experimentDesigns || []).find((item) => item.design_id === $("#designSelect").value);
  if (!design) {
    $("#designPlannerStatus").textContent = "Select a design to check.";
    return;
  }
  const result = await requestJson("/experiment-designs/doe/check-balance", {
    method: "POST",
    body: JSON.stringify({ conditions: design.conditions || [] }),
  });
  $("#designPlannerStatus").textContent = result.warnings?.length ? result.warnings.join(" ") : "Design appears balanced by current checks.";
}

async function updateDesignReminder(eventId, action) {
  if (!eventId) return;
  await requestJson(`/experiment-designs/reminders/${encodeURIComponent(eventId)}/${action}`, { method: "POST" });
  await refreshData();
}

async function updatePurchaseRequestStatus(requestId, action) {
  const body = action === "mark-received" ? JSON.stringify({ update_inventory_quantity: true }) : undefined;
  const saved = await requestJson(`/purchase-requests/${encodeURIComponent(requestId)}/${action}`, {
    method: "POST",
    ...(body ? { body } : {}),
  });
  $("#purchaseStatusMessage").textContent = `Purchase request ${saved.item_name} is now ${saved.status}.`;
  await refreshData();
}

async function requestInventoryReorder(itemId) {
  const saved = await requestJson(`/inventory/${encodeURIComponent(itemId)}/request-reorder`, { method: "POST" });
  $("#inventoryStatus").textContent = `Created purchase request for ${saved.item_name}.`;
  await refreshData();
}

async function importPurchaseCsv() {
  const csvText = $("#purchaseCsvText").value.trim();
  if (!csvText) {
    $("#purchaseStatusMessage").textContent = "Paste CSV text before importing.";
    return;
  }
  const payload = await requestJson("/purchases/import-csv", {
    method: "POST",
    body: JSON.stringify({ provider: "oracle_purchasing", csv_text: csvText }),
  });
  $("#purchaseCsvText").value = "";
  $("#purchaseStatusMessage").textContent = `Imported ${payload.imported_count} purchase record(s) from CSV.`;
  await refreshData();
}

async function previewMappedPurchaseCsv() {
  const csvText = $("#purchaseMappedCsvText").value.trim();
  if (!csvText) {
    $("#purchaseStatusMessage").textContent = "Paste CSV text before previewing.";
    return;
  }
  const preview = await requestJson("/purchases/import-preview", {
    method: "POST",
    body: JSON.stringify({ csv_text: csvText }),
  });
  state.purchaseImportPreview = preview;
  applyPurchaseMappingToForm({ ...preview.suggested_mapping, ...currentPurchaseMapping() });
  renderPurchaseImportPreview();
  $("#purchaseStatusMessage").textContent = `Detected ${preview.row_count} row(s) and ${preview.detected_columns.length} column(s).`;
}

async function importMappedPurchaseCsv() {
  const csvText = $("#purchaseMappedCsvText").value.trim();
  const mapping = currentPurchaseMapping();
  if (!csvText) {
    $("#purchaseStatusMessage").textContent = "Paste CSV text before importing.";
    return;
  }
  if (!mapping.item_name) {
    $("#purchaseStatusMessage").textContent = "Map the item_name field before importing.";
    return;
  }
  const payload = await requestJson("/purchases/import-mapped-csv", {
    method: "POST",
    body: JSON.stringify({ provider: "oracle_purchasing", csv_text: csvText, mapping }),
  });
  $("#purchaseStatusMessage").textContent = `Imported ${payload.imported_count} purchase record(s); skipped ${payload.skipped_count}.`;
  await refreshData();
}

async function savePurchaseImportTemplate() {
  const name = $("#purchaseTemplateName").value.trim();
  const mapping = currentPurchaseMapping();
  if (!name) {
    $("#purchaseStatusMessage").textContent = "Enter a template name before saving.";
    return;
  }
  if (!mapping.item_name) {
    $("#purchaseStatusMessage").textContent = "Map at least item_name before saving a template.";
    return;
  }
  const saved = await requestJson("/purchases/import-templates", {
    method: "POST",
    body: JSON.stringify({ name, provider: "oracle_purchasing", mapping }),
  });
  $("#purchaseTemplateName").value = "";
  $("#purchaseStatusMessage").textContent = `Saved mapping template: ${saved.name}`;
  await refreshData();
}

async function showMethodsCitation(itemId) {
  const citation = await requestJson(`/inventory/${encodeURIComponent(itemId)}/methods-citation`);
  const target = $(`#citation-${CSS.escape(itemId)}`);
  if (target) target.textContent = citation.methods_citation;
}

async function copyMethodsCitation(itemId) {
  const citation = await requestJson(`/inventory/${encodeURIComponent(itemId)}/methods-citation`);
  await navigator.clipboard?.writeText(citation.methods_citation);
  const target = $(`#citation-${CSS.escape(itemId)}`);
  if (target) target.textContent = `Copied: ${citation.methods_citation}`;
}

async function showInventoryUsage(itemId) {
  const usage = await requestJson(`/inventory/${encodeURIComponent(itemId)}/usage`);
  const target = $(`#usage-${CSS.escape(itemId)}`);
  if (!target) return;
  target.innerHTML = usage.length
    ? usage.map((record) => `
      <article class="timeline-item">
        <div class="timeline-item-header">${timelineBadge("reagent_used")}<strong>${escapeHtml(record.purpose || "Inventory used")}</strong></div>
        <span>${escapeHtml(record.date_used || record.created_at)} · ${escapeHtml(record.amount_used ?? "amount not recorded")} ${escapeHtml(record.units || "")}</span>
        <p>${escapeHtml(record.notes || record.experiment_id || "")}</p>
      </article>
    `).join("")
    : `<div class="empty-state">No usage history recorded for this item.</div>`;
}

async function assignInventoryCode(itemId) {
  const barcode = prompt("Barcode value") || "";
  const qrCode = prompt("QR code value", barcode) || "";
  const internalLabel = prompt("Internal label", barcode || qrCode) || "";
  const freezerBox = prompt("Freezer box") || "";
  const freezerPosition = prompt("Freezer position") || "";
  const saved = await requestJson(`/inventory/${encodeURIComponent(itemId)}/assign-code`, {
    method: "POST",
    body: JSON.stringify({
      barcode: barcode.trim() || null,
      qr_code: qrCode.trim() || null,
      internal_label: internalLabel.trim() || null,
      freezer_box: freezerBox.trim() || null,
      freezer_position: freezerPosition.trim() || null,
    }),
  });
  $("#inventoryStatus").textContent = `Assigned code for ${saved.name}.`;
  await refreshData();
}

async function showInventoryLabel(itemId) {
  const label = await requestJson(`/inventory/${encodeURIComponent(itemId)}/label`);
  const target = $(`#label-${CSS.escape(itemId)}`);
  if (!target) return;
  target.innerHTML = `
    <article class="record-card">
      <h4>Printable label</h4>
      ${(label.print_lines || []).filter(Boolean).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}
      <div class="meta">
        <span class="tag">Code: ${escapeHtml(label.code_value || "")}</span>
        ${label.internal_label ? `<span class="tag">${escapeHtml(label.internal_label)}</span>` : ""}
      </div>
    </article>
  `;
}

async function generateExperimentMethodsText(experimentId) {
  const payload = await requestJson(`/experiments/${encodeURIComponent(experimentId)}/methods-materials`);
  const target = $("#methodsMaterialsText");
  if (target) target.textContent = payload.text || "No methods text generated.";
  if (payload.text && navigator.clipboard) {
    await navigator.clipboard.writeText(payload.text);
  }
}

async function renderProtocolWorkspace(protocolId) {
  const target = $("#protocolDetail");
  target.innerHTML = `<div class="empty-state">Loading protocol workspace...</div>`;
  try {
    const protocol = await requestJson(`/protocols/${encodeURIComponent(protocolId)}`);
    const history = protocol.history || [];
    const comparable = history.filter((item) => item.id !== protocol.id)[0];
    target.innerHTML = `
      <a class="inline-link" href="#/protocols">Back to protocols</a>
      <div class="detail-header">
        <div>
          <p class="eyebrow">${escapeHtml(protocol.version || "Protocol")}</p>
          <h2>${escapeHtml(protocol.title || "Protocol Workspace")}</h2>
        </div>
        <div class="prompt-row">
          <span class="status-pill ok">${escapeHtml(protocol.provider || "local")}</span>
          ${comparable ? `<button type="button" class="secondary-button" id="compareProtocolButton" data-other-id="${escapeHtml(comparable.id)}">Compare versions</button>` : ""}
        </div>
      </div>
      <div class="detail-grid">
        ${detailField("Linked experiments", protocol.usage_statistics?.experiment_count)}
        ${detailField("First used", formatDate(protocol.usage_statistics?.first_used))}
        ${detailField("Last used", formatDate(protocol.usage_statistics?.last_used))}
        ${detailField("Success rate", protocol.success_metrics?.success_rate ?? "Not enough data")}
        ${detailField("Positive outcomes", protocol.success_metrics?.positive_outcome_count)}
        ${detailField("Concern count", protocol.success_metrics?.concern_count)}
      </div>
      <section class="detail-section">
        <h3>Research Copilot</h3>
        <p>${escapeHtml(protocol.research_copilot?.performance_summary || "Protocol performance summary unavailable.")}</p>
        <h4>Potential concerns</h4>
        <ul>${listItems(protocol.research_copilot?.potential_concerns || [])}</ul>
        <h4>Suggested improvements</h4>
        <ul>${listItems(protocol.research_copilot?.suggested_improvements || [])}</ul>
        <p class="privacy-note">${escapeHtml(protocol.research_copilot?.guardrail || "ResearchOS never automatically edits protocols.")}</p>
      </section>
      ${workspaceSection("Version History", history, renderProtocolHistoryItem)}
      <section class="detail-section" id="protocolComparisonPanel" hidden></section>
      ${workspaceSection("Timeline", protocol.timeline || [], renderWorkspaceTimelineEvent)}
      ${workspaceSection("Experiments", protocol.experiments || [], renderWorkspaceExperiment)}
      ${workspaceSection("Related Literature", protocol.related_literature || [], renderWorkspaceDocument)}
      ${workspaceSection("Statistics", protocol.statistics || [], renderWorkspaceStatistic)}
      ${tagSection("Detected protocol terms", protocol.usage_statistics?.protocol_terms || [])}
      <details class="detail-section">
        <summary><h3>Source Content</h3></summary>
        <pre class="markdown-preview">${escapeHtml(protocol.content || "No source content available.")}</pre>
      </details>
    `;
    const compareButton = $("#compareProtocolButton");
    if (compareButton) {
      compareButton.addEventListener("click", () => compareProtocolVersions(protocol.id, compareButton.dataset.otherId));
    }
  } catch (error) {
    target.innerHTML = `<div class="empty-state">Protocol workspace unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

function renderProtocolHistoryItem(protocol) {
  return `
    <a class="item-link" href="#/protocols/${encodeURIComponent(protocol.id)}">
      <strong>${escapeHtml(protocol.title)}</strong>
      <span>${escapeHtml(protocol.version)} · ${escapeHtml(formatDate(protocol.updated_at || protocol.created_at))} · ${escapeHtml(protocol.linked_experiment_count || 0)} experiments</span>
    </a>
  `;
}

async function compareProtocolVersions(protocolId, otherId) {
  const panel = $("#protocolComparisonPanel");
  panel.hidden = false;
  panel.innerHTML = `<div class="empty-state">Comparing protocol versions...</div>`;
  try {
    const comparison = await requestJson(`/protocols/${encodeURIComponent(protocolId)}/compare/${encodeURIComponent(otherId)}`);
    panel.innerHTML = `
      <h3>Protocol Version Comparison</h3>
      <p>${escapeHtml(comparison.left?.title || "Left protocol")} vs ${escapeHtml(comparison.right?.title || "right protocol")}</p>
      <div class="detail-grid">
        ${detailField("Added lines", comparison.summary?.added_count)}
        ${detailField("Removed lines", comparison.summary?.removed_count)}
        ${detailField("Changed", comparison.summary?.changed ? "Yes" : "No")}
      </div>
      <h4>Detected changes</h4>
      <ul>${listItems(comparison.summary?.interpretation || [])}</ul>
      <details>
        <summary><h4>Text diff</h4></summary>
        <pre class="markdown-preview">${escapeHtml((comparison.changes?.diff || []).join("\n"))}</pre>
      </details>
    `;
  } catch (error) {
    panel.innerHTML = `<div class="empty-state">Protocol comparison failed: ${escapeHtml(error.message)}</div>`;
  }
}

function statusLabel(status) {
  return {
    active: "Active",
    ok: "Active",
    connected: "Connected",
    configured: "Configured",
    available: "Available",
    not_connected: "Not connected",
    auth_required: "Not connected",
    pending_ucsd_approval: "Pending UCSD approval",
    not_configured: "Not configured",
    warn: "Needs attention",
    error: "Error",
  }[status] || String(status || "Unknown");
}

function statusClass(status) {
  return ["active", "ok", "connected", "configured", "available"].includes(status) ? "ok" : "warn";
}

function providerCard(title, status, message, meta = "") {
  return `
    <article class="provider-card">
      <div class="provider-card-header">
        <span>${escapeHtml(title)}</span>
        <strong class="status-pill ${statusClass(status)}">${escapeHtml(statusLabel(status))}</strong>
      </div>
      <p>${escapeHtml(message || "")}</p>
      ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
    </article>
  `;
}

function renderProviderSettings() {
  const status = state.providerStatus;
  if (!status) {
    $("#providerCards").innerHTML = `<div class="empty-state">Provider status is not available.</div>`;
    renderCurrentUserSettings();
    renderAuthReadinessSettings();
    renderAgentSettings();
    renderOneNoteReadinessSettings();
    renderDeploymentSettings();
    renderProductionReadinessSettings();
    return;
  }

  $("#providerCards").innerHTML = [
    providerCard(
      "Markdown demo provider",
      status.markdown_provider.status,
      status.markdown_provider.message,
      `${status.document_count} documents indexed`,
    ),
    providerCard(
      "OneNote provider",
      status.onenote_auth.status,
      status.onenote_auth.message,
      `Sync: ${statusLabel(status.onenote_sync.status)}`,
    ),
    providerCard(
      "AI provider",
      status.ai_provider.status,
      status.ai_provider.message,
      status.ai_provider.configured ? `${status.ai_provider.provider} / ${status.ai_provider.model}` : "",
    ),
    providerCard(
      "Local database",
      status.database.status,
      status.database.message,
      `${status.experiment_count} experiments indexed`,
    ),
    providerCard(
      "Vector index",
      status.vector_index.status,
      status.vector_index.message,
    ),
  ].join("");
  renderCurrentUserSettings();
  renderAuthReadinessSettings();
  renderAgentSettings();
  renderOneNoteReadinessSettings();
  renderDeploymentSettings();
  renderProductionReadinessSettings();
}

function renderCurrentUserSettings() {
  const target = $("#currentUserCards");
  if (!target) return;
  const user = state.currentUser;
  const permissionSummary = state.currentPermissions || user?.permission_summary || {};
  const resourcePermissions = permissionSummary.resource_permissions || {};
  const workspace = state.currentWorkspace || user?.current_workspace || state.dailyDashboard?.workspace || {};
  const membership = workspace.current_user_membership || {};
  const members = workspace.members || [];
  if (!user) {
    target.innerHTML = `<div class="empty-state">Current user is not available.</div>`;
    return;
  }
  const permissions = user.permissions || {};
  target.innerHTML = [
    providerCard(
      "Signed in as",
      "active",
      user.display_name || user.email || "ResearchOS user",
      user.email || "",
    ),
    providerCard(
      "Role",
      user.role === "admin" ? "configured" : "active",
      user.role || "viewer",
      `View: ${permissions.can_view ? "yes" : "no"} · Edit: ${permissions.can_edit ? "yes" : "no"} · Admin: ${permissions.can_admin ? "yes" : "no"}`,
    ),
    providerCard(
      "Auth mode",
      user.auth_enabled ? "configured" : "warn",
      user.auth_enabled ? "Authentication enforcement enabled." : "Development mode: auth disabled.",
      user.auth_mode || "unknown",
    ),
    providerCard(
      "Resource permissions",
      "active",
      Object.entries(resourcePermissions)
        .map(([name, value]) => `${name}: ${value.can_edit ? "edit" : value.can_view ? "view" : "none"}`)
        .join(" · ") || "No resource permissions available.",
      permissionSummary.enforcement?.note || "Permissions are scaffolded for future enforcement.",
    ),
    providerCard(
      "Current workspace",
      "active",
      workspace.name || "Demo Lab Workspace",
      workspace.institution || "ResearchOS Local Demo",
    ),
    providerCard(
      "Workspace membership",
      membership.role === "admin" ? "configured" : "active",
      membership.role || user.role || "admin",
      workspace.workspace_id || "workspace:demo-lab",
    ),
    providerCard(
      "Workspace members",
      "active",
      `${members.length || 1} member${(members.length || 1) === 1 ? "" : "s"}`,
      members
        .map((member) => `${member.display_name || member.email || member.user_id}: ${member.role}`)
        .join(" · ") || `${user.display_name || user.email}: ${membership.role || user.role || "admin"}`,
    ),
    providerCard(
      "Identity provider",
      "active",
      user.auth_provider || "local_dev",
      user.last_login ? `Last login: ${formatDate(user.last_login)}` : "No login timestamp",
    ),
  ].join("");
}

function renderAuthReadinessSettings() {
  const target = $("#authReadinessCards");
  if (!target) return;
  const readiness = state.authReadiness;
  if (!readiness) {
    target.innerHTML = `<div class="empty-state">Authentication readiness is not available.</div>`;
    return;
  }
  target.innerHTML = [
    providerCard(
      "App login mode",
      readiness.auth_mode === "microsoft" ? "configured" : "active",
      readiness.auth_mode || "dev",
      readiness.require_login ? "Login required when enforcement is enabled." : "Demo-friendly: login is not required.",
    ),
    providerCard(
      "Microsoft identity readiness",
      readiness.microsoft_login_ready ? "configured" : "warn",
      readiness.microsoft_login_ready ? "Ready for Microsoft app login design." : "Not ready for enforced Microsoft login.",
      `Client: ${readiness.microsoft_client_configured ? "configured" : "missing"} · Tenant: ${readiness.tenant_configured ? "configured" : "missing"}`,
    ),
    providerCard(
      "Redirect URI",
      "active",
      readiness.redirect_uri || "Not configured",
      "This is separate from the future ResearchOS app-login redirect design.",
    ),
    providerCard(
      "Production warnings",
      readiness.warnings?.length ? "warn" : "configured",
      readiness.warnings?.length ? `${readiness.warnings.length} warning(s)` : "No readiness warnings.",
      (readiness.warnings || []).join(" · ") || "Local demo defaults are active.",
    ),
  ].join("");
}

function renderAgentSettings() {
  const target = $("#agentCards");
  if (!target) return;
  const status = state.agentStatus;
  if (!status) {
    target.innerHTML = `<div class="empty-state">Agent status is not available.</div>`;
    return;
  }
  target.innerHTML = (status.agents || []).length
    ? status.agents.map(renderAgentCard).join("")
    : `<div class="empty-state">No scientific agents are registered.</div>`;
}

function renderAgentCard(agent) {
  return `
    <article class="provider-card">
      <div class="provider-card-header">
        <span>${escapeHtml(agent.name)}</span>
        <strong class="status-pill ${agent.enabled ? "ok" : "warn"}">${agent.enabled ? "Enabled" : "Disabled"}</strong>
      </div>
      <p>${escapeHtml(agent.description)}</p>
      <small>${escapeHtml(agent.run_count)} runs · ${escapeHtml(agent.error_count)} errors · last: ${escapeHtml(agent.last_run || "never")}</small>
      ${agent.last_error ? `<p class="privacy-note">${escapeHtml(agent.last_error)}</p>` : ""}
      <div class="meta">${(agent.event_types || []).slice(0, 5).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}</div>
      <div class="entry-actions">
        <button type="button" class="secondary-button agent-toggle" data-agent-id="${escapeHtml(agent.agent_id)}" data-agent-action="${agent.enabled ? "disable" : "enable"}">
          ${agent.enabled ? "Disable" : "Enable"}
        </button>
      </div>
    </article>
  `;
}

function renderOneNoteReadinessSettings() {
  const readiness = state.oneNoteReadiness;
  const cards = $("#oneNoteReadinessCards");
  const copy = $("#oneNoteReadinessCopy");
  if (!cards || !copy) return;
  if (!readiness) {
    cards.innerHTML = `<div class="empty-state">OneNote readiness status is not available.</div>`;
    copy.textContent = "OneNote readiness status is not available.";
    return;
  }

  const readOnlyStatus = readiness.read_only_sync_ready ? "available" : "warn";
  const redirectStatus = readiness.redirect_uri_compatible ? "configured" : "warn";
  const clientStatus = readiness.microsoft_client_id_configured ? "configured" : "not_configured";
  const permissionStatus = readiness.missing_required_scopes.length ? "warn" : "configured";

  cards.innerHTML = [
    providerCard(
      "OneNote Readiness",
      readOnlyStatus,
      readiness.read_only_sync_message,
      readiness.ucsd_approval_message,
    ),
    providerCard(
      "Azure app",
      clientStatus,
      readiness.microsoft_client_id_configured ? "Microsoft client ID is configured." : "Microsoft client ID is not configured.",
      readiness.tenant_configured ? "Tenant configured" : "Tenant missing",
    ),
    providerCard(
      "Current redirect URI",
      redirectStatus,
      readiness.current_redirect_uri || "Not configured",
      readiness.redirect_uri_message,
    ),
    providerCard(
      "Required Azure redirect URI",
      redirectStatus,
      readiness.required_azure_redirect_uri,
      "Register this exact callback URI in Microsoft Entra.",
    ),
    providerCard(
      "Delegated permissions",
      permissionStatus,
      readiness.required_scopes.join(", "),
      readiness.missing_required_scopes.length
        ? `Missing from GRAPH_SCOPES: ${readiness.missing_required_scopes.join(", ")}`
        : "Configured scopes include the read-only MVP permissions.",
    ),
    providerCard(
      "Future write-back",
      "warn",
      readiness.write_back_message,
      "Current MVP remains read-only.",
    ),
  ].join("");

  copy.textContent = `Read-only MVP uses delegated ${readiness.required_scopes.join(", ")}. Future OneNote write-back remains disabled and would require separate Notes.Create or Notes.ReadWrite approval.`;
}

function renderDeploymentSettings() {
  const deployment = state.deploymentStatus;
  const cards = $("#deploymentCards");
  const mobileCopy = $("#mobileAccessCopy");
  if (!cards || !mobileCopy) return;
  if (!deployment) {
    cards.innerHTML = `<div class="empty-state">Deployment status is not available.</div>`;
    mobileCopy.textContent = "Deployment status is not available.";
    return;
  }

  cards.innerHTML = [
    providerCard(
      "Deployment mode",
      deployment.mode === "lab_server" ? "active" : "warn",
      deployment.mode === "lab_server" ? "Lab server mode is configured." : "Local development mode.",
      `Bind ${deployment.host}:${deployment.port}`,
    ),
    providerCard(
      "Server URL",
      deployment.public_base_url_configured ? "configured" : "warn",
      deployment.server_url,
      deployment.https_enabled ? "HTTPS enabled" : "HTTPS disabled",
    ),
    providerCard(
      "Data directory",
      "active",
      deployment.data_dir,
      "Local-first ResearchOS state",
    ),
    providerCard(
      "OneNote redirect",
      deployment.microsoft_redirect_uri?.startsWith(deployment.public_base_url || "") && deployment.public_base_url ? "configured" : "warn",
      deployment.microsoft_redirect_uri || "Not configured",
      "Must match the deployed callback URL",
    ),
  ].join("");

  const warningText = (deployment.warnings || []).length
    ? `Warnings: ${deployment.warnings.join(" ")}`
    : "Deployment status looks ready for shared lab access.";
  mobileCopy.textContent = `Open ${deployment.mobile_pwa_url} from phones, tablets, or laptops on the same reachable network. Use HTTPS for installable PWA behavior and OneNote auth. ${warningText}`;
}

function renderEntryTemplates() {
  const select = $("#entryTemplateSelect");
  if (!select) return;
  select.innerHTML = state.entryTemplates.length
    ? state.entryTemplates
        .map((template) => `<option value="${escapeHtml(template.id)}">${escapeHtml(template.name)}</option>`)
        .join("")
    : `<option value="general_experiment">General experiment</option>`;
  if (!select.value) {
    select.value = "retinal_organoid";
  }
}

function renderExperimentsTable() {
  state.selectedExperimentIds = new Set(
    [...state.selectedExperimentIds].filter((id) => state.experiments.some((experiment) => experiment.id === id)),
  );
  $("#experimentsTable").innerHTML = state.experiments.length
    ? state.experiments
        .map(
          (experiment) => `
            <tr>
              <td>
                <input
                  class="experiment-select"
                  type="checkbox"
                  value="${escapeHtml(experiment.id)}"
                  ${state.selectedExperimentIds.has(experiment.id) ? "checked" : ""}
                  aria-label="Select ${escapeHtml(experiment.title)}"
                />
              </td>
              <td><a href="#/experiments/${encodeURIComponent(experiment.id)}">${escapeHtml(experiment.experiment_id || experiment.id)}</a></td>
              <td>${escapeHtml(formatDate(experiment.date))}</td>
              <td>${escapeHtml(experiment.title)}</td>
              <td>${(experiment.compounds || []).map((value) => graphChip("compounds", value)).join("")}</td>
              <td>${(experiment.markers || []).map((value) => graphChip("markers", value)).join("")}</td>
              <td>${escapeHtml(experiment.source_provider)}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="7">No experiments available.</td></tr>`;

  $$(".experiment-select").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const input = event.target;
      if (input.checked) {
        state.selectedExperimentIds.add(input.value);
      } else {
        state.selectedExperimentIds.delete(input.value);
      }
      $("#comparisonStatus").textContent = `${state.selectedExperimentIds.size} experiment${state.selectedExperimentIds.size === 1 ? "" : "s"} selected.`;
    });
  });
}

function renderComparison(comparison) {
  const panel = $("#comparisonPanel");
  const fieldRows = Object.entries(comparison.differences || {})
    .map(
      ([field, values]) => `
        <tr>
          <th>${escapeHtml(field.replaceAll("_", " "))}</th>
          <td>${Object.entries(values)
            .map(([experimentId, value]) => `<div><strong>${escapeHtml(shortExperimentLabel(experimentId))}</strong>: ${escapeHtml(formatComparisonValue(value))}</div>`)
            .join("")}</td>
        </tr>
      `,
    )
    .join("");

  panel.hidden = false;
  panel.innerHTML = `
    <div class="panel-heading">
      <div>
        <p class="eyebrow">Comparison</p>
        <h2>Selected Experiments</h2>
      </div>
      <span class="status-pill ${comparison.ai_used ? "ok" : ""}">${escapeHtml(comparison.provider)}</span>
    </div>
    <section class="detail-section">
      <h3>Likely scientific interpretation</h3>
      <p>${escapeHtml(comparison.likely_scientific_interpretation)}</p>
    </section>
    <section class="detail-section">
      <h3>Shared features</h3>
      <div class="tag-row">
        ${Object.entries(comparison.shared_features || {}).length
          ? Object.entries(comparison.shared_features)
              .map(([field, value]) => `<span class="tag">${escapeHtml(field)}: ${escapeHtml(formatComparisonValue(value))}</span>`)
              .join("")
          : `<span class="muted">No shared structured fields detected.</span>`}
      </div>
    </section>
    <section class="detail-section">
      <h3>Differences</h3>
      <div class="table-wrap">
        <table class="comparison-table">
          <tbody>${fieldRows || `<tr><td>No structured differences detected.</td></tr>`}</tbody>
        </table>
      </div>
    </section>
    <section class="detail-section">
      <h3>Limitations</h3>
      <p>${escapeHtml((comparison.limitations || []).join(" "))}</p>
    </section>
  `;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function shortExperimentLabel(experimentId) {
  const experiment = state.experiments.find((item) => item.id === experimentId);
  return experiment?.experiment_id || experiment?.title || experimentId;
}

function formatComparisonValue(value) {
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  if (value === null || value === undefined || value === "") return "not captured";
  return String(value);
}

function renderEntryDraft(payload) {
  const structured = payload.structured || {};
  state.currentEntryDraft = payload;
  if (payload.id) {
    state.currentSavedEntryId = payload.id;
  }
  const fields = [
    ["Title", structured.title],
    ["Experiment ID", structured.experiment_id],
    ["Objective", structured.objective],
    ["Date", structured.date],
    ["Researcher", structured.researcher],
    ["Cell line", structured.cell_line],
    ["Organoid batch", structured.organoid_batch],
    ["Differentiation day", structured.differentiation_day],
    ["Conditions", structured.conditions],
    ["Treatment schedule", structured.treatment_schedule],
    ["Reagents / concentrations", structured.reagents_concentrations],
    ["Controls", structured.controls],
    ["Planned readouts", structured.planned_readouts],
    ["Observations", structured.observations],
    ["Issues / deviations", structured.issues_deviations],
    ["Next steps", structured.next_steps],
  ];

  $("#entryStructuredPreview").innerHTML = fields
    .map(([label, value]) => detailField(label, formatComparisonValue(value)))
    .join("");
  $("#entryMarkdownPreview").textContent = payload.markdown || "No Markdown generated.";
  $("#oneNoteEntryPreview").hidden = true;
  $("#oneNoteEntryPreview").innerHTML = "";
  $("#entryExportStatus").textContent = "";
  $("#entryDraftStatus").textContent = `Confidence ${Math.round((payload.confidence || 0) * 100)}% · ${payload.provider}`;
  $("#entryDraftStatus").className = `status-pill ${(payload.confidence || 0) >= 0.55 ? "ok" : ""}`;

  if ((payload.missing_fields || []).length) {
    $("#entryStructuredPreview").insertAdjacentHTML(
      "beforeend",
      detailField("Missing fields", payload.missing_fields.join(", ")),
    );
  }
}

function pendingEntryPayload(status = "draft") {
  const draft = state.currentEntryDraft;
  const structured = draft?.structured || {};
  const markdown = currentDraftMarkdown();
  if (!draft || !markdown) {
    throw new Error("Generate or open a draft before saving.");
  }
  return {
    id: state.currentSavedEntryId || draft.id || null,
    title: structured.title || "Untitled notebook draft",
    experiment_id: structured.experiment_id || null,
    template: draft.template || structured.template || $("#entryTemplateSelect").value || "general_experiment",
    structured,
    markdown,
    status,
  };
}

function savedEntryToDraft(entry) {
  return {
    id: entry.id,
    structured: entry.structured || {},
    markdown: entry.markdown,
    template: entry.template,
    confidence: 1,
    missing_fields: [],
    ai_used: false,
    provider: `saved-${entry.status}`,
  };
}

function renderSavedDrafts() {
  const target = $("#savedDraftsList");
  if (!target) return;
  target.innerHTML = state.pendingEntries.length
    ? state.pendingEntries
        .map((entry) => `
          <article class="record-card saved-draft-card">
            <div>
              <h3>${escapeHtml(entry.title)}</h3>
              <p>${escapeHtml(entry.experiment_id || "No experiment ID")} · ${escapeHtml(entry.template)} · ${escapeHtml(entry.status)}</p>
              <div class="meta">
                <span class="tag">updated ${escapeHtml(formatDate(entry.updated_at))}</span>
              </div>
            </div>
            <div class="entry-actions">
              <a class="secondary-link-button" href="#/saved-drafts/${encodeURIComponent(entry.id)}">Open</a>
              <button type="button" class="secondary-button delete-saved-draft" data-entry-id="${escapeHtml(entry.id)}">Delete</button>
            </div>
          </article>
        `)
        .join("")
    : `<div class="empty-state">No pending notebook entries saved yet.</div>`;

  $$(".delete-saved-draft").forEach((button) => {
    button.addEventListener("click", () => {
      deleteSavedDraft(button.dataset.entryId).catch((error) => {
        target.innerHTML = `<div class="empty-state">Could not delete draft: ${escapeHtml(error.message)}</div>`;
      });
    });
  });
}

function currentDraftMarkdown() {
  const markdown = state.currentEntryDraft?.markdown || $("#entryMarkdownPreview").textContent || "";
  return markdown.includes("Generate a structured entry") ? "" : markdown.trim();
}

function entryFilename() {
  const title = state.currentEntryDraft?.structured?.title || "researchos-entry";
  return `${String(title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "researchos-entry"}.md`;
}

async function copyEntryMarkdown() {
  const markdown = currentDraftMarkdown();
  if (!markdown) {
    $("#entryExportStatus").textContent = "Generate a draft before copying Markdown.";
    return;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(markdown);
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = markdown;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  $("#entryExportStatus").textContent = "Markdown copied locally. OneNote write-back was not used.";
}

async function downloadEntryMarkdown() {
  const markdown = currentDraftMarkdown();
  if (!markdown) {
    $("#entryExportStatus").textContent = "Generate a draft before downloading Markdown.";
    return;
  }
  const payload = await requestJson("/entries/export-markdown", {
    method: "POST",
    body: JSON.stringify({ markdown, filename: entryFilename() }),
  });
  const blob = new Blob([payload.content], { type: payload.content_type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = payload.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  $("#entryExportStatus").textContent = `Downloaded ${payload.filename}. OneNote write-back was not used.`;
}

async function saveCurrentDraft(status = "draft") {
  const payload = await requestJson("/entries/save-draft", {
    method: "POST",
    body: JSON.stringify(pendingEntryPayload(status)),
  });
  state.currentSavedEntryId = payload.id;
  state.currentEntryDraft = savedEntryToDraft(payload);
  await refreshData();
  $("#entryExportStatus").textContent = status === "ready_for_onenote"
    ? "Draft marked ready for OneNote inside ResearchOS. OneNote write-back is still disabled."
    : "Draft saved inside ResearchOS.";
  recordActivity("Saved notebook draft", `${payload.title} · ${payload.status}`);
}

async function openSavedDraft(entryId) {
  const entry = await requestJson(`/entries/${encodeURIComponent(entryId)}`);
  state.currentSavedEntryId = entry.id;
  const draft = savedEntryToDraft(entry);
  renderEntryDraft(draft);
  $("#entryTemplateSelect").value = entry.template;
  $("#entryDictation").value = "";
  $("#entryExportStatus").textContent = `Opened saved draft: ${entry.status}.`;
  window.location.hash = "#/new-experiment";
}

async function copySavedDraftMarkdown(entryId) {
  const payload = await requestJson(`/entries/${encodeURIComponent(entryId)}/markdown`);
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(payload.content);
  } else {
    const textarea = document.createElement("textarea");
    textarea.value = payload.content;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  $("#savedDraftActionStatus").textContent = "Markdown copied locally. OneNote write-back was not used.";
}

function downloadSavedDraftMarkdown(entryId) {
  window.location.href = `/entries/${encodeURIComponent(entryId)}/download`;
}

async function markSavedDraftReady(entryId) {
  const entry = await requestJson(`/entries/${encodeURIComponent(entryId)}`);
  const payload = await requestJson("/entries/save-draft", {
    method: "POST",
    body: JSON.stringify({
      id: entry.id,
      title: entry.title,
      experiment_id: entry.experiment_id,
      template: entry.template,
      structured: entry.structured,
      markdown: entry.markdown,
      status: "ready_for_onenote",
    }),
  });
  state.currentSavedEntryId = payload.id;
  await refreshData();
  $("#savedDraftActionStatus").textContent = "Draft marked ready for OneNote. Save to OneNote remains disabled pending approval.";
}

async function deleteSavedDraft(entryId) {
  await requestJson(`/entries/${encodeURIComponent(entryId)}`, { method: "DELETE" });
  if (state.currentSavedEntryId === entryId) {
    state.currentSavedEntryId = null;
  }
  await refreshData();
  recordActivity("Deleted notebook draft", entryId);
}

async function renderSavedDraftDetail(entryId) {
  const target = $("#savedDraftDetail");
  target.innerHTML = `<div class="empty-state">Loading saved draft...</div>`;
  try {
    const entry = await requestJson(`/entries/${encodeURIComponent(entryId)}`);
    target.innerHTML = `
      <a class="inline-link" href="#/saved-drafts">Back to saved drafts</a>
      <div class="detail-header">
        <div>
          <p class="eyebrow">${escapeHtml(entry.status)}</p>
          <h2>${escapeHtml(entry.title)}</h2>
        </div>
        <span class="status-pill ${entry.status === "ready_for_onenote" ? "ok" : ""}">${escapeHtml(entry.status)}</span>
      </div>
      <div class="detail-grid">
        ${detailField("Experiment ID", entry.experiment_id)}
        ${detailField("Template", entry.template)}
        ${detailField("Created", formatDate(entry.created_at))}
        ${detailField("Updated", formatDate(entry.updated_at))}
      </div>
      <div class="entry-actions preview-actions">
        <button type="button" id="copySavedMarkdownButton" class="secondary-button">Copy Markdown</button>
        <button type="button" id="downloadSavedMarkdownButton" class="secondary-button">Download Markdown</button>
        <button type="button" id="markSavedReadyButton" class="secondary-button">Mark Ready for OneNote</button>
        <button type="button" disabled>Save to OneNote</button>
      </div>
      <p class="privacy-note">OneNote write-back is pending UCSD IT approval. This draft is stored locally in ResearchOS and can be copied or downloaded as Markdown.</p>
      <p class="demo-status" id="savedDraftActionStatus"></p>
      <pre class="markdown-preview">${escapeHtml(entry.markdown)}</pre>
    `;
    $("#copySavedMarkdownButton").addEventListener("click", () => {
      copySavedDraftMarkdown(entry.id).catch((error) => {
        $("#savedDraftActionStatus").textContent = `Copy failed: ${error.message}`;
      });
    });
    $("#downloadSavedMarkdownButton").addEventListener("click", () => {
      downloadSavedDraftMarkdown(entry.id);
    });
    $("#markSavedReadyButton").addEventListener("click", () => {
      markSavedDraftReady(entry.id).catch((error) => {
        $("#savedDraftActionStatus").textContent = `Status update failed: ${error.message}`;
      });
    });
  } catch (error) {
    target.innerHTML = `<div class="empty-state">Saved draft unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

function markdownToPreviewHtml(markdown) {
  return markdown
    .split("\n")
    .map((line) => {
      if (line.startsWith("# ")) return `<h1>${escapeHtml(line.slice(2))}</h1>`;
      if (line.startsWith("## ")) return `<h2>${escapeHtml(line.slice(3))}</h2>`;
      if (line.startsWith("- ")) return `<li>${escapeHtml(line.slice(2))}</li>`;
      if (!line.trim()) return "";
      return `<p>${escapeHtml(line)}</p>`;
    })
    .join("");
}

function previewOneNoteEntry() {
  const markdown = currentDraftMarkdown();
  if (!markdown) {
    $("#entryExportStatus").textContent = "Generate a draft before previewing the OneNote entry.";
    return;
  }
  const preview = $("#oneNoteEntryPreview");
  preview.hidden = false;
  preview.innerHTML = `
    <div class="provider-card-header">
      <span>OneNote entry preview</span>
      <strong class="status-pill">Write-back disabled</strong>
    </div>
    <p class="card-copy">This preview shows what would be reviewed before a future OneNote create/write workflow. No OneNote API call was made.</p>
    <div class="onenote-page-preview">${markdownToPreviewHtml(markdown)}</div>
  `;
  $("#entryExportStatus").textContent = "Preview generated locally. Saving to OneNote still requires UCSD approval.";
}

let speechRecognition = null;
let speechListening = false;
let speechFinalTranscript = "";

function setVoiceStatus(message, isActive = false) {
  const status = $("#voiceDictationStatus");
  if (!status) return;
  status.textContent = message;
  status.className = `status-pill ${isActive ? "ok" : ""}`;
}

function appendDictationText(text) {
  const textarea = $("#entryDictation");
  const cleaned = String(text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return;
  const prefix = textarea.value.trim() ? `${textarea.value.trim()} ` : "";
  textarea.value = `${prefix}${cleaned}`.trim();
}

function setupVoiceDictation() {
  const button = $("#voiceDictationButton");
  if (!button) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    button.disabled = true;
    setVoiceStatus("Speech recognition unavailable");
    return;
  }

  speechRecognition = new SpeechRecognition();
  speechRecognition.continuous = true;
  speechRecognition.interimResults = true;
  speechRecognition.lang = navigator.language || "en-US";

  speechRecognition.addEventListener("start", () => {
    speechListening = true;
    speechFinalTranscript = "";
    button.textContent = "Stop microphone";
    setVoiceStatus("Listening...", true);
  });

  speechRecognition.addEventListener("result", (event) => {
    let interimTranscript = "";
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const transcript = event.results[index][0]?.transcript || "";
      if (event.results[index].isFinal) {
        speechFinalTranscript += ` ${transcript}`;
      } else {
        interimTranscript += ` ${transcript}`;
      }
    }
    setVoiceStatus(interimTranscript.trim() ? `Listening... ${shortText(interimTranscript, 60)}` : "Listening...", true);
  });

  speechRecognition.addEventListener("end", () => {
    speechListening = false;
    button.textContent = "Start microphone";
    appendDictationText(speechFinalTranscript);
    speechFinalTranscript = "";
    setVoiceStatus("Stopped");
  });

  speechRecognition.addEventListener("error", () => {
    speechListening = false;
    button.textContent = "Start microphone";
    setVoiceStatus("Stopped");
  });

  button.addEventListener("click", () => {
    if (!speechRecognition) return;
    if (speechListening) {
      speechRecognition.stop();
      return;
    }
    try {
      speechRecognition.start();
    } catch (error) {
      setVoiceStatus("Stopped");
    }
  });
}

async function generateEntryDraft() {
  const notes = $("#entryDictation").value.trim();
  const template = $("#entryTemplateSelect").value || "general_experiment";
  if (!notes) {
    $("#entryDraftStatus").textContent = "Enter dictation first";
    return;
  }
  $("#entryDraftStatus").textContent = "Generating draft...";
  const payload = await requestJson("/entries/draft", {
    method: "POST",
    body: JSON.stringify({ dictation: notes, template }),
  });
  state.currentSavedEntryId = null;
  renderEntryDraft(payload);
}

async function compareSelectedExperiments() {
  const ids = [...state.selectedExperimentIds];
  if (ids.length < 2) {
    $("#comparisonStatus").textContent = "Select at least two experiments to compare.";
    return;
  }
  $("#comparisonStatus").textContent = "Comparing selected experiments...";
  const comparison = await requestJson("/experiments/compare", {
    method: "POST",
    body: JSON.stringify({ experiment_ids: ids }),
  });
  $("#comparisonStatus").textContent = `Compared ${ids.length} experiments.`;
  renderComparison(comparison);
}

function renderExperimentDetail(experimentId) {
  const experiment = state.experiments.find((item) => item.id === experimentId);
  if (!experiment) {
    $("#experimentDetail").innerHTML = `<div class="empty-state">Experiment not found.</div>`;
    return;
  }
  const source = pathForDocument(experiment.source_document_id);
  const imageAssets = (experiment.linked_assets || []).filter(
    (asset) => asset.provider === "microscopy" || ["image", "microscopy"].includes(asset.asset_type),
  );
  $("#experimentDetail").innerHTML = `
    <a class="inline-link" href="#/experiments">Back to experiments</a>
    <div class="detail-header">
      <div>
        <p class="eyebrow">${escapeHtml(experiment.experiment_id || experiment.id)}</p>
        <h2>${escapeHtml(experiment.title)}</h2>
      </div>
      <div class="prompt-row">
        <a class="status-pill ok" href="#/experiments/${encodeURIComponent(experiment.id)}/workspace">Open workspace</a>
        <a class="status-pill ok" href="${graphEntityLink("experiments", experiment.id)}">Open graph</a>
      </div>
    </div>
    <div class="tab-row" role="tablist" aria-label="Experiment detail tabs">
      <button type="button" class="tab-button active" data-experiment-tab="overview">Overview</button>
      <button type="button" class="tab-button" data-experiment-tab="timeline">Timeline</button>
    </div>
    <section id="experimentOverviewTab">
      <div class="detail-grid">
        ${detailField("Date", formatDate(experiment.date))}
        ${detailField("Researcher", experiment.researcher)}
        ${detailField("Cell line", experiment.cell_line)}
        ${detailField("Organoid batch", experiment.organoid_batch)}
        ${detailField("Original document", source?.source_path || source?.source_id || experiment.source_document_id)}
      </div>
      ${linkedSection("Linked assets", experiment.linked_assets || [], (asset) => `
        <a class="item-link" href="#/assets/${encodeURIComponent(asset.asset_id)}">
          <strong>${escapeHtml(asset.title)}</strong>
          <span>${escapeHtml(asset.asset_type)} · ${escapeHtml(asset.filename)} · ${escapeHtml(asset.provider)}</span>
        </a>
      `)}
      ${linkedSection("Linked statistics assets", (experiment.linked_assets || []).filter((asset) => asset.metadata?.statistics), (asset) => `
        <a class="item-link" href="#/assets/${encodeURIComponent(asset.asset_id)}">
          <strong>${escapeHtml(asset.title)}</strong>
          <span>${escapeHtml((asset.metadata?.statistics?.variables || []).join(", "))} · ${escapeHtml((asset.metadata?.statistics?.statistical_tests || []).join(", "))}</span>
        </a>
      `)}
      ${linkedSection("Images", imageAssets, renderImageAssetCard)}
      ${tagSection("Compounds", experiment.compounds, "compounds")}
      ${tagSection("Markers", experiment.markers, "markers")}
      ${tagSection("Time points", experiment.time_points)}
      ${textSection("Notes", experiment.notes)}
      ${textSection("Conclusions", experiment.conclusions)}
    </section>
    <section id="experimentTimelineTab" hidden>
      <div class="timeline experiment-timeline" id="experimentTimeline">
        <div class="empty-state">Loading experiment timeline...</div>
      </div>
    </section>
  `;
  bindExperimentDetailTabs();
  loadExperimentTimeline(experiment.id);
}

async function renderExperimentWorkspace(experimentId) {
  const target = $("#experimentDetail");
  target.innerHTML = `<div class="empty-state">Loading experiment workspace...</div>`;
  try {
    const workspace = await requestJson(`/experiments/${encodeURIComponent(experimentId)}/workspace?use_ai=false`);
    const experiment = workspace.experiment || {};
    const methodsMaterials = await requestJson(`/experiments/${encodeURIComponent(experimentId)}/methods-materials`);
    const summary = workspace.ai_summary || {};
    target.innerHTML = `
      <a class="inline-link" href="#/experiments/${encodeURIComponent(experiment.id || experimentId)}">Back to experiment detail</a>
      <div class="detail-header">
        <div>
          <p class="eyebrow">${escapeHtml(experiment.experiment_id || experiment.id || experimentId)}</p>
          <h2>${escapeHtml(experiment.title || "Experiment Workspace")}</h2>
        </div>
        <span class="status-pill ok">Workspace</span>
      </div>
      <section class="detail-section">
        <h3>AI Summary</h3>
        <p>${escapeHtml(summary.text || "No workspace summary available.")}</p>
        <div class="meta"><span class="tag">${escapeHtml(summary.provider || "local-fallback")}</span></div>
      </section>
      ${renderResearchCopilotCard(workspace.research_copilot)}
      ${renderWorkflowCard(workspace.workflow || workspace.lifecycle)}
      <div class="detail-grid">
        ${detailField("Date", formatDate(experiment.date))}
        ${detailField("Researcher", experiment.researcher)}
        ${detailField("Cell line", experiment.cell_line)}
        ${detailField("Organoid batch", experiment.organoid_batch)}
      </div>
      ${tagSection("Compounds", workspace.compounds || [], "compounds")}
      ${tagSection("Markers", workspace.markers || [], "markers")}
      ${tagSection("Genes", workspace.genes || [], "genes")}
      ${renderMethodsMaterialsSection(experiment.id || experimentId, methodsMaterials)}
      ${workspaceSection("Reagents Used", methodsMaterials.inventory_usage || [], renderInventoryUsageRecord)}
      ${workspaceSection("Scientific Memory", workspace.scientific_memory?.most_similar_experiments || [], renderMemorySimilarity)}
      ${workspaceSection("Timeline", workspace.timeline?.events || [], renderWorkspaceTimelineEvent)}
      ${workspaceSection("Microscopy / Images", workspace.microscopy || [], renderImageAssetCard)}
      ${workspaceSection("GraphPad Analyses", workspace.graphpad || [], renderWorkspaceAsset)}
      ${workspaceSection("Spreadsheets", workspace.spreadsheets || [], renderWorkspaceSpreadsheet)}
      ${workspaceSection("Statistics", workspace.statistics || [], renderWorkspaceStatistic)}
      ${workspaceSection("Literature", workspace.literature || [], renderWorkspaceDocument)}
      ${workspaceSection("Connected Experiments", workspace.related_experiments || [], renderWorkspaceExperiment)}
      ${workspaceSection("Related Entities", workspace.related_entities || [], renderWorkspaceEntity)}
      ${workspaceSection("Files", workspace.sections?.files || [], renderWorkspaceFile)}
      <section class="detail-section">
        <h3>Conclusions</h3>
        <h4>Observed</h4>
        <ul>${listItems(workspace.conclusions?.observed || [])}</ul>
        <h4>Inferred</h4>
        <ul>${listItems(workspace.conclusions?.inferred || [])}</ul>
        <h4>Referenced from literature</h4>
        <ul>${listItems(workspace.conclusions?.referenced_from_literature || [])}</ul>
      </section>
      <section class="detail-section">
        <h3>Limitations</h3>
        <ul>${listItems(workspace.limitations || [])}</ul>
      </section>
      ${workspaceSection("Provenance", workspace.provenance || [], renderWorkspaceProvenance)}
    `;
  } catch (error) {
    target.innerHTML = `<div class="empty-state">Experiment workspace unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

function renderWorkflowCard(workflow) {
  if (!workflow) return "";
  const stage = workflow.stage || {};
  const progress = workflow.progress || {};
  return `
    <section class="detail-section">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Experiment Workflow</p>
          <h3>${escapeHtml(workflow.current_stage || "Planning")}</h3>
        </div>
        <span class="status-pill ok">${escapeHtml((stage.allowed_transitions || workflow.allowed_transitions || []).join(" / ") || "No transitions")}</span>
      </div>
      <div class="workflow-progress" aria-label="Workflow progress">
        <span style="width:${Number(progress.percent || 0)}%"></span>
      </div>
      <p>${escapeHtml(stage.description || "Workflow stage context is available locally.")}</p>
      <h4>Recommended next actions</h4>
      <ul>${listItems(workflow.recommended_next_actions || workflow.suggested_next_actions || [])}</ul>
      <h4>Blocking issues</h4>
      <ul>${listItems(workflow.blocking_issues || [])}</ul>
      <h4>Completion criteria</h4>
      <ul>${listItems(stage.completion_criteria || workflow.completion_criteria || [])}</ul>
      <h4>Workflow history</h4>
      <ul>${listItems((workflow.history || []).slice(-4).map((item) => `${item.from_stage || "Start"} -> ${item.to_stage}`))}</ul>
      <div class="meta">${(workflow.remaining_stages || []).slice(0, 8).map((name) => `<span class="tag">${escapeHtml(name)}</span>`).join("")}</div>
    </section>
  `;
}

function renderMethodsMaterialsSection(experimentId, payload) {
  const warnings = payload?.warnings || [];
  const entries = payload?.entries || [];
  return `
    <section class="detail-section" id="methodsMaterialsSection">
      <div class="panel-heading compact-heading">
        <div>
          <p class="eyebrow">Manuscript support</p>
          <h3>Materials & Reagents</h3>
        </div>
        <button type="button" class="secondary-button" data-generate-methods="${escapeHtml(experimentId)}">Generate Methods Text</button>
      </div>
      <p class="card-copy" id="methodsMaterialsText">${escapeHtml(payload?.text || "No reagent inventory items are linked to this experiment yet.")}</p>
      ${warnings.length ? `<div class="empty-state">${warnings.map((warning) => escapeHtml(warning)).join("<br>")}</div>` : ""}
      ${entries.length ? `<div class="meta">${entries.map((entry) => `<span class="tag">${escapeHtml(entry.name || entry.item_id)}</span>`).join("")}</div>` : ""}
    </section>
  `;
}

function renderInventoryUsageRecord(record) {
  return `
    <article class="timeline-item">
      <div class="timeline-item-header">${timelineBadge("reagent_used")}<strong>${escapeHtml(record.inventory_item_name || record.inventory_item_id)}</strong></div>
      <span>${escapeHtml(record.date_used || record.created_at)} · ${escapeHtml(record.amount_used ?? "amount not recorded")} ${escapeHtml(record.units || "")}</span>
      <p>${escapeHtml(record.purpose || record.notes || "Inventory usage recorded.")}</p>
    </article>
  `;
}

function renderWorkflows() {
  const target = $("#workflowCards");
  if (!target) return;
  target.innerHTML = state.workflows.length
    ? state.workflows.map(renderWorkflowCardSummary).join("")
    : `<div class="empty-state">No experiment workflows available. Load demo notes or extract experiments first.</div>`;
}

function renderWorkflowCardSummary(workflow) {
  const experiment = workflow.subject || {};
  const progress = workflow.progress || {};
  return `
    <article class="provider-card">
      <div class="provider-card-header">
        <span>${escapeHtml(experiment.experiment_id || experiment.title || workflow.subject_id)}</span>
        <strong class="status-pill ok">${escapeHtml(workflow.current_stage)}</strong>
      </div>
      <div class="workflow-progress"><span style="width:${Number(progress.percent || 0)}%"></span></div>
      <p>${escapeHtml((workflow.suggested_next_actions || [])[0] || "Workflow is ready for review.")}</p>
      <div class="meta">
        ${(workflow.blocking_issues || []).slice(0, 3).map((issue) => `<span class="tag">${escapeHtml(issue)}</span>`).join("")}
      </div>
      <div class="entry-actions">
        <a class="secondary-link-button" href="#/experiments/${encodeURIComponent(experiment.id || workflow.subject_id)}/workspace">Open Workspace</a>
      </div>
    </article>
  `;
}

function renderResearchCopilotCard(copilot) {
  if (!copilot || !copilot.sections) {
    return `
      <section class="detail-section">
        <h3>Research Copilot</h3>
        <div class="empty-state">Research Copilot synthesis is not available for this workspace.</div>
      </section>
    `;
  }

  const labels = {
    key_findings: "Key findings",
    potential_concerns: "Potential concerns",
    suggested_follow_up_experiments: "Suggested follow-up experiments",
    related_experiments: "Related experiments",
    related_literature: "Related literature",
    experimental_gaps: "Experimental gaps",
    potential_manuscript_statements: "Potential manuscript statements",
    grant_proposal_ideas: "Grant proposal ideas",
    questions_worth_investigating: "Questions worth investigating",
  };

  return `
    <section class="detail-section copilot-card">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">Workspace synthesis</p>
          <h3>Research Copilot</h3>
        </div>
        <span class="status-pill ok">${escapeHtml(copilot.provider || "local-fallback")}</span>
      </div>
      <p>${escapeHtml(copilot.natural_summary || "Copilot summary unavailable.")}</p>
      <div class="source-list">
        ${Object.entries(labels).map(([key, label]) => renderCopilotSection(label, copilot.sections[key] || [])).join("")}
      </div>
    </section>
  `;
}

function renderCopilotSection(title, statements) {
  return `
    <details class="result" open>
      <summary><h3>${escapeHtml(title)}</h3></summary>
      ${statements.length ? statements.map(renderCopilotStatement).join("") : `<div class="empty-state">No ${escapeHtml(title.toLowerCase())} available.</div>`}
    </details>
  `;
}

function renderCopilotStatement(statement) {
  const provenance = Array.isArray(statement.provenance) ? statement.provenance : [];
  return `
    <article class="copilot-statement">
      <div class="meta"><span class="tag">${escapeHtml(statement.category || "inferred")}</span></div>
      <p>${escapeHtml(statement.text || "")}</p>
      <small>${escapeHtml(
        provenance
          .map((item) => [item.fact, item.source, item.provider, item.document, item.asset].filter(Boolean).join(" · "))
          .filter(Boolean)
          .join(" | ") || "ResearchOS workspace provenance",
      )}</small>
    </article>
  `;
}

function workspaceSection(title, items, renderer) {
  return `
    <details class="detail-section" open>
      <summary><h3>${escapeHtml(title)}</h3></summary>
      ${items.length ? `<div class="source-list">${items.map(renderer).join("")}</div>` : `<div class="empty-state">No ${escapeHtml(title.toLowerCase())} linked.</div>`}
    </details>
  `;
}

function renderWorkspaceTimelineEvent(event) {
  return `
    <article class="timeline-item">
      <div class="timeline-item-header">${timelineBadge(event.event_type)}<strong>${escapeHtml(event.title)}</strong></div>
      <span>${escapeHtml(formatDate(event.timestamp))} · ${escapeHtml(event.source || "")}</span>
      <p>${escapeHtml(event.description || "")}</p>
    </article>
  `;
}

function renderMemorySimilarity(item) {
  const experiment = item.experiment || {};
  const similarities = (item.key_similarities || []).slice(0, 4).join(" · ");
  const differences = (item.important_differences || []).slice(0, 3).join(" · ");
  return `
    <a class="item-link" href="#/experiments/${encodeURIComponent(experiment.id || "")}/workspace">
      <strong>${escapeHtml(experiment.experiment_id || experiment.title || experiment.id || "Similar experiment")}</strong>
      <span>Similarity score: ${escapeHtml(item.similarity_score ?? "0")}</span>
      <span>${escapeHtml(similarities ? `Similarities: ${similarities}` : "No key similarities listed.")}</span>
      <span>${escapeHtml(differences ? `Differences: ${differences}` : "No major differences listed.")}</span>
    </a>
  `;
}

function renderWorkspaceAsset(asset) {
  return `
    <a class="item-link" href="#/assets/${encodeURIComponent(asset.asset_id || "")}">
      <strong>${escapeHtml(asset.title || asset.filename || asset.asset_id)}</strong>
      <span>${escapeHtml(asset.provider || "")} · ${escapeHtml(asset.filename || "")}</span>
    </a>
  `;
}

function renderWorkspaceSpreadsheet(asset) {
  const compact = asset.compact_summary || {};
  return `
    <article class="result">
      <h3>${escapeHtml(asset.title || asset.filename || asset.asset_id)}</h3>
      <p>${escapeHtml(compact.short_interpretation || asset.path || "Spreadsheet metadata available.")}</p>
      <div class="meta"><span class="tag">${escapeHtml(asset.provider || "spreadsheet")}</span></div>
    </article>
  `;
}

function renderWorkspaceStatistic(asset) {
  const compact = asset.compact_summary || {};
  const interpretation = asset.interpretation || {};
  return `
    <article class="result">
      <h3>${escapeHtml(asset.title || asset.filename || asset.asset_id)}</h3>
      <p>${escapeHtml(compact.short_interpretation || interpretation.summary || "Statistics interpretation available.")}</p>
      <div class="meta"><span class="tag">${escapeHtml(asset.provider || "statistics")}</span></div>
    </article>
  `;
}

function renderWorkspaceDocument(document) {
  return `
    <article class="result">
      <h3>${escapeHtml(document.title || document.id)}</h3>
      <p>${escapeHtml(document.source_path || document.source_url || document.provider || "")}</p>
    </article>
  `;
}

function renderWorkspaceExperiment(experiment) {
  return `
    <a class="item-link" href="#/experiments/${encodeURIComponent(experiment.id || "")}/workspace">
      <strong>${escapeHtml(experiment.experiment_id || experiment.title || experiment.id)}</strong>
      <span>${escapeHtml(experiment.source_provider || experiment.provider || "")}</span>
    </a>
  `;
}

function renderWorkspaceEntity(entity) {
  return `
    <a class="item-link" href="#/graph/${encodeURIComponent(entity.entity_type || "entity")}/${encodeURIComponent(entity.entity || "")}">
      <strong>${escapeHtml(entity.entity)}</strong>
      <span>${escapeHtml(entity.entity_type || "")} · ${escapeHtml(entity.reference_count || 0)} references</span>
    </a>
  `;
}

function renderWorkspaceFile(file) {
  return `
    <article class="result">
      <h3>${escapeHtml(file.title || file.filename || file.asset_id)}</h3>
      <p>${escapeHtml(file.path || "")}</p>
      <div class="meta"><span class="tag">${escapeHtml(file.provider || "")}</span></div>
    </article>
  `;
}

function renderWorkspaceProvenance(item) {
  return `
    <article class="result">
      <h3>${escapeHtml(item.fact)} · ${escapeHtml(item.source)}</h3>
      <p>${escapeHtml([item.provider, item.document, item.asset, item.timestamp].filter(Boolean).join(" · "))}</p>
    </article>
  `;
}

function listItems(items) {
  return items.length ? items.map((item) => `<li>${escapeHtml(item)}</li>`).join("") : "<li>None captured.</li>";
}

function bindExperimentDetailTabs() {
  $$(".tab-button[data-experiment-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      const tab = button.dataset.experimentTab;
      $$(".tab-button[data-experiment-tab]").forEach((node) => node.classList.remove("active"));
      button.classList.add("active");
      $("#experimentOverviewTab").hidden = tab !== "overview";
      $("#experimentTimelineTab").hidden = tab !== "timeline";
    });
  });
}

async function loadExperimentTimeline(experimentId) {
  const target = $("#experimentTimeline");
  if (!target) return;
  try {
    const timeline = await requestJson(`/experiments/${encodeURIComponent(experimentId)}/timeline`);
    target.innerHTML = (timeline.events || []).length
      ? timeline.events.map((event) => `
        <article class="timeline-item">
          <div class="timeline-item-header">
            ${timelineBadge(event.event_type)}
            <strong>${escapeHtml(event.title)}</strong>
          </div>
          <span>${escapeHtml(formatDate(event.timestamp))} · ${escapeHtml(event.source)}</span>
          <p>${escapeHtml(event.description)}</p>
          <div class="meta">
            ${(event.linked_asset_ids || []).map((assetId) => `<a class="mini-chip" href="#/assets/${encodeURIComponent(assetId)}">${escapeHtml(assetId)}</a>`).join("")}
            ${(event.linked_document_ids || []).map((documentId) => `<span class="tag">${escapeHtml(documentId)}</span>`).join("")}
          </div>
        </article>
      `).join("")
      : `<div class="empty-state">No timeline events found for this experiment.</div>`;
  } catch (error) {
    target.innerHTML = `<div class="empty-state">Timeline unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

function entityTitle(entityType) {
  return {
    compounds: "Compounds",
    markers: "Markers",
    "cell-lines": "Cell Lines",
    "organoid-batches": "Organoid Batches",
  }[entityType] || "Entities";
}

function renderEntityList(entityType) {
  const entities = state.ontology[entityType] || [];
  $("#entityListEyebrow").textContent = "Retinal organoid ontology";
  $("#entityListTitle").textContent = entityTitle(entityType);
  $("#entityList").innerHTML = entities.length
    ? entities
        .map(
          (entity) => `
            <a class="entity-card" href="#/${entityType}/${encodeURIComponent(entity.name)}">
              <strong>${escapeHtml(entity.name)}</strong>
              <span>${entity.experiments.length} experiments · ${entity.protocols.length} protocols · ${entity.documents.length} documents</span>
              <small>Open local graph</small>
            </a>
          `,
        )
        .join("")
    : `<div class="empty-state">No ${escapeHtml(entityTitle(entityType).toLowerCase())} detected.</div>`;
}

function renderEntityDetail(entityType, name) {
  const entity = (state.ontology[entityType] || []).find(
    (item) => item.name.toLowerCase() === name.toLowerCase(),
  );
  if (!entity) {
    $("#entityDetail").innerHTML = `<div class="empty-state">Entity not found.</div>`;
    return;
  }
  $("#entityDetail").innerHTML = `
    <a class="inline-link" href="#/${entityType}">Back to ${escapeHtml(entityTitle(entityType))}</a>
    <a class="inline-link" href="${graphEntityLink(entityType, entity.name)}">Open in Graph Explorer</a>
    <button type="button" class="secondary-button ask-kg-button" data-question="What do we know about ${escapeHtml(entity.name)}?">Ask about this entity</button>
    <div class="detail-header">
      <div>
        <p class="eyebrow">${escapeHtml(entityTitle(entityType))}</p>
        <h2>${escapeHtml(entity.name)}</h2>
      </div>
      <span class="status-pill ok">${entity.experiments.length} experiments</span>
    </div>
    ${linkedSection("Experiments", entity.experiments, (experiment) => `
      <a class="item-link" href="#/experiments/${encodeURIComponent(experiment.id)}">
        <strong>${escapeHtml(experiment.experiment_id || experiment.title)}</strong>
        <span>${escapeHtml(experiment.date || "No date")} · ${escapeHtml(experiment.provider || "unknown")}</span>
      </a>
    `)}
    ${linkedSection("Protocols", entity.protocols, (document) => `
      <article class="record-card">
        <h3>${escapeHtml(document.title)}</h3>
        <p>${escapeHtml(document.source_path || document.source_url || document.id)}</p>
      </article>
    `)}
    ${linkedSection("Documents", entity.documents, (document) => `
      <article class="record-card">
        <h3>${escapeHtml(document.title)}</h3>
        <p>${escapeHtml(document.source_path || document.source_url || document.id)}</p>
      </article>
    `)}
    ${linkedSection("Images", entity.images, renderImageAssetCard)}
    ${linkedSection("AI summaries", entity.ai_summaries, (summary) => `
      <article class="record-card">
        <h3>${escapeHtml(summary.title || "Summary")}</h3>
        <p>${escapeHtml(summary.summary || "")}</p>
      </article>
    `)}
  `;
}

function linkedSection(title, items, renderer) {
  return `
    <section class="detail-section">
      <h3>${escapeHtml(title)}</h3>
      <div class="item-list">
        ${items.length ? items.map(renderer).join("") : `<div class="empty-state">No linked ${escapeHtml(title.toLowerCase())} yet.</div>`}
      </div>
    </section>
  `;
}

function detailField(label, value) {
  return `<div class="detail-field"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "Not captured")}</strong></div>`;
}

function graphChip(type, value) {
  return `<a class="mini-chip" href="${graphEntityLink(type, value)}">${escapeHtml(value)}</a>`;
}

function tagSection(title, values = [], graphType = "") {
  return `
    <section class="detail-section">
      <h3>${escapeHtml(title)}</h3>
      <div class="tag-row">${values.length ? values.map((value) => graphType ? graphChip(graphType, value) : `<span class="tag">${escapeHtml(value)}</span>`).join("") : `<span class="muted">None captured</span>`}</div>
    </section>
  `;
}

function renderGraphExplorer() {
  const stats = state.graphStats;
  if (!stats) {
    $("#graphStats").innerHTML = `<div class="empty-state">Graph statistics are loading.</div>`;
    $("#graphCanvas").innerHTML = "";
    $("#graphEntityList").innerHTML = "";
    return;
  }

  const entityCounts = stats.entity_counts || {};
  $("#graphStats").innerHTML = Object.entries(entityCounts).length
    ? Object.entries(entityCounts)
        .map(([label, count]) => `<article class="metric-card compact-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(count)}</strong></article>`)
        .join("")
    : `<div class="empty-state">No graph entities detected.</div>`;

  renderGraphVisualization(stats);
  const nodes = (stats.nodes || []).slice(0, 36);
  $("#graphEntityList").innerHTML = nodes.length
    ? nodes
        .map((node) => {
          const routeType = graphRouteType(node.type);
          return `
            <a class="item-link" href="${graphEntityLink(routeType, node.label)}">
              <strong>${escapeHtml(node.label)}</strong>
              <span>${escapeHtml(node.type)}</span>
            </a>
          `;
        })
        .join("")
    : `<div class="empty-state">Load demo notes to populate the graph.</div>`;
}

function graphRouteType(nodeType) {
  return {
    compound: "compounds",
    marker: "markers",
    gene: "genes",
    paper: "papers",
    protocol: "protocols",
    experiment: "experiments",
    "cell-line": "cell-lines",
    "organoid-batch": "organoid-batches",
  }[nodeType] || `${nodeType}s`;
}

function renderGraphVisualization(stats) {
  const rawNodes = (stats.nodes || []).slice(0, 55);
  const rawLinks = (stats.links || []).filter((link) =>
    rawNodes.some((node) => node.id === link.source) && rawNodes.some((node) => node.id === link.target),
  ).slice(0, 110);
  if (!rawNodes.length) {
    $("#graphCanvas").innerHTML = `<div class="empty-state">No graph data yet.</div>`;
    return;
  }

  const width = 720;
  const height = 430;
  const nodes = rawNodes.map((node, index) => {
    const angle = (index / rawNodes.length) * Math.PI * 2;
    return {
      ...node,
      x: width / 2 + Math.cos(angle) * (120 + (index % 5) * 24),
      y: height / 2 + Math.sin(angle) * (90 + (index % 4) * 22),
      vx: 0,
      vy: 0,
    };
  });
  const byId = new Map(nodes.map((node) => [node.id, node]));

  for (let tick = 0; tick < 80; tick += 1) {
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = a.x - b.x || 0.01;
        const dy = a.y - b.y || 0.01;
        const distanceSquared = Math.max(dx * dx + dy * dy, 120);
        const force = 900 / distanceSquared;
        a.vx += dx * force;
        a.vy += dy * force;
        b.vx -= dx * force;
        b.vy -= dy * force;
      }
    }
    for (const link of rawLinks) {
      const a = byId.get(link.source);
      const b = byId.get(link.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      a.vx += dx * 0.006;
      a.vy += dy * 0.006;
      b.vx -= dx * 0.006;
      b.vy -= dy * 0.006;
    }
    for (const node of nodes) {
      node.vx += (width / 2 - node.x) * 0.004;
      node.vy += (height / 2 - node.y) * 0.004;
      node.x = Math.min(width - 28, Math.max(28, node.x + node.vx));
      node.y = Math.min(height - 28, Math.max(28, node.y + node.vy));
      node.vx *= 0.72;
      node.vy *= 0.72;
    }
  }

  const colorFor = (type) => ({
    experiment: "var(--accent)",
    compound: "#2c7be5",
    marker: "#b54708",
    gene: "#7c3aed",
    paper: "#0f766e",
    protocol: "#64748b",
    "cell-line": "#be185d",
    "organoid-batch": "#15803d",
  }[type] || "var(--muted)");

  $("#graphCanvas").innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="ResearchOS force-directed knowledge graph">
      ${rawLinks
        .map((link) => {
          const a = byId.get(link.source);
          const b = byId.get(link.target);
          if (!a || !b) return "";
          return `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}" />`;
        })
        .join("")}
      ${nodes
        .map((node) => `
          <a href="${graphEntityLink(graphRouteType(node.type), node.label)}">
            <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${node.type === "experiment" ? 8 : 6}" fill="${colorFor(node.type)}" />
            <text x="${(node.x + 9).toFixed(1)}" y="${(node.y + 4).toFixed(1)}">${escapeHtml(shortText(node.label, 24))}</text>
          </a>
        `)
        .join("")}
    </svg>
  `;
}

async function renderGraphEntity(entityType, name) {
  const target = $("#graphDetail");
  target.innerHTML = `<div class="empty-state">Loading graph entity...</div>`;
  try {
    const entity = await requestJson(`/graph/entity/${encodeURIComponent(entityType)}/${encodeURIComponent(name)}`);
    target.innerHTML = `
      <a class="inline-link" href="#/graph">Back to Graph Explorer</a>
      <button type="button" class="secondary-button ask-kg-button" data-question="What do we know about ${escapeHtml(entity.name)}?">Ask about this entity</button>
      <div class="detail-header">
        <div>
          <p class="eyebrow">${escapeHtml(entity.type)}</p>
          <h2>${escapeHtml(entity.name)}</h2>
        </div>
        <span class="status-pill ok">${escapeHtml(entity.relationship_counts.citations || 0)} citations</span>
      </div>
      <p class="card-copy">${escapeHtml(entity.overview)}</p>
      <section class="detail-section">
        <h3>AI summary</h3>
        <p>${escapeHtml(entity.ai_summary)}</p>
      </section>
      ${relationshipCountGrid(entity.relationship_counts)}
      ${linkedSection("Related experiments", entity.related_experiments, (experiment) => `
        <a class="item-link" href="#/experiments/${encodeURIComponent(experiment.id)}">
          <strong>${escapeHtml(experiment.experiment_id || experiment.title || experiment.id)}</strong>
          <span>${escapeHtml(formatDate(experiment.date))} · ${escapeHtml(experiment.provider || "unknown")}</span>
        </a>
      `)}
      ${graphTermSection("Related compounds", "compounds", entity.related_compounds)}
      ${graphTermSection("Related markers", "markers", entity.related_markers)}
      ${graphTermSection("Related genes", "genes", entity.related_genes)}
      ${graphTermSection("Related cell lines", "cell-lines", entity.related_cell_lines)}
      ${graphTermSection("Related batches", "organoid-batches", entity.related_batches)}
      ${linkedSection("Related images", entity.related_images || [], renderImageAssetCard)}
      ${linkedSection("Related papers", entity.related_papers, (paper) => `
        <a class="item-link" href="${graphEntityLink("papers", paper.id)}">
          <strong>${escapeHtml(paper.title)}</strong>
          <span>${escapeHtml([paper.year, paper.journal, paper.doi].filter(Boolean).join(" · ") || "local literature")}</span>
        </a>
      `)}
      ${linkedSection("Related protocols", entity.related_protocols, (protocol) => `
        <a class="item-link" href="${graphEntityLink("protocols", protocol.id)}">
          <strong>${escapeHtml(protocol.title)}</strong>
          <span>${escapeHtml(protocol.source_path || protocol.source_url || protocol.id)}</span>
        </a>
      `)}
      ${linkedSection("Timeline", entity.timeline, (item) => `
        <article class="timeline-item">
          <strong>${escapeHtml(item.title)}</strong>
          <span>${escapeHtml(item.kind)} · ${escapeHtml(formatDate(item.date))}</span>
        </article>
      `)}
      ${linkedSection("Source citations", entity.source_citations, (source) => `
        <article class="result">
          <h3>${escapeHtml(source.title)}</h3>
          <p>${escapeHtml(shortText(source.snippet, 260))}</p>
          <div class="meta"><span class="tag">${escapeHtml(source.provider || "unknown")}</span></div>
        </article>
      `)}
    `;
  } catch (error) {
    target.innerHTML = `<div class="empty-state">Graph entity unavailable: ${escapeHtml(error.message)}</div>`;
  }
}

function relationshipCountGrid(counts = {}) {
  return `
    <section class="graph-stat-grid">
      ${Object.entries(counts)
        .map(([label, count]) => `<article class="metric-card compact-metric"><span>${escapeHtml(label.replaceAll("_", " "))}</span><strong>${escapeHtml(count)}</strong></article>`)
        .join("")}
    </section>
  `;
}

function graphTermSection(title, type, values = []) {
  return `
    <section class="detail-section">
      <h3>${escapeHtml(title)}</h3>
      <div class="tag-row">
        ${values.length ? values.map((value) => graphChip(type, value)).join("") : `<span class="muted">None linked.</span>`}
      </div>
    </section>
  `;
}

function textSection(title, value) {
  return `
    <section class="detail-section">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(value || "None captured")}</p>
    </section>
  `;
}

function renderSearchResults(target, results) {
  target.innerHTML = results.length
    ? results
        .map(
          (result) => `
            <article class="result">
              <h3>${highlightText(result.title || "Untitled result")}</h3>
              <p>${highlightText(shortText(result.snippet))}</p>
              <div class="meta">
                <span class="tag">${escapeHtml(result.provider || "unknown")}</span>
                <span class="tag">${escapeHtml(result.source)}</span>
                <span class="tag">score ${escapeHtml(result.score ?? "n/a")}</span>
              </div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No matches found.</div>`;
}

async function runSearch(query, target) {
  state.searchTerms = query.split(/\s+/).filter(Boolean);
  target.innerHTML = `<div class="empty-state">Searching...</div>`;
  const results = await requestJson("/search", {
    method: "POST",
    body: JSON.stringify({ query, limit: 8 }),
  });
  renderSearchResults(target, results);
}

function renderChatResponse(target, payload) {
  const sources = payload.source_document_citations || payload.sources || [];
  const directMatches = payload.direct_matches || payload.evidence_from_experiments || [];
  const relatedContext = payload.related_context || [];
  const literatureContext = payload.literature_context || [];
  const limitations = payload.limitations_uncertainties || [];
  target.innerHTML = `
    <div class="assistant-answer">
      <h3>Answer</h3>
      <p>${escapeHtml(payload.direct_answer || payload.answer)}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(payload.provider)}</span>
        <span class="tag">${payload.ai_used ? "AI synthesis" : "local fallback"}</span>
        <span class="tag">${sources.length} source${sources.length === 1 ? "" : "s"}</span>
      </div>
    </div>
    ${payload.ai_synthesis ? `<div class="assistant-answer"><h3>Synthesis</h3><p>${escapeHtml(payload.ai_synthesis)}</p></div>` : ""}
    ${directMatches.length ? `
      <div class="source-list">
        <h3>Direct Matches</h3>
        ${directMatches
          .map(
            (experiment) => `
              <article class="result">
                <h3>${escapeHtml(experiment.experiment_id || experiment.title || experiment.id)}</h3>
                <p>${escapeHtml(shortText(experiment.conclusions || experiment.notes || "Structured experiment metadata available.", 220))}</p>
                <div class="meta">
                  ${(experiment.compounds || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
                  ${(experiment.markers || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    ` : ""}
    ${relatedContext.length ? `
      <div class="source-list">
        <h3>Related Context</h3>
        ${relatedContext
          .map(
            (experiment) => `
              <article class="result">
                <h3>${escapeHtml(experiment.experiment_id || experiment.title || experiment.id)}</h3>
                <p>${escapeHtml(shortText(experiment.conclusions || experiment.notes || "Related structured metadata available.", 220))}</p>
                <div class="meta">
                  <span class="tag">related</span>
                  ${(experiment.compounds || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
                  ${(experiment.markers || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    ` : ""}
    ${literatureContext.length ? `
      <div class="source-list">
        <h3>Literature Context</h3>
        ${literatureContext
          .map(
            (source) => `
              <article class="result">
                <h3>${escapeHtml(source.title || "Untitled literature source")}</h3>
                <p>${escapeHtml(shortText(source.snippet, 220))}</p>
                <div class="meta">
                  <span class="tag">literature</span>
                  <span class="tag">score ${escapeHtml(source.score ?? "n/a")}</span>
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
    ` : ""}
    <div class="source-list">
      <h3>Sources</h3>
      ${sources
        .map(
          (source, index) => `
            <article class="result">
              <h3>${escapeHtml(source.citation || `[${index + 1}]`)} ${escapeHtml(source.title || "Untitled source")}</h3>
              <p>${escapeHtml(shortText(source.snippet, 180))}</p>
            </article>
          `,
        )
        .join("")}
    </div>
    ${limitations.length ? `<div class="empty-state"><strong>Limitations:</strong> ${escapeHtml(limitations.join(" "))}</div>` : ""}
  `;
}

function renderKnowledgeGraphAssistantResponse(target, payload) {
  const cardList = (title, items, renderer) => `
    <div class="source-list">
      <h3>${escapeHtml(title)}</h3>
      ${items?.length ? items.map(renderer).join("") : `<div class="empty-state">No ${escapeHtml(title.toLowerCase())} linked in the Knowledge Graph.</div>`}
    </div>
  `;
  const evidenceCard = (item) => `
    <article class="result">
      <h3>${escapeHtml(item.experiment_id || item.title || item.filename || item.id || item.asset_id || item.entity || "Evidence")}</h3>
      <p>${escapeHtml(shortText(item.summary || item.snippet || item.path || item.provider || JSON.stringify(item), 240))}</p>
      <div class="meta">
        ${item.provider ? `<span class="tag">${escapeHtml(item.provider)}</span>` : ""}
        ${item.entity_type ? `<span class="tag">${escapeHtml(item.entity_type)}</span>` : ""}
        ${item.source_section ? `<span class="tag">${escapeHtml(item.source_section)}</span>` : ""}
      </div>
    </article>
  `;
  target.innerHTML = `
    <div class="assistant-answer">
      <h3>Knowledge Graph Answer</h3>
      <p>${escapeHtml(payload.direct_answer)}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(payload.provider)}</span>
        <span class="tag">${payload.ai_used ? "AI synthesis" : "local graph fallback"}</span>
        ${payload.entity ? `<span class="tag">${escapeHtml(payload.entity)}</span>` : ""}
        ${payload.entity_type ? `<span class="tag">${escapeHtml(payload.entity_type)}</span>` : ""}
      </div>
    </div>
    <section class="detail-section">
      <h3>Knowledge Graph Summary</h3>
      <p>${escapeHtml(payload.knowledge_graph_summary || "No graph summary available.")}</p>
    </section>
    ${cardList("Experiments", payload.experiments || [], evidenceCard)}
    ${cardList("Notebook Entries", payload.notebook_entries || [], evidenceCard)}
    ${cardList("Literature", payload.literature || [], evidenceCard)}
    ${cardList("GraphPad / Statistics", payload.graphpad_statistics || [], evidenceCard)}
    ${cardList("Spreadsheets", payload.spreadsheets || [], evidenceCard)}
    ${cardList("Microscopy / Images", payload.microscopy_images || [], evidenceCard)}
    ${cardList("Related Entities", payload.related_entities || [], (item) => `
      <a class="item-link" href="#/graph/${encodeURIComponent(item.entity_type || "entities")}/${encodeURIComponent(item.entity || item.name || "")}">
        <strong>${escapeHtml(item.entity || item.name)}</strong>
        <span>${escapeHtml(item.entity_type || "entity")} · ${escapeHtml(item.count ?? item.reference_count ?? "")}</span>
      </a>
    `)}
    <section class="detail-section">
      <h3>Limitations</h3>
      <ul>${(payload.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>None listed.</li>"}</ul>
    </section>
  `;
}

function renderLiteratureComparisonResponse(target, payload) {
  const labExperiments = payload.matching_lab_experiments || [];
  const literatureSources = payload.matching_literature_sources || [];
  const citations = payload.citations || [];
  const listItems = (items) => items.length
    ? items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : `<li>None detected in the retrieved local context.</li>`;

  target.innerHTML = `
    <div class="assistant-answer">
      <h3>Lab-Literature Comparison</h3>
      <p>${escapeHtml(payload.direct_answer)}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(payload.provider)}</span>
        <span class="tag">${payload.ai_used ? "AI synthesis" : "local fallback"}</span>
        <span class="tag">${labExperiments.length} lab match${labExperiments.length === 1 ? "" : "es"}</span>
        <span class="tag">${literatureSources.length} literature source${literatureSources.length === 1 ? "" : "s"}</span>
      </div>
    </div>
    ${payload.ai_synthesis ? `<div class="assistant-answer"><h3>Synthesis</h3><p>${escapeHtml(payload.ai_synthesis)}</p></div>` : ""}
    <div class="source-list">
      <h3>Matching Lab Experiments</h3>
      ${labExperiments.length ? labExperiments.map((experiment) => `
        <article class="result">
          <h3>${escapeHtml(experiment.experiment_id || experiment.title || experiment.id)}</h3>
          <p>${escapeHtml(shortText(experiment.conclusions || experiment.notes || "Structured experiment metadata available.", 220))}</p>
          <div class="meta">
            ${(experiment.compounds || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
            ${(experiment.markers || []).map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("")}
          </div>
        </article>
      `).join("") : `<div class="empty-state">No matching lab experiments found.</div>`}
    </div>
    <div class="source-list">
      <h3>Matching Literature Sources</h3>
      ${literatureSources.length ? literatureSources.map((source) => `
        <article class="result">
          <h3>${escapeHtml(source.title || "Untitled literature source")}</h3>
          <p>${escapeHtml(shortText(source.snippet, 240))}</p>
          <div class="meta">
            <span class="tag">literature</span>
            <span class="tag">score ${escapeHtml(source.score ?? "n/a")}</span>
          </div>
        </article>
      `).join("") : `<div class="empty-state">No matching literature sources found. Ingest papers first.</div>`}
    </div>
    <div class="detail-grid comparison-summary-grid">
      <section class="detail-field">
        <span>Similarities</span>
        <ul>${listItems(payload.similarities || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Differences</span>
        <ul>${listItems(payload.differences || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Protocol/treatment differences</span>
        <ul>${listItems(payload.protocol_treatment_differences || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Limitations</span>
        <ul>${listItems(payload.limitations || [])}</ul>
      </section>
    </div>
    <div class="source-list">
      <h3>Citations</h3>
      ${citations.length ? citations.map((source) => `
        <article class="result">
          <h3>${escapeHtml(source.citation || "")} ${escapeHtml(source.title || "Untitled source")}</h3>
          <p>${escapeHtml(shortText(source.snippet, 180))}</p>
          <div class="meta"><span class="tag">${escapeHtml(source.provider || "unknown")}</span></div>
        </article>
      `).join("") : `<div class="empty-state">No citations retrieved.</div>`}
    </div>
  `;
}

function renderScientificReasoningResponse(target, payload) {
  const reasoning = payload.reasoning || {};
  const sources = payload.sources || [];
  const listItems = (items) => items?.length
    ? items.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.title || item.filename || item.snippet || item.id || JSON.stringify(item))}</li>`).join("")
    : `<li>None detected in local evidence.</li>`;
  const evidenceCards = (items) => items?.length
    ? items.map((item) => `
      <article class="result">
        <h3>${escapeHtml(item.title || item.filename || item.experiment_id || item.id || item.kind || "Evidence")}</h3>
        <p>${escapeHtml(shortText(item.snippet || item.path || item.provider || JSON.stringify(item), 240))}</p>
        <div class="meta">
          <span class="tag">${escapeHtml(item.kind || item.provider || "evidence")}</span>
          ${item.score !== undefined ? `<span class="tag">score ${escapeHtml(item.score)}</span>` : ""}
        </div>
      </article>
    `).join("")
    : `<div class="empty-state">No evidence in this category.</div>`;

  target.innerHTML = `
    <div class="assistant-answer">
      <h3>Scientific Answer</h3>
      <p>${escapeHtml(payload.answer)}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(payload.provider)}</span>
        <span class="tag">${payload.ai_used ? "AI synthesis" : "local deterministic reasoning"}</span>
        <span class="tag">confidence ${escapeHtml(reasoning.confidence || "unknown")}</span>
        <span class="tag">${sources.length} source${sources.length === 1 ? "" : "s"}</span>
      </div>
    </div>
    <div class="detail-grid comparison-summary-grid">
      <section class="detail-field">
        <span>Observations</span>
        <ul>${listItems(reasoning.observations || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Suggested follow-up experiments</span>
        <ul>${listItems(reasoning.recommended_next_experiments || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Limitations</span>
        <ul>${listItems(reasoning.limitations || [])}</ul>
      </section>
    </div>
    <div class="source-list">
      <h3>Supporting Evidence</h3>
      ${evidenceCards(reasoning.supporting_evidence || [])}
    </div>
    <div class="source-list">
      <h3>Conflicting Evidence</h3>
      ${evidenceCards(reasoning.conflicting_evidence || [])}
    </div>
    <div class="source-list">
      <h3>Timeline Context</h3>
      ${evidenceCards(reasoning.timeline_events || [])}
    </div>
    <div class="source-list">
      <h3>Sources</h3>
      ${evidenceCards(sources)}
    </div>
  `;
}

function renderExperimentPlan(target, payload) {
  const listItems = (items) => items?.length
    ? items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : `<li>Not specified.</li>`;
  const sourceCards = (items) => items?.length
    ? items.map((item) => `
      <article class="result">
        <h3>${escapeHtml(item.title || item.filename || item.experiment_id || item.id || item.kind || "Source")}</h3>
        <p>${escapeHtml(shortText(item.snippet || item.path || item.provider || JSON.stringify(item), 220))}</p>
        <div class="meta">
          <span class="tag">${escapeHtml(item.kind || item.provider || "source")}</span>
          ${item.score !== undefined ? `<span class="tag">score ${escapeHtml(item.score)}</span>` : ""}
        </div>
      </article>
    `).join("")
    : `<div class="empty-state">No sources matched this planning question.</div>`;

  target.innerHTML = `
    <div class="assistant-answer">
      <h3>${escapeHtml(payload.proposed_experiment_title)}</h3>
      <p>${escapeHtml(payload.hypothesis)}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(payload.provider)}</span>
        <span class="tag">${payload.ai_used ? "AI synthesis" : "local deterministic plan"}</span>
        <span class="tag">${(payload.sources || []).length} source${(payload.sources || []).length === 1 ? "" : "s"}</span>
      </div>
    </div>
    <section class="detail-section">
      <h3>Rationale</h3>
      <p>${escapeHtml(payload.rationale)}</p>
    </section>
    <div class="detail-grid comparison-summary-grid">
      <section class="detail-field">
        <span>Experimental groups</span>
        <ul>${listItems(payload.experimental_groups || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Treatment schedule</span>
        <ul>${listItems(payload.treatment_schedule || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Controls</span>
        <ul>${listItems(payload.controls || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Planned readouts</span>
        <ul>${listItems(payload.planned_readouts || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Suggested markers</span>
        <ul>${listItems(payload.suggested_markers || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Risks / confounders</span>
        <ul>${listItems(payload.risks_confounders || [])}</ul>
      </section>
      <section class="detail-field">
        <span>Expected outcomes</span>
        <ul>${listItems(payload.expected_outcomes || [])}</ul>
      </section>
    </div>
    <section class="detail-section">
      <h3>Statistical analysis plan</h3>
      <p>${escapeHtml(payload.statistical_analysis_plan)}</p>
    </section>
    <section class="detail-section">
      <h3>Suggested OneNote draft entry</h3>
      <p class="demo-status">Write-back is disabled. Save this as a local ResearchOS draft for review/export.</p>
      <pre class="markdown-preview">${escapeHtml(payload.suggested_onenote_draft_entry)}</pre>
    </section>
    <div class="source-list">
      <h3>Sources</h3>
      ${sourceCards(payload.sources || [])}
    </div>
  `;
}

async function runChat(message, target) {
  target.innerHTML = `<div class="empty-state">Thinking...</div>`;
  try {
    const payload = await requestJson("/assistant/ask", {
      method: "POST",
      body: JSON.stringify({ question: message }),
    });
    renderChatResponse(target, payload);
  } catch (error) {
    target.innerHTML = `<div class="result"><h3>Chat setup required</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function runKnowledgeGraphAssistant(message, target) {
  target.innerHTML = `<div class="empty-state">Querying the Knowledge Graph...</div>`;
  try {
    const payload = await requestJson("/assistant/knowledge", {
      method: "POST",
      body: JSON.stringify({ question: message }),
    });
    renderKnowledgeGraphAssistantResponse(target, payload);
  } catch (error) {
    target.innerHTML = `<div class="result"><h3>Knowledge Graph assistant failed</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function runExperimentPlanner(message, target) {
  $("#plannerStatus").textContent = "Planning follow-up experiment from local evidence...";
  target.innerHTML = `<div class="empty-state">Planning...</div>`;
  try {
    const payload = await requestJson("/assistant/plan-experiment", {
      method: "POST",
      body: JSON.stringify({ question: message }),
    });
    state.currentExperimentPlan = payload;
    $("#plannerStatus").textContent = "Plan generated. Review before saving as a ResearchOS draft.";
    renderExperimentPlan(target, payload);
  } catch (error) {
    $("#plannerStatus").textContent = `Planning failed: ${error.message}`;
    target.innerHTML = `<div class="result"><h3>Planner unavailable</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function runScientificReasoning(message, target) {
  target.innerHTML = `<div class="empty-state">Reasoning across local evidence...</div>`;
  try {
    const payload = await requestJson("/assistant/reason", {
      method: "POST",
      body: JSON.stringify({ question: message }),
    });
    renderScientificReasoningResponse(target, payload);
  } catch (error) {
    target.innerHTML = `<div class="result"><h3>Scientific reasoning failed</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

async function runLiteratureComparison(message, target) {
  target.innerHTML = `<div class="empty-state">Comparing lab records with literature...</div>`;
  try {
    const payload = await requestJson("/assistant/compare-literature", {
      method: "POST",
      body: JSON.stringify({ question: message }),
    });
    renderLiteratureComparisonResponse(target, payload);
  } catch (error) {
    target.innerHTML = `<div class="result"><h3>Comparison unavailable</h3><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function openGlobalSearch() {
  const overlay = $("#globalSearchOverlay");
  const input = $("#globalSearchInput");
  overlay.hidden = false;
  input.focus();
  input.select();
}

function closeGlobalSearch() {
  $("#globalSearchOverlay").hidden = true;
}

async function runUniversalSearch(query) {
  const output = $("#globalSearchResults");
  const meta = $("#globalSearchMeta");
  if (!query.trim()) {
    meta.textContent = "Type to search notebooks, experiments, entities, assets, literature, and commands.";
    output.innerHTML = "";
    return;
  }
  meta.textContent = "Searching all ResearchOS providers...";
  const payload = await requestJson(`/search/universal?q=${encodeURIComponent(query)}&limit_per_group=6`);
  meta.textContent = `${payload.total_results} result${payload.total_results === 1 ? "" : "s"} for "${payload.query}"`;
  renderUniversalSearchResults(output, payload);
}

function renderUniversalSearchResults(target, payload) {
  const grouped = payload.grouped_results || {};
  const labels = {
    experiments: "Experiments",
    notebook_entries: "Notebook entries",
    entities: "Knowledge Graph entities",
    images: "Microscopy / images",
    graphpad: "GraphPad",
    spreadsheets: "Spreadsheets",
    statistics: "Statistics",
    literature: "Literature",
    timeline: "Timeline",
    commands: "Commands",
  };
  const sections = Object.entries(labels)
    .map(([group, label]) => {
      const results = grouped[group] || [];
      if (!results.length) return "";
      return `
        <section class="universal-result-group">
          <h3>${escapeHtml(label)}</h3>
          ${results.map(renderUniversalResult).join("")}
        </section>
      `;
    })
    .join("");
  const suggestions = (payload.suggested_queries || []).length
    ? `
      <section class="universal-result-group">
        <h3>Suggested queries</h3>
        ${(payload.suggested_queries || []).map((query) => `
          <button type="button" class="mini-chip universal-suggestion" data-query="${escapeHtml(query)}">${escapeHtml(query)}</button>
        `).join("")}
      </section>
    `
    : "";
  target.innerHTML = sections || `<div class="empty-state">No universal search results found.</div>`;
  target.insertAdjacentHTML("beforeend", suggestions);
  $$(".universal-suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      $("#globalSearchInput").value = button.dataset.query || "";
      runUniversalSearch($("#globalSearchInput").value).catch((error) => {
        $("#globalSearchMeta").textContent = `Universal search failed: ${error.message}`;
      });
    });
  });
}

function renderUniversalResult(result) {
  return `
    <a class="universal-result" href="${escapeHtml(result.href || "#/dashboard")}" data-universal-result>
      <strong>${escapeHtml(result.title || result.id || "Result")}</strong>
      <span>${escapeHtml(result.subtitle || result.provider || "")}</span>
      <small>${escapeHtml(result.provider || result.type || "")} · score ${escapeHtml(result.score ?? "n/a")}</small>
    </a>
  `;
}

function bindUniversalSearch() {
  const button = $("#globalSearchButton");
  const close = $("#globalSearchClose");
  const overlay = $("#globalSearchOverlay");
  const input = $("#globalSearchInput");
  const results = $("#globalSearchResults");
  let timer = null;

  button?.addEventListener("click", openGlobalSearch);
  close?.addEventListener("click", closeGlobalSearch);
  overlay?.addEventListener("click", (event) => {
    if (event.target === overlay) closeGlobalSearch();
  });
  results?.addEventListener("click", (event) => {
    const link = event.target.closest("[data-universal-result]");
    if (!link) return;
    closeGlobalSearch();
  });
  input?.addEventListener("input", () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < 2) {
      $("#globalSearchMeta").textContent = "Type at least two characters to search.";
      results.innerHTML = "";
      return;
    }
    timer = setTimeout(() => {
      runUniversalSearch(query).catch((error) => {
        $("#globalSearchMeta").textContent = `Universal search failed: ${error.message}`;
      });
    }, 160);
  });
  window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openGlobalSearch();
    }
    if (event.key === "Escape" && !overlay.hidden) {
      closeGlobalSearch();
    }
  });
}

function bindSearch(formSelector, inputSelector, outputSelector) {
  const form = $(formSelector);
  const input = $(inputSelector);
  const output = $(outputSelector);
  let timer = null;

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (query) runSearch(query, output);
  });

  input.addEventListener("input", () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < 2) {
      output.innerHTML = "";
      return;
    }
    timer = setTimeout(() => runSearch(query, output), 250);
  });
}

function bindChat(formSelector, inputSelector, outputSelector) {
  const form = $(formSelector);
  const input = $(inputSelector);
  const output = $(outputSelector);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    if (formSelector === "#chatForm" && state.assistantMode === "reasoning") {
      runScientificReasoning(message, output);
      return;
    }
    if (formSelector === "#chatForm" && state.assistantMode === "knowledge") {
      runKnowledgeGraphAssistant(message, output);
      return;
    }
    runChat(message, output);
  });
}

function bindAssistantModeToggle() {
  $$(".assistant-mode").forEach((button) => {
    button.addEventListener("click", () => {
      state.assistantMode = button.dataset.assistantMode || "search";
      $$(".assistant-mode").forEach((node) => node.classList.remove("active"));
      button.classList.add("active");
    });
  });
}

function bindKnowledgeGraphQuestionButtons() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".ask-kg-button");
    if (!button) return;
    const question = button.dataset.question || "What do we know about this entity?";
    window.location.hash = "#/chat";
    state.assistantMode = "knowledge";
    $$(".assistant-mode").forEach((node) => {
      node.classList.toggle("active", node.dataset.assistantMode === "knowledge");
    });
    $("#chatInput").value = question;
    runKnowledgeGraphAssistant(question, $("#chatOutput"));
  });
}

function bindReasoning(formSelector, inputSelector, outputSelector) {
  const form = $(formSelector);
  const input = $(inputSelector);
  const output = $(outputSelector);
  if (!form || !input || !output) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (message) runScientificReasoning(message, output);
  });
}

function bindExperimentPlanner() {
  const form = $("#plannerForm");
  const input = $("#plannerInput");
  const output = $("#plannerOutput");
  if (!form || !input || !output) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (message) runExperimentPlanner(message, output);
  });
}

async function saveExperimentPlanDraft() {
  const plan = state.currentExperimentPlan;
  if (!plan) {
    $("#plannerStatus").textContent = "Generate a plan before saving it as a draft.";
    return;
  }
  const payload = await requestJson("/entries/save-draft", {
    method: "POST",
    body: JSON.stringify({
      title: plan.proposed_experiment_title,
      experiment_id: plan.structured?.experiment_id || null,
      template: "retinal_organoid",
      structured: plan.structured || {},
      markdown: plan.suggested_onenote_draft_entry,
      status: "draft",
    }),
  });
  await refreshData();
  $("#plannerStatus").textContent = `Saved local ResearchOS draft: ${payload.title}. OneNote write-back was not used.`;
  recordActivity("Saved planned experiment draft", payload.title);
}

function bindLiteratureComparison(buttonSelector, inputSelector, outputSelector) {
  const button = $(buttonSelector);
  const input = $(inputSelector);
  const output = $(outputSelector);
  if (!button || !input || !output) return;
  button.addEventListener("click", () => {
    const message = input.value.trim();
    if (message) runLiteratureComparison(message, output);
  });
}

function bindDashboardSuggestedQuestions() {
  $$(".suggested-question").forEach((button) => {
    button.addEventListener("click", () => {
      const question = button.dataset.question || button.textContent.trim();
      const mode = button.dataset.mode || "ask";
      const input = $("#dashboardChatInput");
      const output = $("#suggestedQuestionOutput");
      input.value = question;
      if (mode === "compare-literature") {
        runLiteratureComparison(question, output);
      } else {
        runChat(question, output);
      }
    });
  });
}

function bindSuggestedPrompts() {
  $$(".prompt-row").forEach((row) => {
    const targetId = row.dataset.promptTarget;
    const input = targetId ? document.getElementById(targetId) : null;
    if (!input) return;

    row.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        input.value = button.textContent.trim();
        input.focus();
      });
    });
  });
}

async function loadStatus() {
  try {
    state.health = await requestJson("/health");
  } catch (error) {
    state.health = null;
  }
  try {
    state.auth = await requestJson("/auth/status");
  } catch (error) {
    state.auth = null;
  }
  try {
    state.currentUser = await requestJson("/auth/me");
  } catch (error) {
    state.currentUser = null;
  }
  try {
    state.currentPermissions = await requestJson("/auth/permissions");
  } catch (error) {
    state.currentPermissions = null;
  }
  try {
    state.authReadiness = await requestJson("/auth/readiness");
  } catch (error) {
    state.authReadiness = null;
  }
  try {
    state.currentWorkspace = await requestJson("/workspaces/current");
  } catch (error) {
    state.currentWorkspace = null;
  }
  try {
    state.providerStatus = await requestJson("/status/providers");
  } catch (error) {
    state.providerStatus = null;
  }
  try {
    state.agentStatus = await requestJson("/agents");
  } catch (error) {
    state.agentStatus = null;
  }
  try {
    state.extensions = await requestJson("/extensions");
  } catch (error) {
    state.extensions = null;
  }
  try {
    state.deploymentStatus = await requestJson("/status/deployment");
  } catch (error) {
    state.deploymentStatus = null;
  }
  try {
    state.oneNoteReadiness = await requestJson("/status/onenote-readiness");
  } catch (error) {
    state.oneNoteReadiness = null;
  }
  try {
    state.productionReadiness = await requestJson("/status/production-readiness");
  } catch (error) {
    state.productionReadiness = null;
  }
  setStatus();
}

async function refreshData() {
  const [documents, papers, assets, spreadsheets, images, statistics, experiments, workflows, protocols, inventory, inventoryStatus, purchases, purchaseRequests, receiving, experimentDesigns, experimentDesignTemplates, plateLayouts, visualBuilders, designDueToday, designUpcoming, designImportTemplates, purchaseSummary, purchaseImportTemplates, sessions, pendingEntries, compounds, markers, cellLines, organoidBatches, graphStats, entryTemplates, dailyDashboard, whiteboard] = await Promise.all([
    requestJson("/documents"),
    requestJson("/papers"),
    requestJson("/assets"),
    requestJson("/spreadsheets"),
    requestJson("/images"),
    requestJson("/statistics"),
    requestJson("/experiments"),
    requestJson("/workflows"),
    requestJson("/protocols"),
    requestJson("/inventory"),
    requestJson("/inventory/status"),
    requestJson("/purchases"),
    requestJson("/purchase-requests"),
    requestJson("/receiving"),
    requestJson("/experiment-designs"),
    requestJson("/experiment-design-templates"),
    requestJson("/plate-layouts"),
    requestJson("/visual-experiment-builders"),
    requestJson("/experiment-designs/reminders/due-today"),
    requestJson("/experiment-designs/reminders/upcoming?days=7"),
    requestJson("/experiment-designs/import-templates"),
    requestJson("/purchases/summary"),
    requestJson("/purchases/import-templates"),
    requestJson("/sessions"),
    requestJson("/entries"),
    requestJson("/api/compounds"),
    requestJson("/api/markers"),
    requestJson("/api/cell-lines"),
    requestJson("/api/organoid-batches"),
    requestJson("/graph/stats"),
    requestJson("/entry-templates"),
    requestJson("/api/dashboard/daily?use_ai=false"),
    requestJson("/whiteboard"),
  ]);
  state.documents = documents;
  state.papers = papers;
  state.assets = assets;
  state.spreadsheets = spreadsheets;
  state.images = images;
  state.statistics = statistics;
  state.experiments = experiments;
  state.workflows = workflows;
  state.protocols = protocols;
  state.inventory = inventory;
  state.inventoryStatus = inventoryStatus;
  state.purchases = purchases;
  state.purchaseRequests = purchaseRequests;
  state.receiving = receiving;
  state.experimentDesigns = experimentDesigns;
  state.experimentDesignTemplates = experimentDesignTemplates;
  state.plateLayouts = plateLayouts;
  state.visualBuilders = visualBuilders;
  state.designDueToday = designDueToday;
  state.designUpcoming = designUpcoming;
  state.designImportTemplates = designImportTemplates;
  state.purchaseSummary = purchaseSummary;
  state.purchaseImportTemplates = purchaseImportTemplates;
  state.sessions = sessions;
  state.pendingEntries = pendingEntries;
  state.graphStats = graphStats;
  state.entryTemplates = entryTemplates;
  state.dailyDashboard = dailyDashboard;
  state.whiteboard = whiteboard;
  state.ontology = {
    compounds,
    markers,
    "cell-lines": cellLines,
    "organoid-batches": organoidBatches,
  };
  state.lastSync = new Date();
  renderAll();
}

function renderAll() {
  setStatus();
  renderWhiteboard();
  renderMorningBrief();
  renderDailyDashboard();
  renderCurrentSessionCard();
  renderMetrics();
  renderTimeline();
  renderRecentExperimentTimeline();
  renderRecentExperiments();
  renderPopularCompounds();
  renderOneNoteStatusCard();
  renderLiteratureStatusCard();
  renderAssetStatusCard();
  renderDocuments();
  renderAssets();
  renderSpreadsheets();
  renderImages();
  renderStatistics();
  renderPapers();
  renderProtocols();
  renderInventory();
  renderPurchases();
  renderReceiving();
  renderDesignPlanner();
  renderPlateLayouts();
  renderVisualBuilder();
  renderWorkflows();
  renderSessions();
  renderExperimentsTable();
  renderExtensions();
  renderProviderSettings();
  renderEntryTemplates();
  renderSavedDrafts();
  route();
}

function renderExtensions() {
  const target = $("#extensionCards");
  const marketplace = $("#extensionMarketplace");
  if (!target) return;
  const status = state.extensions;
  if (!status) {
    target.innerHTML = `<div class="empty-state">Extension registry is not available.</div>`;
    if (marketplace) marketplace.textContent = "Future ResearchOS extension marketplace is not implemented yet.";
    return;
  }
  const extensions = status.extensions || [];
  target.innerHTML = extensions.length
    ? extensions.map(renderExtensionCard).join("")
    : `<div class="empty-state">No extensions are installed.</div>`;
  if (marketplace) {
    marketplace.textContent = status.marketplace?.message || "Future ResearchOS extension marketplace is not implemented yet.";
  }
}

function renderExtensionCard(extension) {
  const capabilities = (extension.capabilities || []).join(", ") || "No capabilities declared";
  const contributions = extension.contributions || {};
  const contributionCount = Object.values(contributions).reduce((count, items) => count + (Array.isArray(items) ? items.length : 0), 0);
  return `
    <article class="provider-card">
      <div class="provider-card-header">
        <span>${escapeHtml(extension.name)}</span>
        <strong class="status-pill ${extension.enabled ? "ok" : "warn"}">${extension.enabled ? "Enabled" : "Disabled"}</strong>
      </div>
      <p>${escapeHtml(extension.description || "ResearchOS extension.")}</p>
      <small>${escapeHtml(extension.version)} · ${escapeHtml(extension.author)} · ${escapeHtml(capabilities)}</small>
      <div class="meta">
        <span class="tag">${escapeHtml(contributionCount)} contribution${contributionCount === 1 ? "" : "s"}</span>
        ${(extension.required_permissions || []).slice(0, 4).map((permission) => `<span class="tag">${escapeHtml(permission)}</span>`).join("")}
      </div>
    </article>
  `;
}

async function loadDemo() {
  $("#demoStatus").textContent = "Loading demo notes...";
  const result = await requestJson("/demo/reset", { method: "POST" });
  await loadStatus();
  await refreshData();
  recordActivity("Demo reset", `Loaded ${result.documents_ingested} notes and ${result.experiments_extracted} experiments`);
  $("#demoStatus").textContent = `Loaded ${result.documents_ingested} notes and ${result.experiments_extracted} experiments.`;
  const settingsStatus = $("#settingsActionStatus");
  if (settingsStatus) {
    settingsStatus.textContent = `Loaded ${result.documents_ingested} demo notes.`;
  }
}

async function extractExperiments() {
  $("#demoStatus").textContent = "Extracting experiments...";
  const result = await requestJson("/extract", {
    method: "POST",
    body: JSON.stringify({}),
  });
  await refreshData();
  recordActivity("Experiment extraction", `Scanned ${result.documents_scanned} documents`);
  $("#demoStatus").textContent = `Scanned ${result.documents_scanned} documents and extracted ${result.experiments_extracted} experiments.`;
}

async function ingestPapers() {
  const target = $("#literatureStatus");
  target.textContent = "Ingesting local papers...";
  const result = await requestJson("/ingest/papers", { method: "POST" });
  await refreshData();
  recordActivity("Paper ingestion", result.message || `Indexed ${result.documents_ingested} paper document(s)`);
  target.textContent = result.message || `Indexed ${result.documents_ingested} paper document(s).`;
}

function renderProductionReadinessSettings() {
  const target = $("#productionReadinessCards");
  if (!target) return;
  const readiness = state.productionReadiness;
  if (!readiness) {
    target.innerHTML = `<div class="empty-state">Production readiness status is not available.</div>`;
    return;
  }
  const modeStatus = readiness.app_env === "production" ? "configured" : "warn";
  target.innerHTML = [
    providerCard(
      "Current mode",
      modeStatus,
      `${readiness.app_env || "development"} / ${readiness.data_classification || "demo"}`,
      readiness.app_env === "production" ? "Production mode selected." : "Preview/dev mode: do not treat this as production deployment.",
    ),
    providerCard(
      "Core safety gates",
      readiness.auth_ready && readiness.https_ready && readiness.workspace_isolation_ready ? "configured" : "warn",
      `Auth: ${readiness.auth_ready ? "ready" : "not ready"} · HTTPS: ${readiness.https_ready ? "ready" : "not ready"} · Workspace isolation: ${readiness.workspace_isolation_ready ? "ready" : "metadata-only"}`,
      `Backups: ${readiness.backup_ready ? "ready" : "missing"} · Audit logs: ${readiness.audit_log_ready ? "ready" : "missing"}`,
    ),
    providerCard(
      "OneNote and AI",
      readiness.onenote_write_disabled ? "active" : "warn",
      `OneNote read: ${readiness.onenote_read_ready ? "ready" : "not ready"} · Write-back: ${readiness.onenote_write_disabled ? "disabled" : "enabled"}`,
      `AI provider: ${readiness.ai_provider_configured ? "configured" : "not configured"}`,
    ),
    providerCard(
      "Production warnings",
      readiness.warnings?.length ? "warn" : "configured",
      readiness.warnings?.length ? `${readiness.warnings.length} warning(s)` : "No production readiness warnings.",
      (readiness.warnings || []).join(" · ") || "All configured production checks passed.",
    ),
    providerCard(
      "Recommended next steps",
      readiness.recommended_next_steps?.length ? "active" : "configured",
      readiness.recommended_next_steps?.length ? `${readiness.recommended_next_steps.length} next step(s)` : "No next steps reported.",
      (readiness.recommended_next_steps || []).join(" · "),
    ),
  ].join("");
}

async function syncOneNoteFromSettings() {
  const target = $("#settingsActionStatus");
  target.textContent = "Starting read-only OneNote sync...";
  try {
    const result = await requestJson("/sync/onenote", { method: "POST" });
    await loadStatus();
    await refreshData();
    target.textContent = `Synced ${result.documents_ingested} OneNote pages and extracted ${result.experiments_extracted} experiments.`;
  } catch (error) {
    await loadStatus();
    renderProviderSettings();
    target.textContent = `OneNote sync failed: ${error.message}`;
  }
}

async function testAiFromSettings() {
  const target = $("#settingsActionStatus");
  target.textContent = "Testing AI chat...";
  try {
    const payload = await requestJson("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: "Reply with one short sentence confirming ResearchOS AI chat is configured.",
        use_search_context: false,
      }),
    });
    target.textContent = `AI provider responded: ${shortText(payload.answer, 180)}`;
  } catch (error) {
    await loadStatus();
    renderProviderSettings();
    target.textContent = `AI test failed: ${error.message}`;
  }
}

$("#loadDemoButton").addEventListener("click", () => {
  loadDemo().catch((error) => {
    $("#demoStatus").textContent = `Demo load failed: ${error.message}`;
  });
});

$("#loadPapersButton").addEventListener("click", () => {
  ingestPapers().catch((error) => {
    $("#demoStatus").textContent = `Paper ingestion failed: ${error.message}`;
  });
});

const sampleDictations = {
  sag_grki: {
    template: "retinal_organoid",
    text: (
      "Create NK Expt 31. Date today. Researcher Nathan. Day 1 SAG plus GRK inhibitor rescue. "
      + "Objective: test whether SAG with GRKi improves early retinal organoid patterning. "
      + "Cell line SIX6 reporter iPSC line. Organoid batch RO-NK-31. Differentiation day D18. "
      + "Treatment schedule: add 100 nM SAG and 250 nM GRK inhibitor from D18 to D24 during media changes. "
      + "DMSO vehicle control. Planned readouts brightfield, SIX6 fluorescence, BRN3B staining at D32. "
      + "Observed smooth rims in treated wells. Issues: one well had partial detachment. "
      + "Next steps quantify SIX6 intensity and repeat with three organoids per condition."
    ),
  },
  bmp4_pulse: {
    template: "retinal_organoid",
    text: (
      "Create BMP4 Expt 12. Researcher Nathan. Objective: test whether a short BMP4 pulse improves retinal vesicle emergence. "
      + "Cell line SIX6 reporter iPSC line. Organoid batch RO-BMP4-12. Differentiation day D16. "
      + "Treatment schedule: pulse 1.5 nM BMP4 from D16 to D20, then wash out at media change. "
      + "Controls: matched no BMP4 control and standard media change control. "
      + "Planned readouts brightfield morphology, SIX6 reporter intensity, and PAX6 staining. "
      + "Observations: treated aggregates looked slightly more symmetric. Next steps image again at D24."
    ),
  },
  immunostaining: {
    template: "immunostaining",
    text: (
      "Create stain Expt 08. Researcher Nathan. Immunostaining result for D32 retinal organoids from SAG comparison. "
      + "Objective: assess progenitor and retinal ganglion cell markers after SAG treatment. "
      + "Organoid batch RO-SAG-24A. Markers SIX6, BRN3B, DAPI. "
      + "Conditions: vehicle and SAG-treated. Planned readouts confocal imaging and marker localization. "
      + "Observations: SIX6 was broad in outer neuroepithelium and BRN3B-positive cells were sparse but organized near the inner surface. "
      + "Issues: BRN3B background was higher than expected. Next steps repeat with longer blocking and secondary-only control."
    ),
  },
  imaging: {
    template: "imaging_session",
    text: (
      "Create imaging session IS-04. Date today. Researcher Nathan. Objective: capture D24 brightfield and fluorescence overview images. "
      + "Cell line SIX6 reporter iPSC line. Organoid batch RO-SAG-24A. Differentiation day D24. "
      + "Conditions: vehicle, SAG, and SAG plus GRKi. Planned readouts brightfield morphology and SIX6 fluorescence. "
      + "Observations: SAG plus GRKi wells had smoother rims, but one field was out of focus. "
      + "Issues: autofocus drift on the last plate. Next steps reimage plate two tomorrow and export representative TIFFs."
    ),
  },
};

$$(".sample-dictation").forEach((button) => {
  button.addEventListener("click", () => {
    const sample = sampleDictations[button.dataset.sample];
    if (!sample) return;
    state.currentSavedEntryId = null;
    $("#entryTemplateSelect").value = sample.template;
    $("#entryDictation").value = sample.text;
    $("#entryDictation").focus();
  });
});

$("#entryDraftForm").addEventListener("submit", (event) => {
  event.preventDefault();
  generateEntryDraft().catch((error) => {
    $("#entryDraftStatus").textContent = `Draft failed: ${error.message}`;
    $("#entryDraftStatus").className = "status-pill";
  });
});

$("#saveDraftButton").addEventListener("click", () => {
  saveCurrentDraft("draft").catch((error) => {
    $("#entryExportStatus").textContent = `Save failed: ${error.message}`;
  });
});

$("#markReadyButton").addEventListener("click", () => {
  saveCurrentDraft("ready_for_onenote").catch((error) => {
    $("#entryExportStatus").textContent = `Status update failed: ${error.message}`;
  });
});

$("#copyMarkdownButton").addEventListener("click", () => {
  copyEntryMarkdown().catch((error) => {
    $("#entryExportStatus").textContent = `Copy failed: ${error.message}`;
  });
});

$("#downloadMarkdownButton").addEventListener("click", () => {
  downloadEntryMarkdown().catch((error) => {
    $("#entryExportStatus").textContent = `Download failed: ${error.message}`;
  });
});

$("#previewOneNoteButton").addEventListener("click", () => {
  previewOneNoteEntry();
});

$("#extractButton").addEventListener("click", () => {
  extractExperiments().catch((error) => {
    $("#demoStatus").textContent = `Extraction failed: ${error.message}`;
  });
});

$("#compareSelectedButton").addEventListener("click", () => {
  compareSelectedExperiments().catch((error) => {
    $("#comparisonStatus").textContent = `Comparison failed: ${error.message}`;
  });
});

$("#ingestPapersButton").addEventListener("click", () => {
  ingestPapers().catch((error) => {
    $("#literatureStatus").textContent = `Paper ingestion failed: ${error.message}`;
  });
});

$("#refreshGraphButton").addEventListener("click", () => {
  refreshData().catch(() => {
    $("#graphStats").innerHTML = `<div class="empty-state">Graph refresh failed.</div>`;
  });
});

$("#settingsLoadDemoButton").addEventListener("click", () => {
  loadDemo().catch((error) => {
    $("#settingsActionStatus").textContent = `Demo load failed: ${error.message}`;
  });
});

$("#settingsSyncOneNoteButton").addEventListener("click", () => {
  syncOneNoteFromSettings();
});

$("#settingsTestAiButton").addEventListener("click", () => {
  testAiFromSettings();
});

$("#settingsApprovalButton").addEventListener("click", () => {
  const approvalInfo = $("#approvalInfo");
  approvalInfo.hidden = !approvalInfo.hidden;
});
$("#agentCards")?.addEventListener("click", (event) => {
  const button = event.target.closest(".agent-toggle");
  if (!button) return;
  const agentId = button.dataset.agentId;
  const action = button.dataset.agentAction;
  requestJson(`/agents/${encodeURIComponent(agentId)}/${action}`, { method: "POST" })
    .then((status) => {
      state.agentStatus = status;
      renderAgentSettings();
      $("#settingsActionStatus").textContent = `${action === "enable" ? "Enabled" : "Disabled"} ${agentId}.`;
    })
    .catch((error) => {
      $("#settingsActionStatus").textContent = `Agent update failed: ${error.message}`;
    });
});

$("#assetTypeFilter")?.addEventListener("change", renderAssets);
$("#assetSearchInput")?.addEventListener("input", renderAssets);
$("#inventorySearchInput")?.addEventListener("input", renderInventory);
$("#inventoryCategoryFilter")?.addEventListener("input", renderInventory);
$("#inventoryVendorFilter")?.addEventListener("input", renderInventory);
$("#inventoryLocationFilter")?.addEventListener("input", renderInventory);
$("#purchaseSearchInput")?.addEventListener("input", renderPurchases);
$("#purchaseVendorFilter")?.addEventListener("input", renderPurchases);
$("#purchaseGrantFilter")?.addEventListener("input", renderPurchases);
$("#purchaseStatusFilter")?.addEventListener("input", renderPurchases);
$("#inventoryForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  saveInventoryItem().catch((error) => {
    $("#inventoryStatus").textContent = `Inventory save failed: ${error.message}`;
  });
});
$("#purchaseForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  savePurchaseRecord().catch((error) => {
    $("#purchaseStatusMessage").textContent = `Purchase save failed: ${error.message}`;
  });
});
$("#receivingForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  saveReceivingRecord().catch((error) => {
    $("#receivingStatus").textContent = `Receiving save failed: ${error.message}`;
  });
});
$("#receivingList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-receiving-intake]");
  if (!button) return;
  intakeReceivingRecord(button.dataset.receivingIntake).catch((error) => {
    $("#receivingStatus").textContent = `Inventory intake failed: ${error.message}`;
  });
});
$("#designForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  saveExperimentDesign().catch((error) => {
    $("#designPlannerStatus").textContent = `Design save failed: ${error.message}`;
  });
});
$("#designConditionForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  addDesignCondition().catch((error) => {
    $("#designPlannerStatus").textContent = `Condition save failed: ${error.message}`;
  });
});
$("#designEventForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  addDesignEvent().catch((error) => {
    $("#designPlannerStatus").textContent = `Event save failed: ${error.message}`;
  });
});
$("#designImportPreviewButton")?.addEventListener("click", () => {
  previewDesignImport().catch((error) => {
    $("#designPlannerStatus").textContent = `Import preview failed: ${error.message}`;
  });
});
$("#saveDesignTemplateButton")?.addEventListener("click", () => {
  saveDesignImportTemplate().catch((error) => {
    $("#designPlannerStatus").textContent = `Template save failed: ${error.message}`;
  });
});
$("#designImportPreview")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-design-template]");
  if (!button) return;
  try {
    const mapping = JSON.parse(button.dataset.designTemplate || "{}");
    Object.entries(mapping).forEach(([field, column]) => {
      const input = document.querySelector(`[data-design-map-field="${CSS.escape(field)}"]`);
      if (input) input.value = column;
    });
    $("#designPlannerStatus").textContent = "Applied design import template.";
  } catch (error) {
    $("#designPlannerStatus").textContent = `Template apply failed: ${error.message}`;
  }
});
$("#designImportForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  importDesignCsv().catch((error) => {
    $("#designPlannerStatus").textContent = `Design import failed: ${error.message}`;
  });
});
$("#designList")?.addEventListener("click", (event) => {
  const saveTemplate = event.target.closest("[data-save-design-template]");
  const generateLayout = event.target.closest("[data-generate-plate-layout]");
  if (saveTemplate) {
    saveCurrentDesignAsTemplate(saveTemplate.dataset.saveDesignTemplate).catch((error) => {
      $("#designPlannerStatus").textContent = `Save template failed: ${error.message}`;
    });
  }
  if (generateLayout) {
    generatePlateLayout(generateLayout.dataset.generatePlateLayout).catch((error) => {
      $("#designPlannerStatus").textContent = `Generate layout failed: ${error.message}`;
    });
  }
});
$("#plateLayoutList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-edit-well]");
  if (!button) return;
  editPlateWell(button.dataset.editWell, button.dataset.position).catch((error) => {
    alert(`Plate layout edit failed: ${error.message}`);
  });
});
$("#visualBuilderSeedButton")?.addEventListener("click", () => {
  snapshotVisualBuilder();
  seedVisualBuilderDraft();
  renderVisualBuilder();
});
$("#visualBuilderAddBranchButton")?.addEventListener("click", duplicateVisualBranch);
$("#visualBuilderSaveButton")?.addEventListener("click", () => {
  saveVisualBuilder().catch((error) => {
    $("#visualBuilderStatus").textContent = `Save failed: ${error.message}`;
  });
});
$("#visualBuilderGenerateButton")?.addEventListener("click", () => {
  generateVisualBuilderDesign().catch((error) => {
    $("#visualBuilderStatus").textContent = `Generate failed: ${error.message}`;
  });
});
$("#visualBuilderUndoButton")?.addEventListener("click", () => {
  if (!state.visualBuilderUndo.length) return;
  state.visualBuilderRedo.push(JSON.stringify(visualBuilderDraft()));
  state.visualBuilderDraft = JSON.parse(state.visualBuilderUndo.pop());
  renderVisualBuilder();
});
$("#visualBuilderRedoButton")?.addEventListener("click", () => {
  if (!state.visualBuilderRedo.length) return;
  state.visualBuilderUndo.push(JSON.stringify(visualBuilderDraft()));
  state.visualBuilderDraft = JSON.parse(state.visualBuilderRedo.pop());
  renderVisualBuilder();
});
$("#visualBuilderCanvas")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-visual-node]");
  if (!button) return;
  const draft = visualBuilderDraft();
  const node = draft.nodes.find((item) => item.node_id === button.dataset.visualNode);
  if (!node) return;
  const action = window.prompt(`Edit ${node.label}: rename, delete, or duplicate`, "rename");
  if (action === null) return;
  snapshotVisualBuilder();
  if (action === "delete") {
    draft.nodes = draft.nodes.filter((item) => item.node_id !== node.node_id);
    draft.connections = draft.connections.filter((item) => item.source !== node.node_id && item.target !== node.node_id);
  } else if (action === "duplicate") {
    const clone = { ...node, node_id: `${node.node_id}_copy_${Date.now()}`, label: `${node.label} copy`, x: Number(node.x || 0) + 40, y: Number(node.y || 0) + 70 };
    draft.nodes.push(clone);
  } else {
    const label = window.prompt("Node label", node.label);
    if (label !== null) node.label = label;
  }
  renderVisualBuilder();
});
$("#visualBuilderList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-load-visual-builder]");
  if (!button) return;
  const builder = (state.visualBuilders || []).find((item) => item.builder_id === button.dataset.loadVisualBuilder);
  if (!builder) return;
  snapshotVisualBuilder();
  state.visualBuilderDraft = {
    title: builder.title,
    description: builder.description,
    nodes: builder.nodes || [],
    connections: builder.connections || [],
  };
  renderVisualBuilder();
});
$("#designTemplateList")?.addEventListener("click", (event) => {
  const createButton = event.target.closest("[data-create-design-template]");
  const deleteButton = event.target.closest("[data-delete-design-template]");
  if (createButton) {
    createDesignFromTemplate(createButton.dataset.createDesignTemplate).catch((error) => {
      alert(`Create from template failed: ${error.message}`);
    });
  }
  if (deleteButton) {
    deleteDesignTemplate(deleteButton.dataset.deleteDesignTemplate).catch((error) => {
      alert(`Delete template failed: ${error.message}`);
    });
  }
});
$("#checkDesignBalanceButton")?.addEventListener("click", () => {
  checkSelectedDesignBalance().catch((error) => {
    $("#designPlannerStatus").textContent = `Balance check failed: ${error.message}`;
  });
});
$("#dailyDashboardCards")?.addEventListener("click", (event) => {
  const complete = event.target.closest("[data-design-reminder-complete]");
  const dismiss = event.target.closest("[data-design-reminder-dismiss]");
  if (complete) {
    updateDesignReminder(complete.dataset.designReminderComplete, "complete").catch((error) => {
      $("#dailyDashboardSummary").textContent = `Reminder completion failed: ${error.message}`;
    });
  }
  if (dismiss) {
    updateDesignReminder(dismiss.dataset.designReminderDismiss, "dismiss").catch((error) => {
      $("#dailyDashboardSummary").textContent = `Reminder dismiss failed: ${error.message}`;
    });
  }
});
$("#purchaseRequestForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  savePurchaseRequest().catch((error) => {
    $("#purchaseStatusMessage").textContent = `Purchase request save failed: ${error.message}`;
  });
});
$("#purchaseRequestsList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-purchase-request-action]");
  if (!button) return;
  updatePurchaseRequestStatus(button.dataset.purchaseRequestId, button.dataset.purchaseRequestAction).catch((error) => {
    $("#purchaseStatusMessage").textContent = `Purchase request update failed: ${error.message}`;
  });
});
$("#purchaseImportForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  importPurchaseCsv().catch((error) => {
    $("#purchaseStatusMessage").textContent = `CSV import failed: ${error.message}`;
  });
});
$("#purchasePreviewButton")?.addEventListener("click", () => {
  previewMappedPurchaseCsv().catch((error) => {
    $("#purchaseStatusMessage").textContent = `Import preview failed: ${error.message}`;
  });
});
$("#purchaseMappedImportForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  importMappedPurchaseCsv().catch((error) => {
    $("#purchaseStatusMessage").textContent = `Mapped CSV import failed: ${error.message}`;
  });
});
$("#savePurchaseTemplateButton")?.addEventListener("click", () => {
  savePurchaseImportTemplate().catch((error) => {
    $("#purchaseStatusMessage").textContent = `Template save failed: ${error.message}`;
  });
});
$("#purchaseTemplateSelect")?.addEventListener("change", (event) => {
  const template = (state.purchaseImportTemplates || []).find((item) => item.template_id === event.target.value);
  if (template) applyPurchaseMappingToForm(template.mapping || {});
});
$("#inventoryList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inventory-citation]");
  if (!button) return;
  showMethodsCitation(button.dataset.inventoryCitation).catch((error) => {
    $("#inventoryStatus").textContent = `Citation failed: ${error.message}`;
  });
});
$("#inventoryList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inventory-copy-citation]");
  if (!button) return;
  copyMethodsCitation(button.dataset.inventoryCopyCitation).catch((error) => {
    $("#inventoryStatus").textContent = `Copy failed: ${error.message}`;
  });
});
$("#inventoryList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inventory-usage]");
  if (!button) return;
  showInventoryUsage(button.dataset.inventoryUsage).catch((error) => {
    $("#inventoryStatus").textContent = `Usage history failed: ${error.message}`;
  });
});
$("#inventoryList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inventory-assign-code]");
  if (!button) return;
  assignInventoryCode(button.dataset.inventoryAssignCode).catch((error) => {
    $("#inventoryStatus").textContent = `Code assignment failed: ${error.message}`;
  });
});
$("#inventoryList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inventory-label]");
  if (!button) return;
  showInventoryLabel(button.dataset.inventoryLabel).catch((error) => {
    $("#inventoryStatus").textContent = `Label preview failed: ${error.message}`;
  });
});
$("#inventoryList")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-inventory-request-reorder]");
  if (!button) return;
  requestInventoryReorder(button.dataset.inventoryRequestReorder).catch((error) => {
    $("#inventoryStatus").textContent = `Reorder request failed: ${error.message}`;
  });
});
$("#experimentDetail")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-generate-methods]");
  if (!button) return;
  generateExperimentMethodsText(button.dataset.generateMethods).catch((error) => {
    const target = $("#methodsMaterialsText");
    if (target) target.textContent = `Methods generation failed: ${error.message}`;
  });
});
$("#imageMarkerFilter")?.addEventListener("change", renderImages);
$("#scanGraphPadButton")?.addEventListener("click", () => {
  scanGraphPadAssets().catch((error) => {
    $("#graphPadScanStatus").textContent = `GraphPad scan failed: ${error.message}`;
  });
});
$("#scanGraphPadStatsButton")?.addEventListener("click", () => {
  scanGraphPadAssets().catch((error) => {
    $("#statisticsStatus").textContent = `GraphPad scan failed: ${error.message}`;
  });
});
$("#scanImagesButton")?.addEventListener("click", () => {
  scanImageAssets().catch((error) => {
    $("#imagesScanStatus").textContent = `Image scan failed: ${error.message}`;
  });
});
$("#scanSpreadsheetsButton")?.addEventListener("click", () => {
  scanSpreadsheetAssets().catch((error) => {
    $("#spreadsheetsStatus").textContent = `Spreadsheet scan failed: ${error.message}`;
  });
});
$("#savePlanDraftButton")?.addEventListener("click", () => {
  saveExperimentPlanDraft().catch((error) => {
    $("#plannerStatus").textContent = `Could not save plan draft: ${error.message}`;
  });
});
$("#sessionStartForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  startExperimentSession().catch((error) => {
    $("#sessionStatus").textContent = `Could not start session: ${error.message}`;
  });
});
$("#endSessionButton")?.addEventListener("click", () => {
  endActiveSession().catch((error) => {
    $("#sessionStatus").textContent = `Could not end session: ${error.message}`;
  });
});

bindSearch("#dashboardSearchForm", "#dashboardSearchInput", "#dashboardSearchResults");
bindSearch("#searchForm", "#searchInput", "#searchResults");
bindChat("#dashboardChatForm", "#dashboardChatInput", "#dashboardChatOutput");
bindChat("#chatForm", "#chatInput", "#chatOutput");
bindReasoning("#reasoningForm", "#reasoningInput", "#reasoningOutput");
bindExperimentPlanner();
bindLiteratureComparison("#dashboardCompareLiteratureButton", "#dashboardChatInput", "#dashboardChatOutput");
bindLiteratureComparison("#compareLiteratureButton", "#chatInput", "#chatOutput");
bindDashboardSuggestedQuestions();
bindSuggestedPrompts();
bindAssistantModeToggle();
bindKnowledgeGraphQuestionButtons();
bindUniversalSearch();
setupVoiceDictation();
registerServiceWorker();

window.addEventListener("hashchange", route);
window.setInterval(() => {
  renderSessionTimer();
  renderCurrentSessionCard();
}, 30000);
window.setInterval(async () => {
  if (!window.location.hash.startsWith("#/whiteboard")) return;
  try {
    state.whiteboard = await requestJson("/whiteboard");
    const rotation = state.whiteboard?.rotation || [];
    if (rotation.length) {
      state.whiteboardRotationIndex = (state.whiteboardRotationIndex + 1) % rotation.length;
    }
    renderWhiteboard();
  } catch {
    // Keep the last rendered whiteboard visible if a refresh fails.
  }
}, 60000);

async function boot() {
  await loadStatus();
  await refreshData();
}

boot().catch(() => {
  setStatus();
});
