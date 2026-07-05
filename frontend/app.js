const state = {
  documents: [],
  experiments: [],
};

const connectionStatus = document.querySelector("#connectionStatus");
const documentsList = document.querySelector("#documentsList");
const experimentsList = document.querySelector("#experimentsList");
const documentCount = document.querySelector("#documentCount");
const experimentCount = document.querySelector("#experimentCount");
const searchForm = document.querySelector("#searchForm");
const searchInput = document.querySelector("#searchInput");
const searchResults = document.querySelector("#searchResults");
const chatForm = document.querySelector("#chatForm");
const chatInput = document.querySelector("#chatInput");
const chatOutput = document.querySelector("#chatOutput");

function setStatus(text, className) {
  connectionStatus.textContent = text;
  connectionStatus.className = `status-pill ${className}`;
}

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
  if (text.length <= length) {
    return text;
  }
  return `${text.slice(0, length).trim()}...`;
}

async function requestJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const errorPayload = await response.json();
      detail = errorPayload.detail || detail;
    } catch (error) {
      detail = `${response.status} ${response.statusText}`;
    }
    throw new Error(detail);
  }
  return response.json();
}

function renderDocuments() {
  documentCount.textContent = state.documents.length;
  if (state.documents.length === 0) {
    documentsList.innerHTML = `<div class="item"><p>No documents ingested yet.</p></div>`;
    return;
  }

  documentsList.innerHTML = state.documents
    .map(
      (document) => `
        <div class="item">
          <h3>${escapeHtml(document.title)}</h3>
          <p>${escapeHtml(document.source_path || document.source_id)}</p>
          <div class="meta">
            <span class="tag">${escapeHtml(document.provider)}</span>
            <span class="tag">${escapeHtml(document.updated_at || "No date")}</span>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderExperiments() {
  experimentCount.textContent = state.experiments.length;
  if (state.experiments.length === 0) {
    experimentsList.innerHTML = `<div class="item"><p>No experiments extracted yet.</p></div>`;
    return;
  }

  experimentsList.innerHTML = state.experiments
    .map(
      (experiment) => `
        <div class="item">
          <h3>${escapeHtml(experiment.title)}</h3>
          <p>${escapeHtml(experiment.conclusions || experiment.notes || "Structured experiment record")}</p>
          <div class="meta">
            <span class="tag">${escapeHtml(experiment.date || "No date")}</span>
            <span class="tag">${escapeHtml(experiment.source_provider)}</span>
            ${experiment.markers
              .slice(0, 3)
              .map((marker) => `<span class="tag">${escapeHtml(marker)}</span>`)
              .join("")}
          </div>
        </div>
      `,
    )
    .join("");
}

function renderSearchResults(results) {
  if (results.length === 0) {
    searchResults.innerHTML = `<div class="result"><p>No matches found.</p></div>`;
    return;
  }

  searchResults.innerHTML = results
    .map(
      (result) => `
        <div class="result">
          <h3>${escapeHtml(result.title || "Untitled result")}</h3>
          <p>${escapeHtml(shortText(result.snippet))}</p>
          <div class="meta">
            <span class="tag">${escapeHtml(result.provider || "unknown")}</span>
            <span class="tag">${escapeHtml(result.source)}</span>
            <span class="tag">score ${escapeHtml(result.score ?? "n/a")}</span>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderChatResponse(payload) {
  const sources = payload.sources || [];
  chatOutput.innerHTML = `
    <div class="assistant-answer">
      <h3>Answer</h3>
      <p>${escapeHtml(payload.answer)}</p>
      <div class="meta">
        <span class="tag">${escapeHtml(payload.provider)}</span>
        <span class="tag">${sources.length} source${sources.length === 1 ? "" : "s"}</span>
      </div>
    </div>
    <div class="source-list">
      ${sources
        .map(
          (source, index) => `
            <div class="result">
              <h3>[${index + 1}] ${escapeHtml(source.title || "Untitled source")}</h3>
              <p>${escapeHtml(shortText(source.snippet, 180))}</p>
              <div class="meta">
                <span class="tag">${escapeHtml(source.provider || "unknown")}</span>
                <span class="tag">${escapeHtml(source.chunk_id || "chunk")}</span>
              </div>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

async function loadStatus() {
  try {
    const health = await requestJson("/health");
    setStatus(`${health.project}: ${health.status}`, "ok");
  } catch (error) {
    setStatus("Backend offline", "error");
  }
}

async function loadDocuments() {
  state.documents = await requestJson("/documents");
  renderDocuments();
}

async function loadExperiments() {
  state.experiments = await requestJson("/experiments");
  renderExperiments();
}

async function runSearch(query) {
  const results = await requestJson("/search", {
    method: "POST",
    body: JSON.stringify({ query, limit: 8 }),
  });
  renderSearchResults(results);
}

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = searchInput.value.trim();
  if (!query) {
    searchResults.innerHTML = `<div class="result"><p>Enter a search query.</p></div>`;
    return;
  }

  searchResults.innerHTML = `<div class="result"><p>Searching...</p></div>`;
  try {
    await runSearch(query);
  } catch (error) {
    searchResults.innerHTML = `<div class="result"><p>Search failed: ${escapeHtml(error.message)}</p></div>`;
  }
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message) {
    chatOutput.innerHTML = `<div class="result"><p>Enter a question for ResearchOS chat.</p></div>`;
    return;
  }

  chatOutput.innerHTML = `<div class="result"><p>Thinking...</p></div>`;
  try {
    const payload = await requestJson("/chat", {
      method: "POST",
      body: JSON.stringify({ message, use_search_context: true, limit: 5 }),
    });
    renderChatResponse(payload);
  } catch (error) {
    chatOutput.innerHTML = `
      <div class="result">
        <h3>Chat is not configured</h3>
        <p>${escapeHtml(error.message)}. Set AI_PROVIDER, AI_BASE_URL, AI_MODEL, and AI_API_KEY when required.</p>
      </div>
    `;
  }
});

async function boot() {
  await loadStatus();
  try {
    await Promise.all([loadDocuments(), loadExperiments()]);
  } catch (error) {
    documentsList.innerHTML = `<div class="item"><p>Could not load local data.</p></div>`;
    experimentsList.innerHTML = `<div class="item"><p>Could not load local data.</p></div>`;
  }
}

boot();
