# Microscopy Provider

The microscopy provider is a local-first skeleton for organizing microscopy and
image files as ResearchOS assets.

## What Is Supported Now

ResearchOS scans configured folders recursively:

- `data/images/`
- `samples/images/`

Supported extensions:

- `.tif`
- `.tiff`
- `.png`
- `.jpg`
- `.jpeg`
- `.czi`
- `.lif`
- `.nd2`
- `.oir`
- `.svs`

Files are registered with provider `microscopy`. Scientific microscopy formats
such as `.tif`, `.tiff`, `.czi`, `.lif`, `.nd2`, `.oir`, and `.svs` are
registered as `asset_type: microscopy`; common exported images such as `.png`,
`.jpg`, and `.jpeg` are registered as `asset_type: image`.

## Filename Metadata

The current provider extracts metadata from filenames only:

- Experiment IDs such as `NK_Expt_31` or `EXP_31`
- Markers: `SIX6`, `BRN3B`, `DAPI`, `RAX`, `VSX2`, `CRX`, `RCVRN`, `RBPMS`,
  `POU4F2`, `ISL1`, `OTX2`
- Timepoints such as `D1`, `D7`, `D32`, or `Day32`

Example:

```text
NK_Expt_31_D32_SIX6_BRN3B_DAPI.tif
```

This registers a microscopy asset linked to `NK_Expt_31` with markers
`SIX6`, `BRN3B`, `DAPI` and timepoint `D32`.

## API

```bash
curl http://127.0.0.1:8001/providers/images/status
curl -X POST http://127.0.0.1:8001/providers/images/scan
curl http://127.0.0.1:8001/images
```

## Future Work

This milestone does not process image pixels or parse proprietary microscope
formats. Future milestones can add thumbnails, metadata extraction from OME-TIFF
or vendor files, channel detection, segmentation, marker quantification, and
links from image regions back to experiments.
