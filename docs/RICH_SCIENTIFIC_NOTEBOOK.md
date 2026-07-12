# Mundi Rich Scientific Notebook

Mundi notebooks are the primary experiment surface. The rich notebook is an indefinitely growing vertical document, not a fixed wizard and not a two-dimensional canvas.

## Editor Decision

Mundi uses Flutter Quill for the first rich notebook implementation.

Reasons:
- Current package with iOS, Android, desktop, and web support.
- Built-in editor and toolbar widgets.
- Stores structured Quill Delta JSON, which maps well to backend persistence.
- Exposes plain text for search, accessibility, and AI context.
- Supports links, headings, lists, checklists, quotes, and custom embed architecture.
- MIT license and lighter product risk than AppFlowy Editor's AGPL/MPL combination.

Alternatives reviewed:
- Super Editor: highly extensible, but stable pub release is old and the project notes ongoing API evolution.
- AppFlowy Editor: powerful block editor, but heavier dependencies and licensing constraints make it less conservative for Mundi's first notebook editor.

## Implemented

- Rich-document editor in experiment workspace.
- Mobile horizontal formatting toolbar.
- Manual Save plus debounced autosave.
- Optimistic document version conflict handling through existing backend version checks.
- Quill Delta JSON persistence.
- Legacy markdown/plain-text migration into structured Delta for display.
- Plain-text cache generation.
- Attachment cards remain separate from document JSON.
- Document zoom persisted as a local user preference.

## Deferred

- Full table block editing.
- Custom rendered embeds for every ResearchObject type.
- Rich paste conversion prompts for standalone URLs.
- Version diff UI.
- Free-positioned canvas, ink, Pencil drawing, lasso, and annotations.
