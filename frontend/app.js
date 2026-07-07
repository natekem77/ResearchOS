const state = {
  documents: [],
  papers: [],
  assets: [],
  spreadsheets: [],
  images: [],
  statistics: [],
  experiments: [],
  selectedExperimentIds: new Set(),
  health: null,
  auth: null,
  providerStatus: null,
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
  "new-experiment": $("#newExperimentView"),
  "saved-drafts": $("#savedDraftsView"),
  savedDraftDetail: $("#savedDraftDetailView"),
  experiments: $("#experimentsView"),
  experimentDetail: $("#experimentDetailView"),
  protocols: $("#protocolsView"),
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
    "new-experiment": ["New Experiment", "Dictation Draft"],
    "saved-drafts": ["Saved Drafts", "Pending Notebook Entries"],
    experiments: ["Experiments", "Experiment Index"],
    protocols: ["Protocols", "Protocol Signals"],
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

function protocolDocuments() {
  return state.documents.filter((document) => /protocol/i.test(document.title));
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
  const protocols = protocolDocuments();
  $("#protocolsList").innerHTML = protocols.length
    ? protocols
        .map(
          (document) => `
            <article class="record-card">
              <h3><a href="${graphEntityLink("protocols", document.id, document.title)}">${escapeHtml(document.title)}</a></h3>
              <p>${escapeHtml(document.source_path || document.source_id)}</p>
              <div class="meta"><span class="tag">${escapeHtml(document.provider)}</span></div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No protocols detected.</div>`;
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
      <div class="detail-grid">
        ${detailField("Date", formatDate(experiment.date))}
        ${detailField("Researcher", experiment.researcher)}
        ${detailField("Cell line", experiment.cell_line)}
        ${detailField("Organoid batch", experiment.organoid_batch)}
      </div>
      ${tagSection("Compounds", workspace.compounds || [], "compounds")}
      ${tagSection("Markers", workspace.markers || [], "markers")}
      ${tagSection("Genes", workspace.genes || [], "genes")}
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
    state.providerStatus = await requestJson("/status/providers");
  } catch (error) {
    state.providerStatus = null;
  }
  setStatus();
}

async function refreshData() {
  const [documents, papers, assets, spreadsheets, images, statistics, experiments, pendingEntries, compounds, markers, cellLines, organoidBatches, graphStats, entryTemplates] = await Promise.all([
    requestJson("/documents"),
    requestJson("/papers"),
    requestJson("/assets"),
    requestJson("/spreadsheets"),
    requestJson("/images"),
    requestJson("/statistics"),
    requestJson("/experiments"),
    requestJson("/entries"),
    requestJson("/api/compounds"),
    requestJson("/api/markers"),
    requestJson("/api/cell-lines"),
    requestJson("/api/organoid-batches"),
    requestJson("/graph/stats"),
    requestJson("/entry-templates"),
  ]);
  state.documents = documents;
  state.papers = papers;
  state.assets = assets;
  state.spreadsheets = spreadsheets;
  state.images = images;
  state.statistics = statistics;
  state.experiments = experiments;
  state.pendingEntries = pendingEntries;
  state.graphStats = graphStats;
  state.entryTemplates = entryTemplates;
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
  renderExperimentsTable();
  renderProviderSettings();
  renderEntryTemplates();
  renderSavedDrafts();
  route();
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

$("#assetTypeFilter")?.addEventListener("change", renderAssets);
$("#assetSearchInput")?.addEventListener("input", renderAssets);
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
setupVoiceDictation();
registerServiceWorker();

window.addEventListener("hashchange", route);

async function boot() {
  await loadStatus();
  await refreshData();
}

boot().catch(() => {
  setStatus();
});
