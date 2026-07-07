# Lab Server Deployment

ResearchOS can run in local development mode or as a shared lab server for
iPhone, Android, tablets, and laptops through the PWA web app.

This is a deployment foundation, not a security-hardening finish line. Use
HTTPS, controlled network access, and clear lab data policies before using
ResearchOS with real lab notebooks or regulated data.

## Local Dev Mode

Use local demo mode while developing on one machine:

```bash
./scripts/demo.sh
```

Default URL:

```text
http://127.0.0.1:8001
```

`127.0.0.1` only works on the same machine. Phones and other lab devices cannot
connect to this address.

## Lab Workstation / Server Mode

Run ResearchOS bound to all interfaces:

```bash
./scripts/run_server.sh --host 0.0.0.0 --port 8001
```

Set a public or LAN URL:

```bash
PUBLIC_BASE_URL=http://lab-workstation.local:8001 ./scripts/run_server.sh --host 0.0.0.0 --port 8001
```

For HTTPS behind a reverse proxy:

```bash
PUBLIC_BASE_URL=https://researchos.lab.example.edu ./scripts/run_server.sh --host 127.0.0.1 --port 8001
```

Recommended production-like pattern:

- Run Uvicorn on localhost or a private interface.
- Put nginx, Caddy, or an institutional proxy in front.
- Terminate HTTPS at the proxy.
- Restrict access to the lab network, VPN, or approved users.

## VPN / Tailscale Option

A practical early lab setup is to run ResearchOS on a lab workstation and expose
it only through VPN or Tailscale.

Benefits:

- Phones, tablets, and laptops can access the PWA from off the lab network.
- ResearchOS is not exposed to the public internet.
- TLS certificates and device access can be managed through the VPN provider.

Use:

```bash
PUBLIC_BASE_URL=https://researchos-yourtailnet.ts.net
```

## UCSD-Hosted Option

For a durable lab or department deployment, ask UCSD IT about hosting options:

- UCSD-managed VM
- departmental server
- Kubernetes or container platform
- institution-managed HTTPS and DNS
- Microsoft Entra app registration owned by UCSD

This is the preferred path for real UCSD OneNote integration and broader lab
use.

## HTTPS Requirement

Use HTTPS for shared lab access.

HTTPS is important because:

- browser PWA installation behaves better on secure origins
- Microsoft auth redirect flows are more reliable
- access tokens and research data should not cross the network in clear text
- mobile browsers increasingly restrict advanced web features on insecure origins

Localhost development is an exception for browser testing, but shared lab access
should use HTTPS.

## OneNote Auth Redirect Implications

`MICROSOFT_REDIRECT_URI` must exactly match the redirect URI registered in the
Microsoft Entra app.

Local development example:

```text
http://localhost:8001/auth/callback
```

Lab server example:

```text
https://researchos.lab.example.edu/auth/callback
```

If `PUBLIC_BASE_URL` changes, update:

- `.env`
- Microsoft Entra app redirect URI
- UCSD IT approval request, if applicable

Do not request write permissions for the current read-only MVP.

## Environment Variables

Core server settings:

```bash
HOST=0.0.0.0
PORT=8001
PUBLIC_BASE_URL=https://researchos.lab.example.edu
DATA_DIR=./data
```

ResearchOS app settings:

```bash
RESEARCHOS_API_HOST=0.0.0.0
RESEARCHOS_API_PORT=8001
RESEARCHOS_PUBLIC_BASE_URL=https://researchos.lab.example.edu
RESEARCHOS_DATA_DIR=./data
RESEARCHOS_DATABASE_URL=sqlite:///./data/researchos.db
RESEARCHOS_CHROMA_PERSIST_DIRECTORY=./data/chroma
```

Microsoft Graph:

```bash
MICROSOFT_CLIENT_ID=
MICROSOFT_TENANT_ID=common
MICROSOFT_REDIRECT_URI=https://researchos.lab.example.edu/auth/callback
GRAPH_SCOPES="User.Read Notes.Read"
```

AI provider:

```bash
AI_PROVIDER=none
AI_BASE_URL=
AI_API_KEY=
AI_MODEL=
```

Never commit real API keys or Microsoft secrets.

## Deployment Status Endpoint

Check deployment readiness:

```bash
curl http://127.0.0.1:8001/status/deployment
```

The endpoint returns:

- host
- port
- whether `PUBLIC_BASE_URL` is configured
- HTTPS enabled/disabled
- data directory
- mobile/PWA URL
- Microsoft redirect URI
- warnings for localhost-only or non-HTTPS mode

It does not expose secrets.

## Security / Privacy Considerations

ResearchOS is local-first, but a shared server changes the risk model.

Before using real lab data:

- restrict network access
- use HTTPS
- keep `.env` out of git
- avoid cloud AI unless approved by the lab/PI/institution
- document who can access the server
- back up the SQLite database and data directory
- do not expose UCSD OneNote data to unmanaged networks
- review Microsoft Graph tenant/app consent with UCSD IT

## Mobile / PWA Access

Once the lab server is reachable, open `PUBLIC_BASE_URL` from iPhone, Android,
tablet, or laptop. Then install through the browser:

- iPhone/iPad: Safari Share menu -> Add to Home Screen
- Android: Chrome menu -> Install app or Add to Home screen

See [MOBILE_PWA.md](MOBILE_PWA.md).
