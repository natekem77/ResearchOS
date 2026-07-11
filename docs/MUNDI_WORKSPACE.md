# The Mundi Workspace

The Mundi Workspace is the notebook-first experiment surface. Creating a new experiment immediately creates an experiment record, notebook, history, permissions, and workspace, then opens the notebook.

## Principle

The notebook is the primary surface. Protocols, Copilot, spreadsheets, voice, images, inventory, chat, timeline, and analysis are tools that operate inside the workspace.

## Creation

```bash
curl -X POST http://127.0.0.1:8001/experiments/notebook-first \
  -H "Content-Type: application/json" \
  -d '{"title":"Optional title"}'
```

If no title is provided, ResearchOS creates an untitled draft experiment. No protocol, metadata, workflow, or sample information is required.

## Tools

Workspace tools open as a side panel on wide screens and bottom sheets on iPhone. They do not replace the notebook.

Initial tools include:

- Experiment Copilot
- Protocols
- Spreadsheet Import
- Voice
- Images
- Attachments
- Timeline
- Conditions
- Samples
- Inventory
- Chat
- Analysis
- Literature
- Scientific Memory
- Whiteboard

## Protocols

Attaching a protocol creates protocol references and can generate inherited timeline events. It does not overwrite notebook content. A protocol summary is inserted only when the researcher chooses that option.
