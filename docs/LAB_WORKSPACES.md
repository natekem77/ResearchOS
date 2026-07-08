# Lab Workspaces

ResearchOS now has a Lab Workspace foundation for future multi-user lab-server, mobile, PWA, and cloud deployments.

This is metadata scaffolding only. Strict workspace isolation is not enforced yet, and local demo mode remains permissive.

## LabWorkspace Model

Each workspace has:

- `workspace_id`
- `name`
- `institution`
- `description`
- `created_at`
- `owner_user_id`
- `settings`

The default development workspace is:

```text
workspace_id: workspace:demo-lab
name: Demo Lab Workspace
institution: ResearchOS Local Demo
```

## Membership Model

Workspace membership records contain:

- `workspace_id`
- `user_id`
- `role`
- `joined_at`

Current workspace roles reuse the basic ResearchOS roles:

- admin
- researcher
- viewer

## API

List workspaces:

```bash
curl http://127.0.0.1:8001/workspaces
```

Get one workspace:

```bash
curl http://127.0.0.1:8001/workspaces/workspace:demo-lab
```

Bootstrap the default workspace:

```bash
curl -X POST http://127.0.0.1:8001/workspaces/bootstrap-default \
  -H "Content-Type: application/json" \
  -d '{}'
```

The current user response also includes `current_workspace`:

```bash
curl http://127.0.0.1:8001/auth/me
```

## Single-User Mode

In local development and demos:

- auth enforcement is disabled
- ResearchOS creates the local dev admin user
- ResearchOS creates `Demo Lab Workspace`
- the local dev user is attached as workspace admin
- existing local data remains visible

This keeps `demo.sh`, smoke tests, OneNote auth, assistant, Knowledge Graph, and workflows unblocked.

## Lab-Server Mode

In lab-server mode, a shared ResearchOS backend may serve multiple lab members through:

- PWA browser access
- future Flutter app access
- laptops/tablets on the lab network
- VPN/Tailscale or institutional hosting

The workspace model prepares for:

- shared lab identity
- workspace-level settings
- membership roles
- ownership metadata
- future workspace-scoped dashboards and assets

Strict isolation is not enabled yet.

## Future Multi-Lab / Cloud Mode

Future cloud or institution-hosted ResearchOS may support multiple workspaces:

- one workspace per PI lab
- one workspace per project
- one workspace per institution/team
- cross-workspace collaboration
- workspace-specific provider settings
- workspace-specific Microsoft Graph app/tenant settings
- workspace-specific AI/data handling policy

This will require stronger authentication, authorization, auditing, and data isolation.

## UCSD Identity Mapping

Future UCSD/Microsoft identity should map into ResearchOS as:

```text
Microsoft Entra user
  -> ResearchOS user
  -> workspace membership
  -> workspace role
  -> resource permissions
```

Possible mapping fields:

- Microsoft `oid` -> external identity ID
- email / `preferred_username` -> user email
- display name -> user display name
- tenant ID -> auth provider metadata
- PI/lab assignment -> workspace membership
- lab role -> workspace role

OneNote delegated tokens should be tied to a ResearchOS user and workspace context.

## Workspace Metadata on Research Records

ResearchOS now has nullable `workspace_id` metadata where safe:

- documents
- experiments
- pending entries
- assets
- sessions
- workflows

Existing local data remains valid because these fields are nullable. Current workspace counts include records with either the workspace ID or no workspace ID so pre-workspace demo data remains visible.

## Dashboard and Settings

The Settings page shows:

- current workspace
- institution
- membership role

The Daily Dashboard includes workspace information and workspace-level counts in the overview section.

## Current Limitations

- Workspace isolation is not enforced.
- There is no workspace switcher yet.
- There is no membership management UI yet.
- Provider settings are not workspace-specific yet.
- Microsoft Graph tokens are not per-workspace/per-user yet.
- Existing records may have `workspace_id = NULL`.

## Future Work

Before production multi-user deployment:

- enforce workspace-aware queries
- add membership management UI
- add workspace switcher
- add per-workspace provider settings
- add per-workspace audit log
- scope OneNote sync to user/workspace
- scope AI provider configuration to workspace policy
- support PI/admin review workflows
- add database migrations with explicit versioning
