# Mundi Brand Integration

Mundi is the user-facing mobile application identity.

ResearchOS remains the platform, backend, API namespace, package naming, and server identity. User-facing mobile screens should say **Mundi** unless they are explicitly describing the backend/platform relationship.

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

## Where ResearchOS Remains

- Backend API names
- server URLs and connection explanations
- docs about backend/server deployment
- package names and bundle identifiers
- platform subtitle: `Powered by ResearchOS`

## Assets

Master vector:

```text
mobile/researchos_mobile/assets/brand/mundi_soft_orbit_nebula_hint.svg
```

Generated PNG sizes:

```text
1024, 512, 256, 180, 120, 76, 60, 40, 29, 20, 16
```

Additional platform-specific generated sizes are included for iOS/macOS icon catalogs and Android launcher densities.

## Platform Notes

The current Flutter shell has iOS, macOS, and Linux platform projects. Android launcher icon assets have been generated under the conventional Android resource path so they are ready when the Android shell is restored.

## Splash

The native launch screen uses a dark navy background and Mundi logo asset. The Flutter startup screen uses the in-app Mundi splash sequence:

1. Logo appears.
2. Central mark brightens through the logo animation.
3. `MUNDI` appears.
4. `Powered by ResearchOS` appears.
5. App continues to Home after connection succeeds.

The sequence is approximately 1.8 seconds when visible.
