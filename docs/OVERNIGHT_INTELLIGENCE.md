# Overnight Intelligence

Overnight Intelligence generates a Morning Brief from actual ResearchOS changes while the lab was inactive.

The engine is deterministic by default. It does not invent observations or scientific conclusions. Every recommendation must include provenance pointing back to the supporting ResearchOS record.

## What the Morning Brief Summarizes

The brief groups observed changes into:

- New experiments
- Updated experiments
- Completed workflows
- Missing analyses
- New literature
- Knowledge Graph changes
- Protocol updates
- Resource alerts
- Research Copilot insights
- Suggested priorities

Sources include experiments, sessions, Knowledge Graph, statistics, GraphPad assets, microscopy assets, spreadsheets, resources, workflows, Research Copilot feed items, Scientific Memory, protocols, and literature.

## Supported Windows

The API supports:

- `today`
- `yesterday`
- `last_week`

## API

```bash
curl http://127.0.0.1:8001/intelligence/morning
curl "http://127.0.0.1:8001/intelligence/morning?period=yesterday"
curl "http://127.0.0.1:8001/intelligence/morning?period=last_week"
```

Mobile clients can use:

```bash
curl http://127.0.0.1:8001/mobile/intelligence/morning
```

## Provenance

Each item includes provenance such as:

- experiment ID
- document ID
- asset ID
- resource ID
- workflow ID
- provider/source

If a category has no observed changes, ResearchOS returns an empty section rather than manufacturing a recommendation.

## Future Work

Future milestones can add:

- Scheduled overnight jobs
- PubMed monitoring
- automatic provider refresh
- email or push notification delivery
- per-user morning briefs
- workspace-specific briefing subscriptions
