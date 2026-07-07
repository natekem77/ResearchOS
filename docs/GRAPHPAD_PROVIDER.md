# GraphPad Provider

The GraphPad provider is a local-first skeleton for discovering GraphPad Prism
analysis files and related exports. It registers files as ResearchOS assets so
they can be linked to experiments, searched in the asset graph, and shown in
experiment detail pages.

## What Is Supported Now

ResearchOS scans configured local folders recursively:

- `data/graphpad/`
- `samples/graphpad/`

Supported extensions:

- `.prism`
- `.pzfx`
- `.pzfx.zip`
- `.csv`
- `.xlsx`
- `.xls`
- `.png`
- `.jpg`
- `.jpeg`
- `.svg`
- `.pdf`

Files are registered as assets with provider `graphpad`:

- `.prism`, `.pzfx`, `.pzfx.zip` -> `asset_type: graphpad`
- `.csv`, `.xlsx`, `.xls` -> `asset_type: spreadsheet`
- `.png`, `.jpg`, `.jpeg`, `.svg` -> `asset_type: image`
- `.pdf` -> `asset_type: pdf`

Duplicate registrations are avoided by provider plus absolute path.

CSV exports are parsed for basic statistics when possible. See
[GRAPHPAD_STATISTICS_EXTRACTION.md](GRAPHPAD_STATISTICS_EXTRACTION.md) for
supported columns and recommended export format.

## Experiment Linking

The provider tries to infer a human experiment ID from filenames:

- `NK_Expt_31.prism` -> `NK_Expt_31`
- `NK-Expt-31-SAG.csv` -> `NK_Expt_31`
- `EXP_31_BRN3B.png` -> `EXP_31`

If the inferred experiment is not yet extracted, the asset is still registered
and the link is shown as `unresolved`. When a matching ResearchOS experiment is
ingested later, the link resolves automatically in `/assets`, `/assets/{id}`,
and `/experiments`.

## API

Check provider status:

```bash
curl http://127.0.0.1:8001/providers/graphpad/status
```

Scan configured folders:

```bash
curl -X POST http://127.0.0.1:8001/providers/graphpad/scan
```

List registered GraphPad assets:

```bash
curl 'http://127.0.0.1:8001/assets?query=graphpad'
```

## Limitations

This milestone does not parse proprietary Prism files. `.prism` and `.pzfx`
files are registered as assets only. Future milestones can add:

- Prism XML/ZIP inspection where format permits.
- Extraction of analysis titles, data table names, and graph names.
- Linking exported figures to Prism source files.
- Statistical result extraction from CSV/XLSX exports.
- Deeper experiment matching using ontology entities and AI assistance.
