# ResearchOS Home Command Center

The ResearchOS Home Command Center is the default Flutter landing page for daily laboratory work. It is designed to answer one question quickly: what should the scientist do next?

## Purpose

Home is separate from the deeper Dashboard. The Dashboard remains available for broader status and analytics, while Home focuses on immediate actions, active work, and recently used scientific objects.

## Sections

- Continue Working: active bench sessions, recent experiments, and pinned shortcuts.
- Create New: entry points for experiments, experiment designs, inventory, and resources.
- Today's Laboratory: experiment count, active sessions, inventory alerts, purchase requests, design reminders, and Bench Mode status.
- Recently Used: recent experiments, protocols, inventory items, resources, and other frequently accessed objects.
- Morning Brief: a compact entry point into the overnight/morning summary.
- Research Copilot: a direct path to evidence-backed assistant questions.
- Recent Searches: locally remembered search shortcuts.

## Quick Actions

The Home page exposes large touch-friendly actions:

- New Experiment
- New Experiment Design
- New Inventory Item
- New Purchase Request
- Start Bench Session
- Search
- Voice Assistant

These actions navigate to existing ResearchOS screens and APIs. The milestone does not add backend behavior.

## Personalization

The Flutter app stores lightweight personalization locally on the device using shared preferences:

- pinned items
- recent searches
- favorite experiments
- favorite protocols

This is intentionally local-only for now. Future multi-user deployments can sync this through user profiles and lab workspaces.

## Navigation

Home is now the first screen after a successful server connection. The existing Dashboard remains available as the second navigation destination. Morning Brief, Intelligence, and Whiteboard remain reachable from Home and the navigation bar.

## Future Work

- Server-backed pinned items and favorites.
- User-specific recent searches.
- Reorderable and collapsible Home cards.
- Deep links from Home cards directly into specific experiment, protocol, inventory, and purchase request detail pages.
- Role-aware quick actions for viewer, researcher, and admin users.
