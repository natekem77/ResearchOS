# Authentication and Users

ResearchOS now has a basic user-account foundation for future lab-server, PWA, mobile, and multi-user deployments.

This is scaffolding. It does not yet enforce login across the full application, and it does not change Microsoft Graph/OneNote delegated auth.

## User Model

Each ResearchOS user has:

- `user_id`
- `email`
- `display_name`
- `role`
- `created_at`
- `last_login`
- `auth_provider`

Roles:

- `admin`
- `researcher`
- `viewer`

Permission scaffolding:

- `can_view`
- `can_edit`
- `can_admin`

Current mapping:

| Role | can_view | can_edit | can_admin |
| --- | --- | --- | --- |
| admin | yes | yes | yes |
| researcher | yes | yes | no |
| viewer | yes | no | no |

## Development Mode

Authentication enforcement is disabled by default:

```bash
AUTH_ENABLED=false
RESEARCHOS_AUTH_ENABLED=false
```

When auth is disabled, ResearchOS uses a local development admin user:

```text
user_id: user:dev-local
email: dev@researchos.local
display_name: ResearchOS Dev User
role: admin
auth_provider: local_dev
```

This keeps demos, smoke tests, PWA development, workflows, assistant routes, OneNote auth, and provider scans unblocked.

Customize the dev user:

```bash
RESEARCHOS_DEV_USER_EMAIL=nathan@example.edu
RESEARCHOS_DEV_USER_DISPLAY_NAME="Nathan"
```

## API

Current ResearchOS user:

```bash
curl http://127.0.0.1:8001/auth/me
```

List users:

```bash
curl http://127.0.0.1:8001/users
```

Get a user:

```bash
curl http://127.0.0.1:8001/users/user:dev-local
```

Bootstrap an admin:

```bash
curl -X POST http://127.0.0.1:8001/users/bootstrap-admin \
  -H "Content-Type: application/json" \
  -d '{
    "email": "nathan@example.edu",
    "display_name": "Nathan",
    "auth_provider": "local"
  }'
```

In local development mode, the dev user is an admin, so bootstrap remains available. Once real auth enforcement is introduced, this endpoint should require an admin session or be restricted to a one-time setup flow.

## Microsoft/UCSD Identity Mapping

Microsoft Graph delegated auth currently handles OneNote access only. It is separate from ResearchOS application login.

Future Microsoft/UCSD login should map Microsoft identity claims to ResearchOS users:

- Microsoft object ID or `oid` -> stable external identity
- email or `preferred_username` -> ResearchOS `email`
- display name -> ResearchOS `display_name`
- tenant ID -> `auth_provider` metadata, such as `microsoft_ucsd`
- lab/PI-managed assignment -> ResearchOS `role`

Suggested future mapping:

```text
Microsoft Entra user
  -> ResearchOS user record
  -> role and permissions
  -> per-user OneNote delegated token
```

Do not assume every Microsoft user is an admin. Role assignment should be explicit.

## OneNote Auth Is Separate

Existing OneNote routes remain unchanged:

- `GET /auth/login`
- `GET /auth/callback`
- `GET /auth/status`
- `POST /sync/onenote`

These routes manage Microsoft Graph delegated tokens for read-only OneNote sync. They do not yet create or enforce ResearchOS app sessions.

Future production architecture should connect them carefully:

1. User signs into ResearchOS.
2. User optionally connects Microsoft OneNote.
3. Microsoft token is stored securely for that ResearchOS user.
4. OneNote sync runs only for notebooks the signed-in user can access.

## Backend Work Still Needed

Before real multi-user deployment:

- request-bound authentication middleware
- session or API-token handling
- passwordless/OIDC/SSO login
- encrypted token storage
- per-user Microsoft token records
- role management UI
- audit logs
- ownership and collaboration permissions
- API versioning for mobile clients
- HTTPS-only deployment
- CORS policy for mobile/native clients

## Settings UI

The Settings page shows:

- current user
- email
- role
- auth mode
- identity provider
- permissions

In default demo mode, it should show development mode with admin permissions.

## Security Notes

This foundation is not a production authentication system. It is intentionally permissive in development mode so ResearchOS remains easy to demo and test.

Do not expose a real lab-server deployment broadly until proper ResearchOS authentication, authorization, HTTPS, token encryption, and audit logging are implemented.
