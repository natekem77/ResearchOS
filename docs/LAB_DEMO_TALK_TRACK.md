# Lab Demo Talk Track

This is a 5-7 minute script for showing ResearchOS to lab members or a PI. The
goal is to explain the project without requiring software or Microsoft Graph
background.

## Opening

"ResearchOS is a local research assistant for lab notebooks. The goal is not to
replace OneNote. The goal is to make the notes we already write easier to search,
summarize, and compare."

"Right now, finding an old experiment usually means remembering where it was
written, searching manually, and reading through pages. ResearchOS adds a layer
on top that can index notes, identify experiments, and connect terms like BMP4,
SAG, SIX6, BRN3B, cell lines, and organoid batches."

## Simple Explanation

"Think of ResearchOS as an operating system for research context. OneNote stays
the official notebook. ResearchOS reads approved notebook content, builds a local
index, and gives us structured views of experiments, compounds, markers,
protocols, and search results."

"The prototype does not need UCSD Microsoft approval because it uses sample
Markdown notes. The same internal pipeline is designed so OneNote pages can plug
in later once IT approves read-only Microsoft Graph access."

## Demo Steps

1. Open the dashboard at `http://127.0.0.1:8001`.
2. Click **Load demo notes**.
3. Show the dashboard counters:
   - documents indexed
   - experiments indexed
   - protocols detected
   - compounds detected
4. Open **Documents** and show the sample lab notes.
5. Open **Experiments** and show the structured table.
6. Click an experiment and show extracted metadata:
   - date
   - cell line
   - organoid batch
   - compounds
   - markers
   - notes
   - conclusions
7. Search for `SAG BRN3B staining`.
8. Open **Compounds** and click `BMP4` or `SAG`.
9. Show that ResearchOS links related experiments, protocols, documents, and AI
   summaries.
10. If an AI provider is configured, ask: "What do the SAG and BRN3B notes
    suggest?"

## What Is Working Now

- Local FastAPI backend.
- Browser dashboard.
- Local Markdown demo provider.
- SQLite document and experiment storage.
- Local document ingestion.
- Search with keyword fallback.
- Experiment extraction from notes.
- Retinal organoid entity linking for compounds, markers, cell lines, and
  organoid batches.
- AI chat architecture with configurable provider support.
- Microsoft login scaffolding and read-only OneNote metadata listing.

## What Needs UCSD IT Approval

"The OneNote sync piece requires UCSD Microsoft tenant approval. We need an app
registration or approval for a ResearchOS Development app with read-only
delegated Microsoft Graph permissions."

"The requested permissions are User.Read, Notes.Read, openid, profile, and
offline_access. The app is read-only initially. It will not write to OneNote or
change official notebook records."

## Privacy And Safety Framing

"The development model is local-first. Notes are indexed on the user's local
machine. No secrets are hardcoded. Cloud AI is optional and should only be used
according to lab and UCSD policy."

"The important boundary is that OneNote remains the official record. ResearchOS
is an analysis and discovery layer."

## Future Roadmap

- UCSD-approved read-only OneNote sync.
- Better HTML-to-text conversion for OneNote pages.
- More robust experiment extraction.
- Protocol versioning.
- Microscopy image analysis.
- RNA-seq integration.
- Inventory and reagent linking.
- Literature and paper-writing support.
- Experiment planning and comparison tools.

## Closing

"The main decision now is whether this workflow is useful enough to pursue UCSD
IT approval for read-only OneNote access. The core system works locally, so
development can continue while approval is pending."
