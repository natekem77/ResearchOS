# ResearchOS 5-Minute Boss Demo Script

## 0:00-0:30 — Opening

ResearchOS is a mobile-first laboratory command center. It brings experiments, notebook context, timelines, inventory, designs, analyses, and Research Copilot into one place.

The official notebook still stays official. ResearchOS is the layer that helps the lab find, structure, and act on the information already being created.

## 0:30-1:15 — iPhone First Run

Show the ResearchOS onboarding screen.

Say:

The phone connects to a ResearchOS backend running on a Mac, lab workstation, or future lab server. In the iPhone Simulator, localhost connects to the Mac backend. On a real iPhone, we use a LAN, Tailscale, or HTTPS URL.

Tap:

1. `Use Local Demo Server` for Simulator, or enter the LAN/Tailscale URL for a physical iPhone.
2. `Test Connection`.
3. `Connect`.

Expected result: Home opens.

## 1:15-2:00 — Home Command Center

Show the Home screen.

Say:

This is the daily starting point. A scientist can immediately see Morning Brief, Bench Mode, experiment designs, active experiments, inventory, whiteboard, and global search.

Tap through the cards briefly:

- Morning Brief: what changed and what needs attention.
- Bench Mode: one-handed capture at the bench.
- Experiment Designs: treatment timelines and reminders.
- Inventory: reagents, purchase requests, and alerts.
- Search: the fastest path to any experiment or entity.

## 2:00-3:00 — Bench Mode

Open Bench Mode.

If no active session exists, tap `Start Demo Session`.

Say:

Bench Mode is designed for one-handed use while standing at the bench. It has large actions for voice notes, observations, treatments, media changes, images, and finishing the session.

Tap:

1. `Observation`
2. Enter a short note such as `Organoids look healthy before D32 imaging.`
3. Save it.

Say:

The goal is fast documentation without breaking the scientist's flow.

## 3:00-3:45 — Search and Experiments

Open Search.

Search:

```text
SAG
```

Say:

ResearchOS searches across experiments, notebook-derived records, knowledge graph entities, images, statistics, literature, and assets. The scientist should not have to remember where a detail was written.

Open Experiments.

Say:

Each experiment becomes a connected workspace over time: notebook entries, timelines, images, GraphPad, spreadsheets, statistics, literature, and copilot summaries.

## 3:45-4:30 — Inventory and Experiment Design

Open Inventory from Home.

Say:

ResearchOS also handles practical lab operations: low-stock alerts, expiring reagents, purchase requests, receiving, usage tracking, and methods-ready reagent details.

Return Home and point to Experiment Designs.

Say:

The design planner turns treatment schedules like D1/D9 SAG into reminders, timelines, and eventually plate layouts. That helps avoid missed treatment and imaging days.

## 4:30-5:00 — OneNote and Future Integration

Say:

Today the demo uses local sample data so development is not blocked by Microsoft tenant approval. The OneNote integration is designed as read-only first. OneNote remains the official notebook, and ResearchOS becomes the intelligence and workflow layer around it.

Future approval from UCSD IT will let ResearchOS sync OneNote pages through Microsoft Graph. Write-back stays disabled until separate create/write permissions are approved.

## Closing

ResearchOS is not just a database. It is a mobile laboratory companion: a scientist can plan an experiment, run it at the bench, capture notes, connect data, track inventory, and ask evidence-backed questions from the same system.
