# Mundi Style Guide

## Brand Idea

Mundi presents ResearchOS as a premium scientific companion: calm, connected, precise, and exploratory.

The approved logo is the frozen Mundi icon stored at:

```text
mobile/researchos_mobile/assets/brand/mundi_approved_icon_1024.png
```

This PNG is the only canonical source. The previous generated SVG/vector concept is not an approved source and must not be used.

## Logo Characteristics

- Hidden G structure
- Bright blue central star
- Blue beam extending toward the inner orbit
- Soft fading beam
- Golden outer constellation
- Inner constellation slightly fainter
- Subtle blue nebula on the right side
- Tiny background stars
- Premium dark navy background

The approved PNG remains the source of truth for exported assets.

## Colors

| Role | Hex |
| --- | --- |
| Dark space background | `#061123` |
| Deep navy | `#08182F` |
| Blue nebula | `#2B7CFF` |
| Electric blue star | `#5FD4FF` |
| Warm gold orbit | `#E6B85C` |
| White typography | `#FFFFFF` |

## Typography

Use minimal, modern type treatment:

- App wordmark: uppercase `MUNDI`
- Letter spacing: wide, around `3.5-4`
- Weight: medium/semi-bold
- Subtitle: smaller, wide tracking
- Avoid ornamental display fonts

## UI Usage

Use the logo mark for:

- launcher icon
- splash screen
- loading states
- welcome screen
- settings/about
- home/dashboard hero identity

Use `Powered by ResearchOS` in:

- splash
- settings/about
- welcome screen

Do not rename backend endpoints, package names, or ResearchOS platform documentation when the context is technical.

## Motion

Splash timing should remain short and premium:

- total visible animation about `1.8s`
- soft opacity and scale transitions
- no bouncing or playful motion
- fade cleanly into Home

## Accessibility

- Keep contrast high on dark backgrounds.
- Do not rely only on color for status or navigation.
- Ensure the wordmark is not the only app identifier for screen readers.
- Keep tap targets and labels consistent with the existing mobile design system.
