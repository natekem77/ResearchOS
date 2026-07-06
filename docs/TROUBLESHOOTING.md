# Troubleshooting

## Port 8001 Already In Use

Check the ResearchOS backend status:

```bash
./scripts/status.sh
```

Stop the process on port `8001`:

```bash
./scripts/stop.sh
```

Then restart:

```bash
./scripts/restart.sh
```

To use a different port temporarily:

```bash
RESEARCHOS_DEV_PORT=8010 ./scripts/demo.sh
```

## Backend Not Starting

Run:

```bash
./scripts/restart.sh
```

If it fails, inspect the log:

```bash
tail -n 80 .researchos-dev.log
```

Common causes:

- `backend/.venv` does not exist.
- Dependencies are not installed.
- Another process is already using the port.
- The command is being run outside the repository root.

## Missing Python Dependencies

Activate the backend virtual environment and reinstall requirements:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

Then run:

```bash
./scripts/demo.sh
```

## OneNote Login Blocked

If `/auth/login` or `/sync/onenote` fails, check:

- `MICROSOFT_CLIENT_ID` is set.
- `MICROSOFT_TENANT_ID` is set.
- `MICROSOFT_REDIRECT_URI` matches the Azure app registration.
- The Azure app is configured as a public client.
- The redirect URI is `http://localhost:8001/auth/callback` for the local demo.

If UCSD blocks consent, ResearchOS needs tenant approval or a UCSD-owned app
registration.

## UCSD Tenant Approval

Use:

```text
docs/UCSD_IT_APPROVAL_REQUEST.md
```

The initial requested Microsoft Graph permissions are delegated and read-only:

- `User.Read`
- `Notes.Read`
- `openid`
- `profile`
- `offline_access`

ResearchOS does not write back to OneNote in the MVP.

## AI Provider Not Configured

Search works without AI. `/chat` requires an AI provider configuration.

Set these in `.env` when ready:

```bash
AI_PROVIDER=openai_compatible
AI_BASE_URL=<provider-base-url>
AI_API_KEY=<api-key-if-required>
AI_MODEL=<model-name>
```

Local OpenAI-compatible servers such as LM Studio or Ollama may not require an
API key, depending on local configuration.

## Demo Reset Fails

Run:

```bash
curl -i -X POST http://127.0.0.1:8001/demo/reset
```

If the backend is not reachable, restart it:

```bash
./scripts/restart.sh
```
