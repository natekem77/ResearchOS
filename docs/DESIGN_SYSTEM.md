# ResearchOS Design System

ResearchOS Experience v1 defines a calm, modern interface for scientific work. The product should feel closer to Apple Health, Linear, Things 3, Notion, Arc Browser, and GitHub Mobile than to an internal lab database.

## Design Philosophy

ResearchOS should feel trustworthy, precise, and quiet. The interface should help scientists see what is known, what is inferred, what is suggested, and where each statement came from.

Core principles:

- Scientific work stays provenance-first.
- AI-assisted content is clearly separated from observed data.
- The scientist stays in control.
- Bench workflows require large touch targets and minimal typing.
- Every screen should work on phone, tablet, desktop, and PWA widths.

## Typography

ResearchOS uses Material 3 typography with heavier weights for scan-friendly scientific information.

- Page titles use `headlineSmall` or `headlineMedium` with weight 800.
- Card titles use `titleMedium` with weight 800.
- Compact metadata uses `labelSmall` or `labelMedium`.
- Body text uses normal Material 3 body sizes with comfortable line height.
- Letter spacing remains `0` for clarity and accessibility.

## Spacing And Grid

Spacing tokens live in `ResearchOsSpacing`.

- `xs`: 4 px
- `sm`: 8 px
- `md`: 12 px
- `lg`: 16 px
- `xl`: 24 px
- `xxl`: 32 px

Cards use 16 px internal padding by default. Compact cards use 12 px. Responsive grids choose 2 columns on phones, 3 on tablets, and 4 on desktop where space allows.

## Radius, Elevation, And Shadows

ResearchOS uses restrained rounded corners:

- Compact controls: 8 px
- Standard cards: 12 px
- Larger empty-state tiles: 16 px

Cards use low elevation with a soft border and subtle shadow. The goal is depth without decorative clutter.

## Color System

The primary seed color is blue (`#2563EB`). Entity and state colors are intentionally distinct so screens do not become one-note.

Status colors:

- Success: green
- Warning: amber
- Error: red
- Info: blue

Workflow colors:

- Planning: slate
- Running/Treatment: blue
- Waiting/Media: amber
- Imaging: violet
- Quantification/Statistics: teal
- Writing/Submitted: pink
- Published/Archived: green

Scientific entity colors:

- Compounds/treatments: blue
- Markers/genes/proteins: violet
- Cell lines: teal
- Batches: amber
- Literature: pink
- Assets/files: slate

## Components

Reusable Flutter components are exported from `lib/design_system/researchos_design_system.dart`.

Cards:

- `ResearchOsCard`
- `ResearchOsInfoCard`
- `ResearchOsSummaryCard`
- `ResearchOsExperimentCard`
- `ResearchOsAssetCard`
- `ResearchOsTimelineCard`
- `ResearchOsKnowledgeCard`
- `ResearchOsCopilotCard`
- `ResearchOsStatisticsCard`
- `ResearchOsSearchResultCard`
- `ResearchOsExpandableCard`

Badges:

- `ScientificBadge`
- `WorkflowBadge`
- `EvidenceBadge`
- `SessionBadge`

States:

- `ResearchOsEmptyState`
- `ResearchOsLoadingSkeleton`
- `ResearchOsErrorState`

Layout:

- `ResearchOsSectionHeader`
- `ResearchOsWorkflowIndicator`
- `ResearchOsResponsive`
- `ResearchOsBreakpoints`

Bench controls:

- `ResearchOsActionButton`

## Animation

Animation tokens live in `ResearchOsAnimation` and `ResearchOsTokens`.

- Fast: 140 ms
- Standard: 220 ms
- Slow: 320 ms
- Curve: ease-out cubic

Current animations include:

- Page/navigation transitions
- Card expansion
- Search result entry
- Loading shimmer
- Micro-interactions on tappable cards and controls

Animations should clarify state changes. They should not distract from scientific content.

## Themes

ResearchOS supports:

- Light theme
- Dark theme
- System theme

The Flutter app uses `ThemeMode.system` by default. Components should always draw colors from theme or design tokens, never one-off local palettes.

## Dashboard Pattern

The dashboard should summarize the current workspace:

- ResearchOS welcome card
- Compact statistics
- Today's work
- Active session
- Recent experiments
- Research Copilot
- Recent imports

Empty states should be useful and specific, not blank.

## Experiment Workspace Pattern

The Experiment Workspace is the primary experiment page. It should prioritize:

- Overview
- Workflow status
- Asset and note counts
- Statistics
- Images
- GraphPad
- Spreadsheets
- Timeline
- Knowledge graph
- Evidence
- Research Copilot

Every section should remain readable on a phone and expandable when dense.

## Bench Mode Pattern

Bench Mode is optimized for one-handed use while standing at the bench.

Rules:

- Large touch targets, at least 88 px for primary bench actions.
- Minimal typing.
- High contrast.
- Clear active-session status.
- Fast access to voice note, observation, treatment, media change, capture image, attach file, and finish session.

## Search Pattern

Search should feel like Spotlight:

- Prominent global search field.
- Live results after short input.
- Grouped results.
- Keyboard-friendly on desktop.
- Quick query chips on mobile.
- Result cards with type labels and compact snippets.

## Accessibility

Required standards:

- Minimum 48 px touch targets, 88 px for bench actions.
- Screen-reader labels for tappable cards and controls.
- No text-only color coding for scientific status.
- Scalable text without clipped buttons.
- High contrast in light and dark mode.

## Implementation Notes

Current implementation focus:

- Flutter mobile/PWA shell.
- Shared design tokens and component library.
- Dashboard redesign.
- Spotlight-style search.
- Experiment Workspace presentation.
- Bench Mode visual polish.

Backend APIs remain unchanged except for consuming existing mobile endpoints from the Flutter client.
