# Mobile PWA

ResearchOS is a responsive web app that can be used from iPhone, Android,
tablet, and desktop. Milestone 49 adds the Progressive Web App foundation:

- responsive dashboard and experiment workspace
- mobile bottom navigation
- PWA manifest
- service worker skeleton
- install/add-to-home-screen metadata

ResearchOS is still served by the existing FastAPI backend. This is not a
native iOS or Android app.

## Start ResearchOS

On the machine running ResearchOS:

```bash
./scripts/demo.sh
```

Open:

```text
http://127.0.0.1:8001
```

For phones or tablets, the device must be able to reach the server. If the
backend is running inside WSL or on a laptop, use that machine's reachable LAN
address and ensure the firewall allows access. `127.0.0.1` only works on the
same device that is running the server.

## iPhone / iPad

1. Open Safari.
2. Navigate to the ResearchOS dashboard URL.
3. Tap Share.
4. Tap Add to Home Screen.
5. Confirm the name ResearchOS.

iOS uses Safari's web app behavior. The app still talks to the FastAPI server,
so the server must be reachable from the iPhone or iPad.

## Android

1. Open Chrome.
2. Navigate to the ResearchOS dashboard URL.
3. Tap the browser menu.
4. Tap Install app or Add to Home screen.
5. Confirm ResearchOS.

Android Chrome uses the PWA manifest and service worker metadata when available.

## Mobile Navigation

At phone widths, ResearchOS hides the desktop sidebar and shows bottom
navigation for:

- Dashboard
- Experiments
- New Entry
- Assistant
- Graph

The New Experiment dictation page uses larger touch targets and a taller notes
area for phone dictation or paste workflows.

## Experiment Workspace

Experiment Workspace pages are optimized for scrolling on narrow screens. The
workspace uses collapsible sections for timeline, microscopy, GraphPad,
spreadsheets, statistics, literature, related entities, files, limitations, and
provenance.

## OneNote Auth Compatibility

Microsoft OneNote login remains a browser-based Microsoft Graph delegated auth
flow. It should work in mobile browsers once UCSD tenant approval/app
registration is complete and the redirect URI used by ResearchOS is reachable
from the device.

For local development, the registered redirect URI is still commonly:

```text
http://localhost:8001/auth/callback
```

Mobile testing with a LAN URL may require adding a matching redirect URI in the
Microsoft Entra app registration.

## Current Limitations

- Offline mode is a skeleton for static assets only.
- API responses still require the backend server.
- No native push notifications or native file integrations are implemented.
- No native iOS or Android app has been built.
