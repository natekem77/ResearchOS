# Research Asset Graph

ResearchOS treats every research file as an `Asset`.

An asset is a lightweight local record for a notebook page, protocol, paper, image,
GraphPad file, spreadsheet, CSV, PDF, presentation, sequencing output,
microscopy dataset, or any other research file. The asset record stores metadata
and links to experiments without requiring provider-specific parsing up front.

## Asset Model

Each asset contains:

- `asset_id`: local stable identifier.
- `asset_type`: one of `notebook`, `protocol`, `literature`, `image`,
  `graphpad`, `spreadsheet`, `csv`, `pdf`, `presentation`, `sequencing`,
  `microscopy`, or `other`.
- `experiment_id`: optional link to a structured experiment record.
- `title`: human-readable name.
- `filename`: original file name when available.
- `provider`: source system such as `local`, `markdown`, `onenote`,
  `literature`, `microscopy`, or a future provider.
- `path`: local path, provider path, or source locator.
- `created_at` / `updated_at`: local registration timestamps.
- `metadata`: provider-specific JSON metadata.

## Experiments Connect Assets

Experiments are the central scientific records in ResearchOS. Assets attach
supporting files to those experiments:

- Notebook pages provide the written record.
- Protocols describe planned or repeated methods.
- Literature assets provide external context.
- Images and microscopy files provide readouts.
- GraphPad, spreadsheets, and CSV files provide analysis artifacts.
- Sequencing assets provide bulk, single-cell, or other omics outputs.

The experiment API exposes `linked_assets` so a researcher can move from a
structured experiment to all supporting research files.

## OneNote As An Asset Provider

OneNote is not special in the core architecture. It is one provider that can
produce notebook assets and ResearchDocuments. The read-only MVP syncs OneNote
pages into local ResearchOS records while OneNote remains the official notebook.

Future OneNote write-back can create or update notebook assets only after UCSD
IT approves the required create/write permissions.

## Future Providers

The asset graph is designed to accept new providers incrementally:

- GraphPad files can be registered now and parsed later.
- Microscopy image folders can become image or microscopy assets.
- PDF and paper notes can become literature assets.
- PowerPoint files can become presentation assets.
- Sequencing output folders can become sequencing assets.

Milestone 31 intentionally implements registration and linking only. It does not
parse GraphPad, images, sequencing files, or other specialized formats yet.

## API

List assets:

```bash
curl http://127.0.0.1:8001/assets
```

Register an asset:

```bash
curl -X POST http://127.0.0.1:8001/assets/register \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "image",
    "title": "D32 SAG BRN3B representative image",
    "filename": "sag_brn3b_d32.tif",
    "provider": "local",
    "path": "data/images/sag_brn3b_d32.tif",
    "metadata": {"channel": "BRN3B"}
  }'
```

Link an asset to an experiment:

```bash
curl -X POST http://127.0.0.1:8001/assets/link \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "asset:example",
    "experiment_id": "experiment:example"
  }'
```

Link a GraphPad Prism file to a human experiment ID before the extracted
experiment exists:

```bash
curl -X POST http://127.0.0.1:8001/assets/register \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "graphpad",
    "title": "NK Expt 31 SAG rescue Prism analysis",
    "filename": "NK_Expt_31_SAG_rescue.pzfx",
    "provider": "local",
    "path": "data/graphpad/NK_Expt_31_SAG_rescue.pzfx"
  }'

curl -X POST http://127.0.0.1:8001/assets/link \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "asset:example",
    "experiment_id": "NK_Expt_31"
  }'
```

If `NK_Expt_31` has not been extracted yet, the link is kept with
`link_status: "unresolved"`. When a future ingested experiment has
`experiment_id` equal to `NK_Expt_31`, ResearchOS resolves the link
automatically in asset and experiment responses.

Link a microscopy image to an experiment:

```bash
curl -X POST http://127.0.0.1:8001/assets/register \
  -H "Content-Type: application/json" \
  -d '{
    "asset_type": "microscopy",
    "title": "D32 BRN3B confocal field 01",
    "filename": "D32_BRN3B_field01.tif",
    "provider": "local",
    "path": "data/microscopy/D32_BRN3B_field01.tif",
    "metadata": {"marker": "BRN3B", "modality": "confocal"}
  }'
```

Link a Prism analysis directly to an extracted ResearchOS experiment ID:

```bash
curl -X POST http://127.0.0.1:8001/assets/link \
  -H "Content-Type: application/json" \
  -d '{
    "asset_id": "asset:example",
    "experiment_id": "experiment:8ff67dfff14ec61c"
  }'
```

Delete an asset registration:

```bash
curl -X DELETE http://127.0.0.1:8001/assets/asset:example
```
