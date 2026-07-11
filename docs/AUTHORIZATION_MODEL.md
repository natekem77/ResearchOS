# Authorization Model

ResearchOS uses a centralized `AuthorizationService` for backend-enforced access control. Frontend visibility is treated only as presentation. The backend decides whether a user can access a resource.

## Design Principles

- Never trust role, ownership, or lab information supplied by the client.
- Never return unauthorized notebook metadata.
- Keep role labels separate from granular permissions.
- Keep private notebooks private by default.
- Allow explicit user, group, and role-based notebook sharing.
- Record security-sensitive activity in audit logs.
- Keep development-mode authentication clearly separate from production identity.

## Central Check

Route handlers call:

```python
can_user(user_id, action, resource_type, resource_id)
```

For notebooks, the service evaluates:

1. Does the notebook exist?
2. Is the user the notebook owner?
3. Does the user have a lab-level permission such as `lab.notebooks.view_all`?
4. Is the notebook lab-visible?
5. Does a user, group, or role sharing grant provide sufficient access?

If none of those checks pass, access is denied.

## Granular Permissions

Initial permissions include:

- `lab.members.manage`
- `lab.roles.manage`
- `lab.notebooks.view_all`
- `lab.notebooks.comment_all`
- `lab.notebooks.manage_sharing`
- `lab.audit.view`

New permissions should be added as action strings, not by hardcoding every rule to a role.

## Access Levels

Notebook access levels are hierarchical:

```text
view < comment < edit < manage
```

A `manage` grant includes lower-level access. A `view` grant does not allow edit or sharing changes.

## Audit Events

The backend records:

- notebook sharing
- permission changes
- permission revocation
- elevated notebook viewing
- group creation
- group membership changes

Audit events include actor, action, resource, lab, timestamp, and metadata.

## Development Mode

The current development scaffold uses seeded demo users and allows `X-ResearchOS-User` to simulate user context. This is not production authentication and should be disabled before lab-server deployment.

Production authentication should use Microsoft/UCSD identity or another reviewed SSO mechanism. ResearchOS must not store plaintext passwords.

## Future Work

Planned hardening includes:

- production login enforcement
- secure session tokens
- full workspace isolation
- supervisor/project assignment rules
- immutable audit retention
- notebook finalization and amendment workflows
- Microsoft identity to ResearchOS user mapping

