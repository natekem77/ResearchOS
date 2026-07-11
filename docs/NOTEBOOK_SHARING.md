# Notebook Sharing

ResearchOS notebooks are private by default. A researcher should only see their own notebooks unless the owner, a group grant, a role grant, or a lab-level permission allows access.

## Notebook Visibility

Each notebook stores:

- `notebook_id`
- `lab_id`
- `owner_user_id`
- `title`
- `visibility`: `private`, `shared`, `project`, or `lab`
- `created_at`
- `updated_at`

`private` is the default. The backend never returns unauthorized notebook metadata.

## Sharing Grants

Notebook sharing is represented by `NotebookPermission`:

- `permission_id`
- `notebook_id`
- `principal_type`: `user`, `group`, or `role`
- `principal_id`
- `access_level`: `view`, `comment`, `edit`, or `manage`
- `granted_by`
- `granted_at`
- `expires_at`

Access levels are ordered:

`view < comment < edit < manage`

## API

Useful endpoints:

```bash
curl -H "X-ResearchOS-User: user:researcher-a" http://127.0.0.1:8001/notebooks
curl -H "X-ResearchOS-User: user:researcher-a" http://127.0.0.1:8001/notebooks/notebook:researcher-a
curl -H "X-ResearchOS-User: user:researcher-a" http://127.0.0.1:8001/notebooks/notebook:researcher-a/permissions
```

Share a notebook:

```bash
curl -X POST http://127.0.0.1:8001/notebooks/notebook:researcher-a/share \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:researcher-a" \
  -d '{"principal_type":"user","principal_id":"user:researcher-b","access_level":"view"}'
```

Create a group and add a member:

```bash
curl -X POST http://127.0.0.1:8001/groups \
  -H "Content-Type: application/json" \
  -H "X-ResearchOS-User: user:pi-owner" \
  -d '{"lab_id":"lab:demo","name":"Project Team"}'
```

## Notebook Entries

Notebook-entry access inherits notebook authorization. Direct notebook-entry requests must pass through the same `AuthorizationService` checks as notebook routes.

Future notebook entry states are planned:

- `draft`
- `finalized`
- `amended`

Digital signatures and immutable amendment trails are intentionally not implemented yet.

## Audit Logging

ResearchOS records security-relevant notebook actions, including sharing, permission changes, revocations, and elevated access.

