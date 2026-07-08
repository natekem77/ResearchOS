# Production Safety Checklist

ResearchOS is currently a local-first preview system. This checklist identifies gaps that must be addressed before using ResearchOS as a real shared lab system for unpublished, sensitive, or regulated data.

## Authentication

- Local demo mode must not be used as production auth.
- `REQUIRE_LOGIN=true` should be required before shared deployment.
- Microsoft identity should become the app-login provider for UCSD/lab users.
- ResearchOS roles must be enforced server-side, not only displayed in the UI.
- Session expiration, logout, and token revocation need production behavior.

## HTTPS

- Lab-server, PWA, mobile, and cloud deployment require HTTPS.
- Microsoft redirect URIs must match the deployed public HTTPS URL.
- Plain HTTP should be limited to `localhost` development only.

## Microsoft / UCSD Identity

- UCSD IT should approve the Azure app or register a UCSD-owned app.
- OneNote delegated permissions should stay minimal for the read-only MVP.
- Microsoft user identity must map to a ResearchOS user.
- ResearchOS users must map to lab workspace memberships and roles.
- App login auth must remain separate from OneNote sync authorization.

## Workspace Isolation

- Workspace IDs are currently metadata scaffolding.
- Strict isolation is not enforced yet.
- Production must enforce workspace membership on every read/write endpoint.
- Admin cross-workspace access should be audited.
- Legacy rows with `workspace_id = NULL` need migration/backfill before strict mode.

## Database Backups

- SQLite data must be backed up before real lab use.
- Backups should include documents, experiments, assets, entries, sessions, workflows, users, workspaces, and provider metadata.
- Backup restore should be tested.
- Backups containing unpublished research data must follow lab/institution policy.

## Audit Logs

Production ResearchOS needs audit logs for:

- login/logout
- failed login attempts
- OneNote sync
- data import/export
- draft creation/deletion
- asset registration/linking
- workspace membership changes
- future OneNote write-back
- admin actions

## PHI / PII Handling

ResearchOS should not be used for PHI, human-subject identifiers, patient IDs, or restricted data until:

- data classification is set appropriately
- institutional policy is reviewed
- access control is enforced
- audit logs exist
- backup/security controls are approved

## Unpublished Research Data

Unpublished experiments, protocols, images, statistics, manuscripts, and grant ideas may be sensitive intellectual property.

Before shared deployment:

- define who can view/export data
- define whether cloud AI is allowed
- define retention and deletion policies
- document lab ownership and PI review workflows

## AI Provider Data Exposure

AI providers may receive snippets from notebooks, experiments, papers, images, statistics, and spreadsheets.

Production deployment should clearly state:

- whether AI is disabled, local, or cloud
- what data may be sent to AI providers
- whether prompts/responses are logged by the provider
- which workspaces allow cloud AI
- how users can verify source provenance

For restricted data, prefer local AI or disable AI until approved.

## Local vs Cloud Deployment

Local/demo:

- suitable for synthetic/demo notes
- uses dev user by default
- no production isolation guarantee

Lab server:

- requires HTTPS or VPN/Tailscale
- needs real login
- needs workspace isolation
- needs backups and audit logs

Cloud/institution-hosted:

- needs stronger compliance review
- needs managed identity/secrets
- needs secure storage and monitoring

## OneNote Sync Risks

Read-only OneNote sync risks:

- tenant consent may fail
- OneNote licenses may be missing
- notebook permissions may expose unexpected pages
- local synced content may include sensitive data
- refresh tokens must be secured

Mitigations:

- keep MVP read-only
- use minimal delegated scopes
- document local storage behavior
- require UCSD/lab approval before real notebook sync

## Write-Back Risks

OneNote write-back is disabled by design.

Future write-back risks:

- AI-generated text could be saved as official notebook record
- accidental edits could affect official lab documentation
- write permissions need separate UCSD IT approval
- review-before-save must be mandatory
- write-back actions must be audited

Do not enable OneNote write-back until the safety, permission, and audit model is reviewed.

## Readiness Endpoint

Check current status:

```bash
curl http://127.0.0.1:8001/status/production-readiness
```

This endpoint reports production safety gaps without enforcing restrictions.
