# Laboratory Whiteboard

The Laboratory Whiteboard is a continuously updating situational awareness view for a shared lab monitor.

It is designed for glanceability, not data entry.

## API

```http
GET /whiteboard
```

The response is display-ready and includes:

- active experiments
- today's tasks
- today's imaging
- today's collections
- today's treatments
- inventory alerts
- purchase requests
- recent literature
- Research Copilot cards
- Laboratory Intelligence items
- rotation panels
- refresh/rotation timing hints

Example:

```bash
curl -s http://127.0.0.1:8001/whiteboard
```

## Web UI

Open:

```text
http://127.0.0.1:8001/#/whiteboard
```

The web view uses large cards, high contrast, dark-mode-ready colors, and a responsive grid suitable for desktop or TV display.

When the whiteboard route is active, the browser refreshes the whiteboard data every 60 seconds and advances the rotation panel.

## Rotation Mode

Rotation panels include:

- Dashboard
- Timeline
- Experiment Status
- Inventory
- Morning Brief

This is intended for a passive lab monitor where interaction is minimal.

## Flutter

The Flutter mobile preview includes a Whiteboard tab that consumes the same `/whiteboard` endpoint.

The layout supports portrait and landscape. Landscape mode shows denser cards for tablet or wall-display use.

## Empty Lab Behavior

If no data has been loaded, sections show explicit empty states rather than blank panels.

## Design Principles

- Use actual ResearchOS records only.
- Never invent lab status.
- Keep cards readable from a distance.
- Prefer high-signal counts and short summaries.
- Preserve route metadata so users can open the source object from desktop/mobile.

## Future Work

- Dedicated kiosk mode.
- Browser full-screen prompt.
- Per-lab custom section ordering.
- Live WebSocket refresh.
- Calendar and reminder integrations.
- Smart monitor deployment profile.
