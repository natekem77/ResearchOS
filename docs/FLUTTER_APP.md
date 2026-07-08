# Flutter Mobile App

ResearchOS now includes an initial Flutter mobile app scaffold under:

```text
mobile/researchos_mobile/
```

The app is a thin client over the `/mobile/*` API namespace. It does not duplicate provider logic, Knowledge Graph construction, statistics parsing, workspace aggregation, OneNote internals, event bus behavior, or agent logic.

## Current Scope

Implemented screens:

- Server Connection
- Bench Mode
- Experiments
- Experiment Detail
- Search
- Copilot
- Settings

Implemented API calls:

- `GET /mobile/status`
- `GET /mobile/dashboard`
- `GET /mobile/experiments`
- `GET /mobile/experiments/{experiment_id}`
- `GET /mobile/search?q=...`
- `GET /mobile/auth/me`
- `GET /mobile/settings`
- `GET /mobile/sessions/active`
- `POST /mobile/sessions/{session_id}/note`
- `POST /mobile/sessions/{session_id}/end`
- `POST /mobile/assistant/copilot`

Not implemented yet:

- Authentication/login
- Microsoft OneNote login
- Offline sync
- Push notifications
- Native file import
- Full Experiment Workspace rendering

## Bench Mode

Bench Mode is the mobile Home tab. It is designed for active laboratory work:
large touch targets, minimal typing, portrait-first layout, and fast timestamped
capture into the active ResearchOS session.

See [docs/BENCH_MODE.md](BENCH_MODE.md).

## Setup

Install Flutter from the official Flutter documentation for your OS.

Then run:

```bash
cd mobile/researchos_mobile
flutter pub get
```

This repository stores the Dart app scaffold, not generated platform folders. After Flutter is installed, generate platform files locally:

```bash
cd mobile/researchos_mobile
flutter create .
```

Run the ResearchOS backend in another terminal:

```bash
./scripts/demo.sh
```

Run the mobile app:

```bash
cd mobile/researchos_mobile
flutter run
```

## Server URL Notes

The default server URL is:

```text
http://127.0.0.1:8001
```

This works for desktop Flutter when the backend is running on the same machine.

For a physical iPhone or Android device, `127.0.0.1` points to the phone itself, not the lab workstation. Use a reachable server URL instead:

- lab workstation LAN address
- HTTPS reverse proxy URL
- Tailscale URL
- UCSD-hosted server URL
- Android emulator loopback, commonly `http://10.0.2.2:8001`

Production mobile use should require HTTPS, real authentication, secure session handling, workspace isolation, and a production safety review.

## iOS Notes

Future iOS development will need:

- macOS with Xcode
- Apple Developer account for TestFlight/App Store
- HTTPS backend URL for production-like testing
- Privacy policy describing local/server storage, Microsoft Graph use, and optional AI provider data handling

## Android Notes

Future Android development will need:

- Android Studio or Android SDK tooling
- Google Play developer account for distribution
- HTTPS backend URL for production-like testing
- Clear data handling and privacy documentation

## Future TestFlight/App Store Path

Before App Store or TestFlight distribution, ResearchOS should add:

- Microsoft identity as app login
- Secure backend sessions
- API versioning
- CORS and HTTPS hardening
- Workspace-level authorization
- Secure token storage strategy
- Audit logging
- Privacy policy and data handling disclosures
- UCSD IT review for Microsoft Graph access

The first mobile release should remain a companion app for lab-server ResearchOS rather than a standalone data system.
