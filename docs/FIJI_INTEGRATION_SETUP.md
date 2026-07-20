# Fiji Integration Setup

Mundi Imaging uses the backend API for uploads and a separate local worker for
validated Fiji/ImageJ workflows. The Flutter app never sends arbitrary commands
or macros.

## Install Fiji

Download Fiji from https://imagej.net/software/fiji/ and place it somewhere
stable on the Mac, for example:

```bash
/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx
```

Set:

```bash
export MUNDI_FIJI_PATH=/Applications/Fiji.app/Contents/MacOS/ImageJ-macosx
export MUNDI_IMAGING_WORK_DIR=./data/imaging/work
export MUNDI_IMAGING_WORKER_ID=mac-fiji-worker
export MUNDI_IMAGING_JOB_POLL_SECONDS=3
export MUNDI_IMAGING_MAX_FILE_MB=512
export MUNDI_IMAGING_JOB_TIMEOUT_SECONDS=600
```

## Check Fiji

```bash
python3 scripts/check_fiji_installation.py
```

The checker creates a tiny TIFF, launches Fiji headlessly, runs the bundled
`generate_preview.ijm` macro, verifies `preview.png`, and exits. It proves real
macro execution instead of probing the executable version.

## Start Backend

Use the existing backend startup command for this repo, for example:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Start Imaging Worker

From the repo root:

```bash
python3 scripts/run_imaging_worker.py
```

The worker polls queued jobs, writes outputs under `data/imaging/jobs/{job_id}`,
and records heartbeat status visible through:

```bash
curl http://127.0.0.1:8000/mobile/imaging/worker-status
```

## Storage Layout

Raw uploads are immutable:

```text
data/imaging/raw/{asset_id}/original-file
```

Derived outputs are separate:

```text
data/imaging/jobs/{job_id}/
  preview.png
  log.txt
  provenance.json
```

## Adding Validated Workflows

Add workflows only in `backend/app/imaging/workflows.py`. Do not expose macro
text fields in Flutter. Validate all parameters against the schema before a job
is queued.

Current MVP workflow:

- Generate Preview

This milestone intentionally proves only:

```text
input.tif -> Fiji headless macro -> preview.png
```

## Troubleshooting

- `worker-status` unavailable: start `scripts/run_imaging_worker.py`.
- Fiji not found: set `MUNDI_FIJI_PATH` to the executable inside Fiji.app.
- Proprietary metadata unavailable: upload still succeeds; Mundi shows
  `Metadata unavailable`.
- Output missing: inspect the job log output and backend console for sanitized
  worker errors.
