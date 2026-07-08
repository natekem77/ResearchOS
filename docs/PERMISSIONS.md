# Permissions and Lab Roles

ResearchOS now has role-aware permission scaffolding for future multi-user lab deployment.

This milestone does not aggressively enforce permissions across research routes. Local demo mode remains permissive and uses the local development admin user.

## Roles

Current roles:

- `admin`
- `researcher`
- `viewer`

Default behavior:

| Role | Research objects | Users/settings | Notes |
| --- | --- | --- | --- |
| admin | view/edit | admin | can administer everything |
| researcher | view/edit | no admin access | can work with experiments, assets, notebooks, papers, workflows, sessions |
| viewer | view only | no admin access | read-only lab access |

## Permission Helpers

Implemented in `backend/app/permissions.py`:

- `can_view_resource(user, resource)`
- `can_edit_resource(user, resource)`
- `can_admin(user)`

Supported resource types:

- experiments
- assets
- notebooks
- papers
- workflows
- sessions
- users
- settings

Current resource policy:

- `admin`: view/edit/admin everything
- `researcher`: view/edit research objects, no user/admin settings
- `viewer`: read-only access to research objects

## API

Current user:

```bash
curl http://127.0.0.1:8001/auth/me
```

Current permission matrix:

```bash
curl http://127.0.0.1:8001/auth/permissions
```

Users:

```bash
curl http://127.0.0.1:8001/users
curl http://127.0.0.1:8001/users/user:dev-local
```

Admin bootstrap:

```bash
curl -X POST http://127.0.0.1:8001/users/bootstrap-admin \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.edu","display_name":"Admin"}'
```

`/users` and `/users/bootstrap-admin` are admin-only where auth enforcement exists. In local development mode, the dev user is an admin, so demos and smoke tests remain unblocked.

## Ownership Fields

ResearchOS has nullable ownership fields where safe:

- experiments
- pending entries
- assets
- sessions
- workflows

Fields:

- `owner_user_id`
- `created_by`

Existing local data remains valid because these fields are nullable. Current direct user-created resources such as pending drafts, registered assets, sessions, and workflows can record the local dev user.

## Current Enforcement

Current enforcement is intentionally limited:

- admin-only checks are used for `/users`, `/users/{user_id}`, and `/users/bootstrap-admin`
- research routes primarily return or use permission metadata
- demo mode remains permissive
- no existing OneNote, assistant, Knowledge Graph, workflow, or provider route is blocked

This keeps ResearchOS suitable for local demos while preparing for multi-user deployment.

## Settings UI

The Settings page shows:

- current user
- role
- auth mode
- identity provider
- global permissions
- per-resource permission summary

In default local mode, this shows the development admin user.

## Future UCSD / Microsoft Identity Mapping

Future Microsoft/UCSD login should map Microsoft Entra identity to ResearchOS users:

- Microsoft `oid` or stable user ID -> ResearchOS external identity
- email / preferred username -> ResearchOS `email`
- display name -> ResearchOS `display_name`
- tenant and provider -> `auth_provider`
- lab assignment -> role

Recommended future model:

```text
Microsoft/UCSD identity
  -> ResearchOS user
  -> lab workspace membership
  -> role
  -> resource permissions
```

OneNote delegated tokens should be scoped per ResearchOS user.

## Future Lab Workspace Permissions

Future permissions should support:

- lab workspaces
- PI/admin ownership
- project membership
- per-experiment collaboration
- comments and review workflows
- protocol approval
- notebook write-back approval
- audit trails
- invitation/removal flows

Possible future roles:

- PI/admin
- lab manager
- researcher
- student/trainee
- collaborator
- viewer/auditor

For now, ResearchOS keeps the role model intentionally small: admin, researcher, viewer.

## Security Notes

This scaffolding is not a production authorization system yet. Before broad lab-server deployment, ResearchOS still needs:

- request-bound authentication middleware
- secure sessions or API tokens
- encrypted Microsoft token storage
- user-specific OneNote token ownership
- audit logging
- database migrations managed explicitly
- HTTPS-only production access
- CORS policy for mobile/native clients
- backup and account recovery policy
