# ResearchOS v0.2 Preview Release Notes

ResearchOS v0.2 preview stabilizes the local-first lab intelligence prototype
after the provider, Knowledge Graph, Experiment Workspace, PWA, lab-server, and
OneNote readiness milestones.

This is still a preview release. It is intended for PI/lab demos, technical
review, and UCSD IT conversations rather than production use with real lab data.

## New Since v0.1

- Global Knowledge Graph that indexes entities across experiments, documents,
  literature, assets, microscopy files, GraphPad exports, spreadsheets,
  statistics, and pending notebook entries.
- Knowledge Graph powered assistant mode for questions about entities and
  experiments.
- Unified Experiment Workspace that aggregates notebook records, timelines,
  provider assets, statistics, literature, related entities, summaries, and
  provenance into one experiment page.
- Research Asset Graph for registering and linking arbitrary research files to
  experiments.
- Provider skeletons for GraphPad, microscopy/images, and generic spreadsheets.
- GraphPad CSV statistics extraction and statistics interpretation.
- Compact quantitative summaries for spreadsheet and statistics assets.
- Browser PWA foundation with responsive dashboard/workspace layouts, manifest,
  service worker skeleton, and mobile navigation.
- Lab server deployment foundation for shared access from phones, tablets, and
  lab laptops.
- OneNote readiness validation for redirect URI, configured Microsoft Graph
  scopes, current auth status, deployment URL, UCSD approval status, and
  read-only sync readiness.
- Pending notebook entry draft storage and export workflow while OneNote
  write-back remains disabled.

## PWA / Mobile Support

ResearchOS now includes a mobile-first web app foundation:

- Responsive dashboard and Experiment Workspace.
- PWA manifest and placeholder icons.
- Service worker skeleton.
- Bottom navigation on narrow screens.
- Mobile-friendly New Experiment dictation page.

Phones and tablets must be able to reach the backend URL. `127.0.0.1` only works
on the machine running the server. See `docs/MOBILE_PWA.md`.

## Lab Server Deployment

The preview includes:

- `scripts/run_server.sh` for production-like foreground serving.
- `HOST`, `PORT`, `PUBLIC_BASE_URL`, `DATA_DIR`, and AI provider environment
  settings.
- `GET /status/deployment` for deployment diagnostics.
- Settings page deployment cards with server URL and mobile/PWA guidance.

Use HTTPS for shared lab access and Microsoft auth. See
`docs/LAB_SERVER_DEPLOYMENT.md`.

## OneNote Readiness

OneNote sync remains read-only. v0.2 adds:

- `GET /status/onenote-readiness`
- Exact current redirect URI display.
- Required Azure redirect URI display.
- Required delegated read-only permissions:
  `User.Read`, `Notes.Read`, `openid`, `profile`, and `offline_access`.
- UCSD approval guidance.
- Explicit confirmation that write-back is disabled.

No OneNote write permissions are requested. Future write-back would require a
separate UCSD IT approval for permissions such as `Notes.Create` or
`Notes.ReadWrite`.

## Knowledge Graph

The Global Knowledge Graph dynamically builds relationships from existing
provider metadata instead of maintaining a separate duplicate database.

Useful endpoints:

```bash
curl http://127.0.0.1:8001/knowledgegraph
curl "http://127.0.0.1:8001/knowledgegraph/search?q=SAG"
curl http://127.0.0.1:8001/knowledgegraph/entity/SIX6
curl http://127.0.0.1:8001/knowledgegraph/experiment/NK_Expt_31
```

## Experiment Workspace

Each experiment has a central workspace:

```bash
curl "http://127.0.0.1:8001/experiments/NK_Expt_31/workspace?use_ai=false"
```

The workspace gathers notebook entries, extracted experiment metadata,
timelines, microscopy/image assets, GraphPad analyses, spreadsheets, statistics,
literature, related Knowledge Graph entities, conclusions, limitations, and
provenance.

## Providers

v0.2 preview includes local provider foundations for:

- Markdown demo notes.
- OneNote read-only sync after Microsoft Graph login and tenant approval.
- Literature notes/PDFs.
- GraphPad/Prism-associated files.
- GraphPad CSV statistics exports.
- Generic spreadsheets: CSV, TSV, XLS, XLSX.
- Microscopy/image files with filename-based metadata extraction.
- Pending notebook entry drafts.

The GraphPad and microscopy providers intentionally do not deeply parse
proprietary binary formats yet.

## Known Limitations

- Demo data is bundled sample data, not UCSD OneNote content.
- OneNote access requires Microsoft Entra/UCSD IT approval.
- OneNote write-back is disabled.
- Token storage is temporary, process-local, and not production-ready.
- PWA offline behavior is only a skeleton.
- Lab server deployment still needs HTTPS, access control, backups, and data
  governance before real use.
- AI is optional and only runs when explicitly configured.
- Provider metadata extraction is intentionally conservative and may miss
  domain-specific details.
- Statistics interpretation depends on clean exported columns and does not
  replace formal statistical review.

## Next Milestones

- UCSD-approved OneNote read-only pilot.
- User-scoped encrypted token storage.
- Authentication and access control for shared lab deployment.
- HTTPS deployment recipe for a lab workstation or UCSD-hosted environment.
- Better OneNote HTML-to-markdown preservation.
- Deeper provider parsers for GraphPad, microscopy, flow cytometry, RNA-seq, and
  image analysis outputs.
- Knowledge Graph driven inventory, protocol versioning, paper writing, and
  experiment planning workflows.
