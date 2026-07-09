# ResearchOS Demo Readiness

This checklist is for preparing ResearchOS for a macOS and iPhone demonstration. The goal is a polished, understandable demo without adding new scientific functionality.

## Current Demo Goal

Nathan should be able to hand an iPhone to another scientist and have the first screen communicate:

- ResearchOS is an AI-powered laboratory command center.
- It connects experiments, sessions, inventory, designs, search, and Research Copilot.
- It is local/server backed, so the phone must connect to a reachable ResearchOS backend URL.

## Critical

### Fixed: Apple platform scaffolding was missing

The Flutter project had Linux scaffolding but no `ios/` or `macos/` target folders. That prevented iPhone Simulator, physical iPhone, and macOS app testing from even starting.

Status: fixed by generating iOS and macOS Flutter platform targets.

### Fixed: Mobile navigation was too crowded

The bottom navigation exposed too many destinations for a phone. That made the app feel like an internal tool and increased the chance of confusing navigation during a handoff demo.

Status: fixed by keeping the bottom navigation focused on:

- Home
- Experiments
- Bench
- Search
- Settings

Additional screens remain reachable from Home and in-app cards.

### Verify before every demo: backend URL must be reachable from the phone

Phones cannot use `127.0.0.1` to reach a backend running on a laptop, WSL, or lab workstation.

Use one of:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://<reachable-ip>:8001 ./scripts/demo.sh
```

or:

```bash
PUBLIC_BASE_URL=http://<reachable-ip>:8001 ./scripts/mobile_dev_server.sh
```

Then open the same URL from Safari on the iPhone:

```text
http://<reachable-ip>:8001/health
```

Expected:

```json
{"status":"ok","project":"ResearchOS"}
```

## Important

### Fixed: App identity on Apple targets

Generated Apple project names used the default Flutter project naming. For a demo, the app should appear as ResearchOS.

Status: fixed:

- iOS display name: `ResearchOS`
- macOS product name: `ResearchOS`
- bundle identifier namespace: `com.researchos.mobile`

### Server Connection screen is demo-safe

The first launch still requires a server URL. This is expected for the current lab-server architecture, but Nathan should configure the URL before handing over the phone.

Before a demo:

1. Start the backend with a reachable mobile URL.
2. Open the Flutter app.
3. Enter the server URL.
4. Tap `Test Connection`.
5. Tap `Connect`.
6. Confirm Home loads.

### Loading and error states

The current Flutter screens have basic loading/error states. They are acceptable for the demo, but network failures should be avoided by checking the backend URL before presenting.

### Placeholder screens

Some future-facing areas still contain placeholder or scaffolded workflows. For the demo, steer through:

- Home
- Bench Mode
- Experiments
- Search
- Research Copilot
- Inventory
- Morning Brief

Avoid presenting unfinished provider internals unless specifically asked.

## Nice To Have

- Custom ResearchOS app icon instead of generated Flutter placeholder icons.
- Branded splash screen.
- More direct deep links from Home cards into specific object detail pages.
- Server-backed pinned items and recent searches.
- TestFlight setup.
- HTTPS with a stable lab-server URL.
- Demo screenshots in README/docs.

## Pre-Demo Checklist

### Backend

1. Stop stale backend processes:

```bash
./scripts/stop.sh
```

2. Start ResearchOS for local desktop demo:

```bash
RESEARCHOS_OPEN_BROWSER=0 ./scripts/demo.sh
```

3. Start ResearchOS for phone demo:

```bash
HOST=0.0.0.0 PORT=8001 PUBLIC_BASE_URL=http://<reachable-ip>:8001 ./scripts/demo.sh
```

4. Verify health:

```bash
curl http://127.0.0.1:8001/health
```

5. From iPhone Safari, verify:

```text
http://<reachable-ip>:8001/health
```

### Flutter App

1. Open the Flutter app.
2. Enter the reachable backend URL.
3. Tap `Test Connection`.
4. Tap `Connect`.
5. Confirm the Home Command Center appears.
6. Confirm bottom navigation shows only Home, Experiments, Bench, Search, and Settings.

### Suggested Demo Flow

1. Home: show ResearchOS as the laboratory command center.
2. Search: search for `SAG` or `BRN3B`.
3. Experiments: open the experiment list.
4. Bench: show large one-handed actions for active lab work.
5. Research Copilot from Home: ask a precise question.
6. Inventory: show lab operations are part of the same system.
7. Morning Brief: show proactive daily summary.

### Validation Commands

Run before showing the app:

```bash
cd mobile/researchos_mobile
flutter test
```

```bash
./scripts/demo.sh
./scripts/smoke_test.sh
./scripts/stop.sh
```

On a Mac with Xcode installed:

```bash
cd mobile/researchos_mobile
flutter devices
flutter run -d macos
flutter run -d "iPhone 15"
```

Use the actual simulator name shown by `flutter devices`.

## Environment Notes

This repository was prepared in a Linux/WSL-style environment. iPhone Simulator and macOS app execution require macOS with Xcode installed. The iOS/macOS project scaffolding is present, but final simulator/device execution must be performed on Nathan's Mac.
