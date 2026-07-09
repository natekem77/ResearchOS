# Mobile Networking

ResearchOS mobile clients are thin clients. The iPhone, Android device, tablet, or simulator must reach the FastAPI backend over the network.

## Why `127.0.0.1` Fails on iPhone

`127.0.0.1` always means "this device."

- On your Mac, it means the Mac.
- In iOS Simulator, it usually reaches the Mac.
- On a physical iPhone, it means the iPhone, not the Mac.

For a physical iPhone, use a LAN, Tailscale, HTTPS, or lab-server URL.

## LAN Testing

Find your Mac LAN IP:

```bash
ipconfig getifaddr en0
```

Start ResearchOS on all interfaces:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://<lan-ip>:8001 ./scripts/demo.sh
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

## One-command Mobile Dev Server

ResearchOS includes a helper for mobile testing:

```bash
./scripts/mobile_dev_server.sh
```

It starts the normal demo workflow with:

```text
HOST=0.0.0.0
PORT=8001
```

If possible, it infers a LAN URL and prints it. You can override the mobile URL:

```bash
PUBLIC_BASE_URL=http://<lan-or-tailscale-ip>:8001 ./scripts/mobile_dev_server.sh
```

Enter the printed mobile URL in the Flutter app Server Connection screen.

## Tailscale Testing

Install Tailscale on:

- Mac/workstation running ResearchOS
- iPhone

Start ResearchOS:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://<tailscale-ip>:8001 ./scripts/demo.sh
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

## Windows and WSL Caveats

If ResearchOS runs inside WSL, there are two network layers:

- WSL Linux network namespace
- Windows host network

Binding to `127.0.0.1` only exposes the backend inside the same machine. For device testing, start with:

```bash
HOST=0.0.0.0 PORT=8001 ./scripts/demo.sh
```

Find the Windows LAN IP from PowerShell:

```powershell
ipconfig
```

Look for the active Wi-Fi or Ethernet adapter IPv4 address, for example:

```text
IPv4 Address . . . . . . . . . . : 192.168.1.25
```

Then launch with:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://192.168.1.25:8001 ./scripts/demo.sh
```

If the iPhone still cannot connect:

- Allow Python/WSL traffic through Windows Defender Firewall.
- Confirm the Windows network is marked Private, not Public.
- Test `http://<windows-ip>:8001/health` from another device browser.
- If WSL does not forward the port automatically, use a Windows port proxy or Tailscale.

Example Windows port proxy from an Administrator PowerShell:

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8001 connectaddress=<wsl-ip> connectport=8001
```

Find the WSL IP from WSL:

```bash
hostname -I
```

Remove a proxy if needed:

```powershell
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8001
```

Tailscale often avoids WSL LAN forwarding issues because both devices join the same private overlay network.

## Firewall Checklist

- macOS: allow incoming connections for Python or terminal.
- Windows: allow Python/WSL on private networks.
- University/lab Wi-Fi: client isolation may block phone-to-laptop connections.
- VPN: may route traffic away from the LAN.
- Tailscale: confirm both devices are online in the same tailnet.

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
