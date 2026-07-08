# Microsoft Identity Roadmap

ResearchOS currently uses Microsoft authentication only for read-only Microsoft Graph access to OneNote. It does not yet use Microsoft identity as the ResearchOS application login.

## Current State

Current Microsoft auth is delegated Graph consent for OneNote sync:

- `GET /auth/login` starts Microsoft delegated login.
- `GET /auth/callback` receives the authorization code.
- `GET /auth/status` reports Graph token status.
- `POST /sync/onenote` uses the delegated token for read-only OneNote page sync.

This flow exists so ResearchOS can read notebook metadata and page content after the user grants `Notes.Read`.

Local ResearchOS application auth is still demo-friendly:

- `AUTH_MODE=dev`
- `REQUIRE_LOGIN=false`
- `AUTH_ENABLED=false`
- a local development admin user is created automatically

## Future ResearchOS Login With Microsoft Identity

Future lab-server and mobile deployments should use Microsoft Entra ID as the ResearchOS login provider.

The future login flow should:

1. Redirect the user to Microsoft login.
2. Validate Microsoft identity claims server-side.
3. Map the Microsoft user to a ResearchOS user.
4. Map that ResearchOS user to one or more lab workspaces.
5. Enforce permissions by workspace and role.

This app-login flow is related to, but distinct from, OneNote sync authorization.

## UCSD Tenant Approval

For UCSD deployment, ResearchOS will likely need one of these paths:

- UCSD IT approves the ResearchOS Development Azure app for the UCSD tenant.
- UCSD IT registers and owns a UCSD-managed Azure app for ResearchOS.

Read-only MVP permissions should remain minimal:

- `openid`
- `profile`
- `offline_access`
- `User.Read`
- `Notes.Read`

Future OneNote write-back would require separate approval for write/create permissions. It should not be bundled into the read-only MVP.

## Mapping Microsoft User To ResearchOS User

Recommended identity mapping:

```text
Microsoft Entra user
  -> ResearchOS user
  -> workspace membership
  -> workspace role
  -> resource permissions
```

Useful Microsoft claims:

- `oid`: stable Microsoft user object ID
- `tid`: tenant ID
- `preferred_username` or email: ResearchOS user email
- `name`: display name

ResearchOS should store a stable external identity mapping rather than relying only on display name or email.

## Mapping Users To Lab Workspaces

ResearchOS workspaces represent labs, projects, or groups. A user may eventually belong to multiple workspaces.

Current roles:

- `admin`: PI/admin user, workspace and member management
- `researcher`: normal lab member, research object creation/editing
- `viewer`: read-only collaborator/reviewer

Future enforcement should check both:

- user role
- workspace membership

## Token Storage And Security

Current local token storage is development-only and should be treated as temporary.

Before production:

- store tokens per user
- scope tokens per workspace when appropriate
- encrypt refresh tokens at rest
- avoid logging tokens or authorization codes
- rotate credentials when compromised
- support logout/token revocation
- use HTTPS for all non-local deployments
- separate app-login sessions from OneNote Graph tokens

## Mobile And PWA Implications

PWA/mobile access changes redirect and security requirements:

- lab-server deployments need HTTPS
- Microsoft redirect URIs must match the public server URL
- iPhone/Android users need reachable server access through lab network, VPN, Tailscale, or hosted deployment
- browser/PWA sessions need secure cookies or an equivalent session design
- offline use should not assume Microsoft tokens are available

## OneNote Sync Auth vs App Login Auth

These are separate concerns:

| Concern | Purpose | Current Status |
| --- | --- | --- |
| OneNote sync auth | Read OneNote through Microsoft Graph | Scaffolded and read-only |
| ResearchOS app login | Identify who is using ResearchOS | Future roadmap |
| Workspace permissions | Decide what each user can access | Scaffolded, not strict |
| OneNote write-back | Create/write notebook pages | Disabled pending separate approval |

ResearchOS should not assume that a user authorized OneNote sync is automatically allowed to access every workspace. App login and workspace permissions must become the source of truth for ResearchOS access.

## Readiness Endpoint

Check current app-login readiness:

```bash
curl http://127.0.0.1:8001/auth/readiness
```

This endpoint reports:

- auth mode
- whether login is required
- Microsoft client/tenant configuration
- redirect URI
- user/workspace table readiness
- production warnings

It does not expose secrets and does not force login.
