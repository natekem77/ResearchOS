# Experiment Workspace Layout

The experiment workspace layout is centered on the notebook.

## Header

- Experiment title
- Status
- Owner
- Current experimental day when known

## Primary Surface

The notebook editor is always visible in the main workspace surface.

Current mobile implementation stores markdown/plain text while backend notebook capabilities advertise headings, lists, checklists, tables, links, attachments, and resource links for richer editors.

## Tool Palette

The tool palette appears below the notebook on small screens and can open side panels on wider screens.

Tools are temporary assistants. Closing a tool returns focus to the notebook without navigating away.

## Adaptive Behavior

- Phone: scrollable notebook-first layout, tool bottom sheets.
- Tablet/Desktop: notebook with optional right-side tool panel.
- Landscape: notebook and tool panel can coexist.

## Migration

Existing generalized experiments already expose a workspace and notebook. Structured data remains available through tools and does not overwrite narrative notes.
