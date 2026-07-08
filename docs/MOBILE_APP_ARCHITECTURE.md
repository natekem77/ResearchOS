# Mobile App Architecture

This document plans the future native/mobile ResearchOS app. It does not implement Flutter, React Native, Swift, Kotlin, or any native mobile code yet.

## Recommended Architecture

Recommended path:

1. Keep the FastAPI backend as the system of record.
2. Continue improving the web/PWA frontend for near-term mobile access.
3. Add a future Flutter app when ResearchOS needs native mobile capabilities.
4. Keep a shared HTTP API layer for web, PWA, and native clients.
5. Keep Microsoft OneNote access in the backend through Microsoft Graph delegated auth.

High-level architecture:

```text
iPhone / Android / Tablet / Desktop
        |
        | Web/PWA today
        | Flutter app later
        v
Shared ResearchOS API
        |
        v
FastAPI backend
        |
        | SQLite/local data initially
        | Chroma/vector index
        | Asset providers
        | Workflow engine
        | Knowledge graph
        | Assistant/Copilot
        v
Local/lab/cloud storage and Microsoft Graph
```

The backend should own:

- authentication and authorization
- Microsoft Graph token handling
- OneNote sync
- local storage
- workflow state
- Knowledge Graph
- provider ingestion
- assistant/RAG orchestration

The mobile app should own:

- fast mobile navigation
- dictation capture
- review-before-save workflows
- offline-friendly drafts where safe
- mobile file/image selection
- push-notification hooks in a future phase

## Why FastAPI Remains Central

FastAPI already exposes ResearchOS as provider-agnostic APIs. Keeping it central avoids duplicating scientific logic inside mobile clients.

The mobile app should not reimplement:

- notebook parsing
- experiment extraction
- workflow transitions
- asset linking
- Knowledge Graph construction
- statistics interpretation
- OneNote sync
- AI provider calls

Instead, the mobile app should call stable API endpoints and display provenance-backed data from the backend.

## Client Options

### PWA Only

Best for: current ResearchOS demos and early lab use.

Pros:

- Already exists.
- One codebase for desktop and mobile browsers.
- Easy to deploy from the FastAPI backend.
- No App Store review.
- Good enough for dashboard, search, assistant, entries, and workspace browsing.

Cons:

- Limited offline capability.
- Browser speech recognition behavior varies.
- iOS background behavior is limited.
- Native file/image capture is less polished.
- Push notifications are more constrained.
- Mobile distribution depends on users adding it to the home screen.

Recommendation: use this for Phase 1 and Phase 2.

### Flutter App

Best for: future cross-platform native mobile app.

Pros:

- One codebase for iOS and Android.
- Good performance and consistent UI.
- Strong camera/file/audio integration.
- Mature offline storage options.
- Suitable for App Store and Google Play.
- Can share API models conceptually with backend schemas.

Cons:

- Requires mobile build pipeline.
- Requires Apple Developer and Google Play accounts.
- Requires mobile auth, token storage, release management, crash reporting, and privacy review.
- Adds a second frontend to maintain.

Recommendation: preferred native path after the PWA and lab-server deployment are stable.

### React Native

Best for: teams already invested in TypeScript/React mobile.

Pros:

- JavaScript/TypeScript ecosystem.
- Large community.
- Can share some UI/domain conventions with a future React web app.
- Good native module ecosystem.

Cons:

- Native module compatibility can become maintenance-heavy.
- Build and dependency churn can be significant.
- ResearchOS current frontend is plain HTML/CSS/JS, so there is not much React code to share today.

Recommendation: viable, but less compelling than Flutter unless the project moves to React across the frontend.

### Native Swift/Kotlin

Best for: maximum platform-specific polish.

Pros:

- Best integration with iOS and Android platform features.
- Strong security/token storage primitives.
- Best long-term native UX if each platform has dedicated owners.

Cons:

- Two codebases.
- Higher maintenance burden.
- Slower feature parity.
- Requires platform-specific expertise.

Recommendation: not the best first native path for ResearchOS unless the team later has dedicated iOS and Android developers.

## iPhone and Android Access

### Local Development

Localhost URLs only work on the machine running ResearchOS:

```text
http://127.0.0.1:8001
```

Phones cannot reach this URL unless the backend is running on the phone itself, which is not the current architecture.

### Lab Server

For phones/tablets to access ResearchOS, run the backend on a reachable lab workstation or server:

```bash
./scripts/run_server.sh --host 0.0.0.0 --port 8001
```

Use a LAN, VPN, Tailscale, or institutional hostname:

```text
https://researchos.lab.example.edu
```

Mobile users then open the URL in Safari/Chrome and install the PWA.

### Cloud or Hosted Deployment

A cloud or UCSD-hosted deployment is the likely path for broader use:

- HTTPS by default
- stable DNS
- managed backups
- institutional access controls
- UCSD-owned Microsoft Entra app registration
- easier mobile/PWA access

Use cloud/hosted mode only after privacy/security review.

### Microsoft Login

Microsoft login should remain browser-based OAuth through Microsoft Graph delegated auth.

Mobile implications:

- Redirect URI must match the deployed ResearchOS URL.
- HTTPS should be used for shared access.
- UCSD tenant approval is required for real lab OneNote sync.
- Public-client local development should not require a client secret.

Local redirect example:

```text
http://localhost:8001/auth/callback
```

Lab/server redirect example:

```text
https://researchos.lab.example.edu/auth/callback
```

### OneNote Sync

OneNote sync should remain backend-owned:

- mobile app starts login or sync
- backend stores and refreshes delegated tokens securely
- backend fetches notebooks/sections/pages from Microsoft Graph
- backend converts pages into ResearchDocuments
- mobile app reads normalized ResearchOS data from the API

The mobile app should not directly parse OneNote HTML or store Microsoft tokens in an ad hoc way.

### Voice Dictation

Short term:

- PWA uses browser dictation where available.
- Users can type or paste notes if speech recognition is unavailable.

Future Flutter app:

- native speech-to-text integration
- audio capture with review-before-save
- local draft creation
- optional server-side AI formatting

Voice capture must preserve the review-before-save rule. ResearchOS should never silently write dictated content into OneNote.

### Offline Limitations

Current PWA offline behavior is only a static shell skeleton. The API still requires the backend.

Future mobile offline work requires:

- authenticated local mobile storage
- offline draft queue
- conflict handling
- sync status
- clear warnings when data has not reached the lab server
- careful handling of OneNote write-back once approved

Offline OneNote sync is not planned for the near-term MVP.

## App Store Path

### Apple Developer Account

Required for:

- TestFlight distribution
- App Store release
- iOS signing
- app identifiers
- push notifications later

The account should ideally be owned by the lab, institution, or project organization rather than a personal account if ResearchOS becomes a durable lab tool.

### Google Play Account

Required for:

- internal testing tracks
- closed testing
- production Android release

### Privacy Policy

Before app distribution, ResearchOS needs a public privacy policy describing:

- what data is collected
- where data is stored
- whether cloud AI is used
- whether Microsoft Graph/OneNote data is accessed
- how users can delete local/server data
- whether analytics/crash reporting are used
- contact information

### Data Handling

The native app must clearly distinguish:

- local mobile drafts
- lab-server data
- Microsoft OneNote data
- optional cloud AI data
- exported files

Sensitive research data should not be sent to third-party AI providers unless explicitly configured and approved.

### Institutional Deployment

For UCSD/lab use, options include:

- private TestFlight group
- Google Play closed/internal test
- Apple Business Manager or institutional MDM
- UCSD-managed app registration and deployment
- web/PWA deployment only for early lab use

Institutional deployment may be preferable before public App Store distribution.

## Backend Changes Needed Before Mobile

Before a real mobile app, ResearchOS needs stronger backend foundations.

### Authentication

Current local/demo mode does not provide a full ResearchOS user login system. Mobile/server deployments need user authentication separate from Microsoft Graph.

Options:

- institutional SSO
- OAuth/OIDC
- lab-managed accounts
- reverse-proxy auth for early internal deployment

### User Accounts

Needed for:

- personalized dashboards
- ownership of drafts
- per-user OneNote tokens
- audit trails
- comments/reviews
- PI approvals

### API Versioning

Mobile apps update slower than web apps, so APIs need versioning:

```text
/api/v1/...
```

Versioning should cover request/response schemas, deprecations, and compatibility windows.

### HTTPS

Shared mobile access must use HTTPS. This is required for security and improves browser/mobile platform compatibility.

### CORS

If the native app or hosted web client uses a different origin from the backend, CORS must be configured intentionally:

- allowed origins
- allowed headers
- credentials/token behavior
- development vs production origins

Do not use permissive wildcard CORS for real deployments.

### Secure Token Storage

Backend:

- Microsoft refresh/access tokens should be encrypted at rest.
- Tokens should be scoped to users.
- Token access should be auditable.

Mobile app:

- app session tokens should use Keychain on iOS and Keystore on Android.
- Microsoft tokens should preferably stay backend-side unless a future architecture explicitly requires mobile-held tokens.

### Multi-User Permissions

Needed before real lab deployment:

- roles: researcher, PI, admin, viewer
- experiment ownership/collaboration
- draft ownership
- notebook/provider access boundaries
- audit trail
- approval workflow

## Roadmap

### Phase 1: PWA

Status: current direction.

Goals:

- mobile-responsive dashboard
- New Experiment dictation page
- Experiment Workspace on phone/tablet
- Add to Home Screen guidance
- basic service worker shell

### Phase 2: Lab-Server Mobile Access

Goals:

- run ResearchOS on a lab workstation/server
- HTTPS or VPN/Tailscale access
- reachable `PUBLIC_BASE_URL`
- correct Microsoft redirect URI
- Settings readiness cards
- labmate access through phone/tablet browser

### Phase 3: Flutter Prototype

Goals:

- Flutter shell
- login to ResearchOS backend
- dashboard
- experiment/workflow workspace
- voice note/draft entry flow
- assistant questions
- API client generated or typed from schemas

No OneNote write-back should be implemented until separate approval exists.

### Phase 4: App Store / TestFlight

Goals:

- Apple Developer account
- Google Play account
- privacy policy
- app signing
- TestFlight/internal Android testing
- crash reporting decision
- institutional review

### Phase 5: Production Mobile App

Goals:

- production authentication
- multi-user permissions
- secure token storage
- offline draft queue
- audit trail
- notifications/reminders
- OneNote sync status
- optional approved write-back workflow
- long-term maintenance plan

## Recommendation

Use PWA and lab-server access first. Build a Flutter prototype only after ResearchOS has stable authentication, API versioning, HTTPS deployment, user accounts, and clearer UCSD OneNote approval boundaries.
