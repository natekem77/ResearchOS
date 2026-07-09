# Mobile Networking

ResearchOS mobile clients are thin clients. The iPhone, Android device, tablet, or simulator must reach the FastAPI backend over the network.

## Why `127.0.0.1` Fails on iPhone

`127.0.0.1` always means "this device."

- On your Mac, it means the Mac.
- In iOS Simulator, it usually reaches the Mac.
- On a physical iPhone, it means the iPhone, not the Mac.

For a physical iPhone, use a LAN, Tailscale, HTTPS, or lab-server URL.

## LAN Testing

Find your workstation IP:

```bash
ipconfig getifaddr en0
```

Start ResearchOS on all interfaces:

```bash
RESEARCHOS_DEV_HOST=0.0.0.0 RESEARCHOS_DEV_PORT=8001 PUBLIC_BASE_URL=http://<lan-ip>:8001 ./scripts/demo.sh
```

Test from iPhone Safari:

```text
http://<lan-ip>:8001/health
```

If Safari cannot reach it:

- Confirm iPhone and Mac are on the same Wi-Fi.
- Check firewall settings.
- Confirm the backend is bound to `0.0.0.0`, not `127.0.0.1`.
- Confirm the port is `8001`.

## Tailscale Testing

Install Tailscale on:

- Mac/workstation running ResearchOS
- iPhone

Start ResearchOS:

```bash
RESEARCHOS_DEV_HOST=0.0.0.0 RESEARCHOS_DEV_PORT=8001 PUBLIC_BASE_URL=http://<tailscale-ip>:8001 ./scripts/demo.sh
```

Use the Tailscale IP or MagicDNS name in the app:

```text
http://<tailscale-ip>:8001
```

HTTPS is recommended for production-like use.

## Lab Server Mode

Use `scripts/run_server.sh` for shared access:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=https://researchos-lab.example.edu ./scripts/run_server.sh
```

Mobile clients should use `PUBLIC_BASE_URL`.

## Connection Info Endpoint

ResearchOS exposes:

```http
GET /mobile/connection-info
```

Example:

```bash
curl -s http://127.0.0.1:8001/mobile/connection-info
```

The response includes:

- server name
- version
- public base URL
- current host/port
- recommended mobile URL
- localhost warnings

## OneNote Redirect Implications

OneNote auth redirect URIs are exact.

Local dev:

```text
http://localhost:8001/auth/callback
```

Lab server/mobile:

```text
https://your-public-researchos-url/auth/callback
```

Do not add write-back permissions for mobile testing. Current OneNote scope remains read-only.

## Recommended Mobile URL Order

1. HTTPS lab server URL
2. Tailscale HTTPS URL
3. Tailscale HTTP URL for development only
4. LAN HTTP URL for development only
5. `127.0.0.1` only for same-machine desktop or simulator testing
