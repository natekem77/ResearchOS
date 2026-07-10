# Network-Agnostic Mobile Connections

ResearchOS mobile uses saved server profiles so scientists do not have to type a changing LAN IP every time they switch networks.

## Connection Priority

On launch, the mobile app tries:

1. Preferred profile
2. Production HTTPS profiles
3. Tailscale/MagicDNS profiles
4. Last successful custom profiles
5. Local development fallback: `http://127.0.0.1:8001`
6. Manual server entry

Each profile is validated with `/mobile/connection-info` or `/mobile/status` using a short timeout. If one profile succeeds, the app opens Home directly.

## Profile Types

- Production: stable hosted HTTPS URL, such as `https://researchos.lab.edu`
- Tailscale: private stable URL, such as `https://researchos-host.example-tailnet.ts.net`
- Local: simulator/macOS development URL, usually `http://127.0.0.1:8001`
- Custom: LAN IP, temporary host, or other manually entered URL

No credentials, Tailscale tokens, API keys, or secrets are stored in the mobile app.

## Mode A: Simulator + Local Mac Backend

Start the backend on the Mac:

```bash
RESEARCHOS_OPEN_BROWSER=0 ./scripts/demo.sh
```

Run the app in iPhone Simulator:

```bash
cd mobile/researchos_mobile
flutter run -d "iPhone 17"
```

Use:

```text
http://127.0.0.1:8001
```

The iOS Simulator can reach the Mac loopback interface.

## Mode B: Physical iPhone + Tailscale/MagicDNS

Start ResearchOS on a machine connected to the tailnet:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=https://researchos-host.example-tailnet.ts.net ./scripts/demo.sh
```

On the iPhone:

1. Open Tailscale.
2. Confirm the device is connected to the tailnet.
3. Open ResearchOS.
4. Add a `Tailscale / Private Server` profile.
5. Enter the MagicDNS HTTPS URL.
6. Test and connect.

ResearchOS does not control the Tailscale app and does not store Tailscale credentials.

## Mode C: Physical iPhone + Hosted HTTPS

Use a stable HTTPS endpoint:

```text
https://researchos.lab.example.edu
```

Configure the backend:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=https://researchos.lab.example.edu ./scripts/run_server.sh
```

The app should prefer this profile automatically after it succeeds once.

## Offline Screen

If no profile works, the app shows a connection screen with:

- saved servers
- retry buttons
- edit/delete actions
- Add Production Server
- Add Tailscale Server
- Add Local/Custom Server
- concise VPN/Tailscale reminders

Raw stack traces are not shown to users.

## Server Identity

The app reads `/mobile/connection-info` for:

- server name
- version
- environment
- demo/development status
- `PUBLIC_BASE_URL`
- recommended mobile URL
- connection warnings
