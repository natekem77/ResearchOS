# ResearchOS Product Principles

These principles define how ResearchOS should behave as it grows.

## 1. ResearchOS Never Invents Observations

ResearchOS may summarize, organize, compare, and suggest.

It must never invent experimental observations, measurements, results, or conclusions.

If evidence is missing, ResearchOS should say so.

## 2. Every Statement Has Provenance

Scientific statements should trace back to:

- notebook entries
- experiments
- assets
- images
- spreadsheets
- GraphPad analyses
- statistics
- literature
- user-created drafts
- timestamps
- providers

No important claim should be disconnected from its source.

## 3. The Scientist Stays in Control

ResearchOS should assist the scientist, not override them.

The user reviews, approves, edits, exports, and decides.

## 4. AI Assists

AI can help with:

- summarization
- search
- comparison
- draft generation
- reasoning over evidence
- planning follow-up experiments
- writing support

AI should be grounded in retrieved evidence and should expose limitations.

## 5. AI Never Silently Edits Notebooks

Notebook write-back must always be explicit, reviewed, permissioned, and auditable.

ResearchOS should not silently modify OneNote or any official notebook provider.

## 6. Providers Remain Modular

Every provider should be replaceable.

OneNote, Markdown, GraphPad, spreadsheets, microscopy, sequencing, literature, PubMed, Benchling, ImageJ, CellProfiler, Seurat, Scanpy, and future tools should plug into ResearchOS without rewriting the core platform.

## 7. Everything Becomes an Asset

Every research object should be representable as an asset or connected to one:

- notebooks
- protocols
- literature
- images
- GraphPad files
- spreadsheets
- PDFs
- presentations
- sequencing data
- microscopy data
- figures
- manuscripts

Assets are the bridge between files and experiments.

## 8. Everything Is Searchable

Documents, experiments, sessions, protocols, images, statistics, literature, files, entities, and commands should be searchable from one global interface.

Search should work locally even without AI.

## 9. Everything Connects Through the Knowledge Graph

The Knowledge Graph should become the central relationship layer.

Future features should consume graph evidence instead of rebuilding their own relationship logic.

## 10. Local-First by Default

ResearchOS should work locally with SQLite and local files before depending on cloud services.

Cloud AI and cloud hosting should be optional and clearly disclosed.

## 11. Read-Only First, Write Later

New integrations should begin read-only whenever possible.

Write-back requires stronger permissions, review workflows, audit trails, and explicit user action.

## 12. Deterministic Before Generative

Regex, parsers, structured metadata, deterministic agents, and local statistics should be used before LLMs.

LLMs should improve synthesis, not become the only source of behavior.

## 13. Small Modules Beat Large Controllers

Providers, routes, repositories, services, agents, and frontend views should stay modular.

Large files should be split before they become risky to change.

## 14. Scientific Uncertainty Is a Feature

ResearchOS should expose:

- missing data
- conflicting evidence
- weak evidence
- low confidence
- statistical limitations
- literature disagreements

The system should make uncertainty visible.

## 15. Labs Should Be Able to Leave

ResearchOS should avoid lock-in.

Data should remain exportable as local files, SQLite records, Markdown, JSON, CSV, and provider-native formats where possible.

## 16. Security and Privacy Are Product Features

ResearchOS should make data handling visible:

- where data is stored
- whether AI is configured
- whether cloud services are used
- what OneNote permissions are requested
- what write-back is disabled or enabled

## 17. The Official Notebook Remains Official

ResearchOS can augment OneNote or other notebooks, but it should not create ambiguity about the official scientific record.

## 18. Build for Real Lab Friction

The product should support messy filenames, incomplete notes, old spreadsheets, partial metadata, inconsistent experiment IDs, and evolving protocols.

The system should preserve unknown terms rather than discarding them.

## 19. Review Before Save

Draft generation, voice-to-entry, manuscript text, protocol suggestions, and OneNote write-back should all use review-before-save workflows.

## 20. Evidence Over Aesthetics

ResearchOS should look polished, but scientific traceability is more important than visual novelty.
