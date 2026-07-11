# Mundi Brand Lock v1.0

Mundi is the user-facing application identity for the ResearchOS platform.

ResearchOS remains the platform, backend, API namespace, package naming, and server identity. User-facing application screens should say **Mundi** unless they are explicitly describing the backend/platform relationship.

## Canonical Artwork

The official icon source of truth is:

```text
mobile/researchos_mobile/assets/brand/mundi_approved_icon_1024.png
```

This file is frozen. Do not redraw, regenerate, reinterpret, trace, vectorize, recolor, crop, recompose, or substitute the logo. All app icons, splash assets, web icons, and in-app logo marks must be generated from this PNG.

## Naming

- Application name: `Mundi`
- Subtitle: `Powered by ResearchOS`
- Backend/platform: `ResearchOS`
- Flutter package name: unchanged, `researchos_mobile`
- Bundle identifiers: unchanged

## Where Mundi Appears

- iOS display name
- macOS product name
- Flutter `MaterialApp` title
- first-run welcome screen
- startup/loading splash
- app logo
- Home hero
- dashboard hero
- Settings/About card
- launcher icons
- web/PWA icon

## Where ResearchOS Remains

- Backend API names
- server URLs and connection explanations
- docs about backend/server deployment
- package names and bundle identifiers
- platform subtitle: `Powered by ResearchOS`

## Generated Assets

Generated PNG sizes include:

```text
1024, 512, 256, 180, 152, 120, 87, 80, 76, 60, 58, 40, 29, 20, 16
```

Additional platform-specific generated sizes are included for:

- iOS `AppIcon.appiconset`
- Android mipmap launcher icons
- macOS `AppIcon.appiconset`
- Windows `.ico`
- Linux PNG icon
- Web/PWA icons and favicon

## Platform Notes

The current Flutter shell has iOS, macOS, and Linux platform projects. Android and Windows icon assets are generated under conventional platform paths so they are ready when those platform shells are restored or regenerated.

## Splash

The native launch screen uses a dark navy background and the approved Mundi icon asset. The Flutter startup screen uses the approved icon plus typography:

1. Logo appears.
2. Icon brightens/fades in.
3. `MUNDI` appears.
4. `Powered by ResearchOS` appears.
5. App continues to Home after connection succeeds.

The sequence is approximately 1.8 seconds when visible.

## Usage Rules

- Use the approved PNG as the only source.
- Never use the old ResearchOS `R` mark.
- Never use the old microscope/biotech app icon.
- Do not adapt the logo to UI changes; adapt UI around the logo.
- Preserve original proportions, spacing, nebula placement, stars, color, and geometry.
