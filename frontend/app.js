const state = {
  documents: [],
  papers: [],
  experiments: [],
  selectedExperimentIds: new Set(),
  health: null,
  auth: null,
  providerStatus: null,
  ontology: {},
  lastSync: null,
  searchTerms: [],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const views = {
  dashboard: $("#dashboardView"),
  experiments: $("#experimentsView"),
  experimentDetail: $("#experimentDetailView"),
  protocols: $("#protocolsView"),
  documents: $("#documentsView"),
  literature: $("#literatureView"),
  entityList: $("#entityListView"),
  entityDetail: $("#entityDetailView"),
  search: $("#searchView"),
  chat: $("#chatView"),
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

function route() {
  const pathView = window.location.pathname.replace(/^\//, "");
  const raw = window.location.hash.replace(/^#\/?/, "") || pathView || "dashboard";
  const [view, id] = raw.split("/");

  $$(".view").forEach((node) => node.classList.remove("active"));
  $$(".side-nav a").forEach((node) => node.classList.remove("active"));

  if (view === "experiments" && id) {
    views.experimentDetail.classList.add("active");
    $("[data-nav='experiments']").classList.add("active");
    renderExperimentDetail(decodeURIComponent(id));
    setHeader("Experiment Detail", "Experiment record");
    return;
  }

  if (["compounds", "markers", "cell-lines", "organoid-batches"].includes(view)) {
    const entityType = view;
    if (id) {
      views.entityDetail.classList.add("active");
      const nav = $(`[data-nav='${entityType}']`);
      if (nav) nav.classList.add("active");
      renderEntityDetail(entityType, decodeURIComponent(id));
      setHeader("Retinal Ontology", decodeURIComponent(id));
      return;
    }
    views.entityList.classList.add("active");
    const nav = $(`[data-nav='${entityType}']`);
    if (nav) nav.classList.add("active");
    renderEntityList(entityType);
    setHeader("Retinal Ontology", entityTitle(entityType));
    return;
  }

  const target = views[view] ? view : "dashboard";
  views[target].classList.add("active");
  const nav = $(`[data-nav='${target}']`);
  if (nav) nav.classList.add("active");

  const titles = {
    dashboard: ["Dashboard", "ResearchOS Dashboard"],
    experiments: ["Experiments", "Experiment Index"],
    protocols: ["Protocols", "Protocol Signals"],
    documents: ["Documents", "Document Library"],
    literature: ["Literature", "Paper Library"],
    search: ["Search", "Search Research Notes"],
    chat: ["AI Chat", "Ask ResearchOS"],
    settings: ["Settings", "Workspace Settings"],
  };
  setHeader(...titles[target]);
}

function allCompounds() {
  return (state.ontology.compounds || []).map((entity) => entity.name);
}

function protocolDocuments() {
  return state.documents.filter((document) => /protocol/i.test(document.title));
}

function renderMetrics() {
  $("#metricExperiments").textContent = state.experiments.length;
  $("#metricDocuments").textContent = state.documents.length;
  $("#metricProtocols").textContent = protocolDocuments().length;
  $("#metricCompounds").textContent = allCompounds().length;
  $("#metricLastSync").textContent = state.lastSync ? state.lastSync.toLocaleTimeString() : "Never";
}

function renderTimeline() {
  const items = [
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
    : `<div class="empty-state">No activity yet. Load demo notes to begin.</div>`;
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
    : `<div class="empty-state">No experiments extracted.</div>`;
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
            `<a class="compound-chip" href="#/compounds/${encodeURIComponent(name)}">${escapeHtml(name)} <small>${count}</small></a>`,
        )
        .join("")
    : `<div class="empty-state">No compounds detected.</div>`;
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
    : `<div class="empty-state">No documents indexed.</div>`;
}

function renderPapers() {
  $("#papersList").innerHTML = state.papers.length
    ? state.papers
        .map(
          (paper) => `
            <article class="record-card">
              <h3>${escapeHtml(paper.title)}</h3>
              <p>${escapeHtml(shortText(paper.abstract || paper.source_path || "No abstract detected.", 260))}</p>
              <div class="meta">
                ${paper.year ? `<span class="tag">${escapeHtml(paper.year)}</span>` : ""}
                ${paper.journal ? `<span class="tag">${escapeHtml(paper.journal)}</span>` : ""}
                ${paper.doi ? `<span class="tag">${escapeHtml(paper.doi)}</span>` : ""}
              </div>
              <div class="meta">
                ${(paper.compounds || []).map((value) => `<span class="mini-chip">${escapeHtml(value)}</span>`).join("")}
                ${(paper.markers || []).map((value) => `<span class="mini-chip">${escapeHtml(value)}</span>`).join("")}
                ${(paper.methods || []).map((value) => `<span class="mini-chip">${escapeHtml(value)}</span>`).join("")}
              </div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No literature indexed. Add .pdf, .txt, or .md files under samples/papers or data/papers, then ingest papers.</div>`;
}

function renderProtocols() {
  const protocols = protocolDocuments();
  $("#protocolsList").innerHTML = protocols.length
    ? protocols
        .map(
          (document) => `
            <article class="record-card">
              <h3>${escapeHtml(document.title)}</h3>
              <p>${escapeHtml(document.source_path || document.source_id)}</p>
              <div class="meta"><span class="tag">${escapeHtml(document.provider)}</span></div>
            </article>
          `,
        )
        .join("")
    : `<div class="empty-state">No protocols detected yet.</div>`;
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
              <td>${(experiment.compounds || []).map((value) => `<span class="mini-chip">${escapeHtml(value)}</span>`).join("")}</td>
              <td>${(experiment.markers || []).map((value) => `<span class="mini-chip">${escapeHtml(value)}</span>`).join("")}</td>
              <td>${escapeHtml(experiment.source_provider)}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="7">No experiments extracted.</td></tr>`;

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
  $("#experimentDetail").innerHTML = `
    <a class="inline-link" href="#/experiments">Back to experiments</a>
    <div class="detail-header">
      <div>
        <p class="eyebrow">${escapeHtml(experiment.experiment_id || experiment.id)}</p>
        <h2>${escapeHtml(experiment.title)}</h2>
      </div>
      <span class="status-pill ok">${escapeHtml(experiment.source_provider)}</span>
    </div>
    <div class="detail-grid">
      ${detailField("Date", formatDate(experiment.date))}
      ${detailField("Researcher", experiment.researcher)}
      ${detailField("Cell line", experiment.cell_line)}
      ${detailField("Organoid batch", experiment.organoid_batch)}
      ${detailField("Original document", source?.source_path || source?.source_id || experiment.source_document_id)}
    </div>
    ${tagSection("Compounds", experiment.compounds)}
    ${tagSection("Markers", experiment.markers)}
    ${tagSection("Time points", experiment.time_points)}
    ${textSection("Notes", experiment.notes)}
    ${textSection("Conclusions", experiment.conclusions)}
  `;
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
    ${linkedSection("Images", entity.images, (image) => `<article class="record-card"><h3>${escapeHtml(image.title || "Image")}</h3></article>`)}
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

function tagSection(title, values = []) {
  return `
    <section class="detail-section">
      <h3>${escapeHtml(title)}</h3>
      <div class="tag-row">${values.length ? values.map((value) => `<span class="tag">${escapeHtml(value)}</span>`).join("") : `<span class="muted">None captured</span>`}</div>
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
    if (message) runChat(message, output);
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
  const [documents, papers, experiments, compounds, markers, cellLines, organoidBatches] = await Promise.all([
    requestJson("/documents"),
    requestJson("/papers"),
    requestJson("/experiments"),
    requestJson("/api/compounds"),
    requestJson("/api/markers"),
    requestJson("/api/cell-lines"),
    requestJson("/api/organoid-batches"),
  ]);
  state.documents = documents;
  state.papers = papers;
  state.experiments = experiments;
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
  renderRecentExperiments();
  renderPopularCompounds();
  renderDocuments();
  renderPapers();
  renderProtocols();
  renderExperimentsTable();
  renderProviderSettings();
  route();
}

async function loadDemo() {
  $("#demoStatus").textContent = "Loading demo notes...";
  const result = await requestJson("/demo/reset", { method: "POST" });
  await loadStatus();
  await refreshData();
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
  $("#demoStatus").textContent = `Scanned ${result.documents_scanned} documents and extracted ${result.experiments_extracted} experiments.`;
}

async function ingestPapers() {
  const target = $("#literatureStatus");
  target.textContent = "Ingesting local papers...";
  const result = await requestJson("/ingest/papers", { method: "POST" });
  await refreshData();
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

bindSearch("#dashboardSearchForm", "#dashboardSearchInput", "#dashboardSearchResults");
bindSearch("#searchForm", "#searchInput", "#searchResults");
bindChat("#dashboardChatForm", "#dashboardChatInput", "#dashboardChatOutput");
bindChat("#chatForm", "#chatInput", "#chatOutput");
bindSuggestedPrompts();

window.addEventListener("hashchange", route);

async function boot() {
  await loadStatus();
  await refreshData();
}

boot().catch(() => {
  setStatus();
});
