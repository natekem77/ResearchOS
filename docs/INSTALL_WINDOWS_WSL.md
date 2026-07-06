# Install ResearchOS On Windows With WSL

This guide is for running the local ResearchOS demo on Windows using WSL.

## Prerequisites

Install:

- Windows 10 or 11 with WSL enabled.
- Ubuntu or another Linux distribution in WSL.
- Git.
- Python 3.12.
- A terminal inside WSL.

Check Python:

```bash
python3.12 --version
```

If Python 3.12 is missing, install it through your WSL distribution package
manager or your lab's preferred Python setup.

## Clone The Repository

```bash
git clone <researchos-repo-url>
cd labnote-ai
```

If the repository is already present:

```bash
cd /home/<your-user>/workspace/labnote-ai
```

## Create The Backend Virtual Environment

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

Return to the repository root:

```bash
cd ..
```

## Run The Demo

```bash
./scripts/demo.sh
```

The script will:

- restart the backend on `127.0.0.1:8001`
- wait for `/health`
- load sample lab notes
- print the dashboard URL
- try to open the dashboard in a browser if WSL can launch one

## Open The Dashboard

Open:

```text
http://127.0.0.1:8001
```

Click through:

- Dashboard
- Documents
- Experiments
- Compounds
- Settings

## Stop The Backend

```bash
./scripts/stop.sh
```

## Notes

The demo uses local Markdown notes and does not require UCSD Microsoft tenant
approval. Real OneNote sync requires Microsoft Graph login and UCSD tenant
approval or a UCSD-owned app registration.
