# ResearchOS Mobile Design System

The Flutter design system lives in:

```text
mobile/researchos_mobile/lib/design_system/
```

It provides reusable Material 3 components for the ResearchOS mobile app. The goal is to keep the mobile UI consistent while preserving the rule that Flutter remains a thin client over `/mobile/*` backend endpoints.

## Principles

- Mobile-first.
- Bench-friendly touch targets.
- Material 3.
- Dark mode ready.
- Accessible labels and semantic containers.
- Reusable scientific UI components.
- Responsive layouts for phone, tablet, and desktop Flutter.
- No duplicated backend research logic.

## Theme

`ResearchOsTheme` defines:

- light theme
- dark theme
- Material 3 color scheme
- typography weights
- card shape/elevation
- button shape/minimum size
- input styling
- navigation bar behavior

The app uses:

```dart
theme: ResearchOsTheme.light(),
darkTheme: ResearchOsTheme.dark(),
themeMode: ThemeMode.system,
```

## Spacing

`ResearchOsSpacing` centralizes:

- `xs`, `sm`, `md`, `lg`, `xl`, `xxl`
- screen padding
- card padding
- sheet padding
- standard border radii

Use spacing constants instead of one-off pixel values when creating new screens.

## Cards

Reusable cards:

- `ResearchOsCard`
- `ResearchOsInfoCard`
- `ResearchOsExperimentCard`
- `ResearchOsCopilotCard`
- `ResearchOsStatisticsCard`

These should be preferred over raw `Card` or ad hoc `ListTile` blocks.

## Buttons

`ResearchOsActionButton` provides large, accessible, bench-friendly touch targets.

Use it for:

- Bench Mode actions
- capture actions
- session actions
- major workflow actions

## Scientific Badges

`ScientificBadge` supports:

- general labels
- compounds
- markers
- workflow stages
- warnings

Badges should be used for scientific entities and workflow state instead of plain text chips.

## Timeline

`ResearchOsTimeline` and `TimelineItem` provide a reusable vertical timeline pattern for:

- experiment timeline previews
- session events
- workflow transitions
- asset history

## Responsive Layouts

`ResearchOsBreakpoints` and `ResearchOsResponsive` define layout decisions for:

- phone
- tablet
- desktop

Bench Mode uses responsive column counts for large action buttons.

## Animation

`FadeSlideIn` provides a subtle transition for screen content. Animations should be short, functional, and never distract from bench workflow.

## Accessibility

Components include semantic labels where useful. New UI should preserve:

- readable text sizes
- high contrast
- large touch targets
- clear button labels
- non-color-only state indicators

## Adding New Components

Add reusable primitives under `lib/design_system/` and export them from:

```text
researchos_design_system.dart
```

Screens should import the barrel file:

```dart
import '../design_system/researchos_design_system.dart';
```

Avoid screen-specific components unless the UI is genuinely unique to one workflow.
