# ResearchOS 5-Minute Demo Script

## Opening

ResearchOS is an AI-powered research operating system for scientific labs. The
goal is not to replace the official lab notebook. The goal is to make the
knowledge already inside lab notes searchable, structured, and useful.

## Problem

Scientific notes are often hard to reuse. Important details are spread across
protocol notes, experiment pages, staining results, images, and follow-up
comments. A researcher may remember that an experiment happened, but not which
batch, marker, treatment, or result contained the key detail.

## Why OneNote Stays Official

Many labs already use Microsoft OneNote as the official notebook. ResearchOS is
designed to respect that. OneNote can remain the source of record, with its
existing access controls and lab habits.

ResearchOS adds a read-only intelligence layer on top. It can ingest notes,
search across them, extract structured experiment records, and later connect to
OneNote through Microsoft Graph after tenant approval.

## What ResearchOS Adds

ResearchOS adds:

- Local document ingestion for development and demos.
- Search across lab notes.
- Automatic experiment extraction.
- Structured fields like date, cell line, compounds, markers, time points, and
  conclusions.
- A provider-agnostic foundation for OneNote, Markdown, Obsidian, Notion, and
  future lab systems.
- A configurable AI chat layer for OpenAI-compatible providers and local models.

## Demo Flow

1. Open `http://127.0.0.1:8001`.
2. Point out backend status at the top.
3. Click **Load demo notes**.
4. Show the three sample lab notes in the Documents panel.
5. Show the extracted experiment records in the Experiments panel.
6. Select the SAG experiment and SIX6/BRN3B staining result, then click
   **Compare selected**.
7. Search for `SAG BRN3B staining`.
8. Explain that search works locally even without cloud AI.
9. Ask the assistant: `Compare SAG experiment and SIX6/BRN3B staining result`.
10. Show that the answer includes structured evidence and source snippets.

## Demo Search

Search query:

```text
SAG BRN3B staining
```

Talk track:

ResearchOS finds the staining result and the SAG experiment because the notes
mention shared markers, treatment context, and readouts. This is the first step
toward asking questions across an entire lab notebook.

## Demo Experiment Extraction

Click **Extract experiments** or use the already extracted records after loading
demo notes.

Talk track:

The system converts unstructured notebook-style text into structured experiment
records. It extracts fields like date, researcher, organoid batch, treatment,
concentration, time points, markers, notes, and conclusions. This is regex-first
today, with an interface for future LLM extraction.

## Demo Experiment Comparison

In the Experiments panel, select two experiment rows and click **Compare
selected**.

Talk track:

ResearchOS compares structured fields side-by-side: compounds, treatments,
concentrations, time points, markers, imaging methods, notes, and conclusions.
The local fallback interpretation works without an AI key, and an AI provider
can optionally rewrite the comparison narrative.

## Future UCSD OneNote Integration

Today the demo uses local Markdown notes so development is not blocked by
Microsoft tenant approval.

The existing Microsoft Graph auth and OneNote metadata code remains in the
backend. Once UCSD tenant approval is available, OneNote will plug in as another
notebook provider and feed the same ResearchDocument, search, experiment
extraction, and chat pipeline.

## Closing

ResearchOS keeps the official notebook intact while adding a searchable,
structured, AI-ready layer for research workflows.
