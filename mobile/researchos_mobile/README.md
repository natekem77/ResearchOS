# ResearchOS Mobile

This is the initial Flutter shell for the ResearchOS mobile app.

The app is intentionally thin. It calls the `/mobile/*` API endpoints exposed by the FastAPI backend and does not duplicate provider, Knowledge Graph, workspace, statistics, or OneNote logic.

Default backend URL:

```text
http://127.0.0.1:8001
```

For iPhone, Android, and physical tablets, `127.0.0.1` points to the device itself. Use a reachable lab-server URL, HTTPS URL, Tailscale URL, or emulator loopback address instead.

Bench Mode is the Home tab and is designed for one-handed experiment capture during active sessions.

See [../../docs/FLUTTER_APP.md](../../docs/FLUTTER_APP.md), [../../docs/BENCH_MODE.md](../../docs/BENCH_MODE.md), and [../../docs/MOBILE_DESIGN_SYSTEM.md](../../docs/MOBILE_DESIGN_SYSTEM.md).
