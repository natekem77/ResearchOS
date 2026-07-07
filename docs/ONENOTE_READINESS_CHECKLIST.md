# OneNote Readiness Checklist

ResearchOS OneNote integration is read-only for the MVP. The goal of this
checklist is to confirm that Microsoft Graph delegated login, redirect URIs,
and UCSD approval status are aligned before attempting sync.

## Quick Readiness Check

Start ResearchOS, then run:

```bash
curl http://127.0.0.1:8001/status/onenote-readiness
curl http://127.0.0.1:8001/auth/status
curl -X POST http://127.0.0.1:8001/sync/onenote
```

`/status/onenote-readiness` does not expose secrets or tokens. It reports
whether the Azure app, redirect URI, delegated read-only scopes, current auth
session, and deployment URL look ready.

## Azure App Registration Checklist

In Microsoft Entra ID / Azure Portal:

- Create or use an app registration named `ResearchOS Development`.
- Configure the platform as `Mobile and desktop applications` for local/public
  client delegated auth.
- Enable public client flows.
- Do not create or use a client secret for local ResearchOS development.
- Copy the Application Client ID into `MICROSOFT_CLIENT_ID`.
- Copy the Tenant ID into `MICROSOFT_TENANT_ID`, or use `common` only for early
  prototype testing.
- Add delegated Microsoft Graph permissions for the read-only MVP:
  `User.Read`, `Notes.Read`, `openid`, `profile`, and `offline_access`.
- Do not add write permissions for the MVP.

Future write-back is intentionally separate. Saving generated entries to
OneNote would require separate UCSD IT approval for `Notes.Create` or
`Notes.ReadWrite`.

## Redirect URI Checklist

The redirect URI in Azure must exactly match the callback ResearchOS uses.

Local development default:

```text
http://localhost:8001/auth/callback
```

If running on a lab server with:

```text
PUBLIC_BASE_URL=https://researchos.lab.example.edu
```

Register this Azure redirect URI:

```text
https://researchos.lab.example.edu/auth/callback
```

The readiness endpoint returns both:

- `current_redirect_uri`: the value ResearchOS is using now.
- `required_azure_redirect_uri`: the exact URI Azure should contain for the
  current local/server mode.

## Local Dev Mode

Use local dev mode when ResearchOS is running only on Nathan's machine:

```bash
MICROSOFT_REDIRECT_URI=http://localhost:8001/auth/callback
./scripts/demo.sh
```

Open:

```text
http://127.0.0.1:8001
```

Then check Settings -> OneNote readiness.

## Lab Server Mode

Use lab server mode when phones, tablets, or other lab laptops connect to a
shared workstation or server:

```bash
PUBLIC_BASE_URL=https://researchos.lab.example.edu \
MICROSOFT_REDIRECT_URI=https://researchos.lab.example.edu/auth/callback \
./scripts/run_server.sh --host 0.0.0.0 --port 8001
```

HTTPS is strongly recommended for shared access and Microsoft auth. Azure must
contain the same HTTPS callback URL.

## PWA / Mobile Mode

ResearchOS remains a web app served by the backend. iPhone and Android users
open the lab server URL and add it to the home screen.

For OneNote login from mobile/PWA mode:

- The phone must be able to reach `PUBLIC_BASE_URL`.
- `PUBLIC_BASE_URL` should be HTTPS.
- `MICROSOFT_REDIRECT_URI` must use the same public host and `/auth/callback`.
- The Azure app must contain that exact redirect URI.

## UCSD IT Approval Checklist

For the read-only MVP, request approval for:

- App name: `ResearchOS Development`
- Redirect URI: the exact local or lab-server callback URL
- Delegated permissions: `User.Read`, `Notes.Read`, `openid`, `profile`,
  `offline_access`
- Public client flow enabled
- Read-only OneNote sync only
- Local-first storage
- No hardcoded secrets
- Optional cloud AI only when explicitly configured

Write-back should be described as a future phase requiring a separate approval
request. Do not request `Notes.Create` or `Notes.ReadWrite` for the current MVP.

## Troubleshooting

`AADSTS50011 redirect URI mismatch`:
Azure does not contain the exact `MICROSOFT_REDIRECT_URI`. Copy the
`required_azure_redirect_uri` from `/status/onenote-readiness` into Azure.

`AADSTS7000218 client_secret required`:
The Azure app is configured like a confidential web app. Use a public client
platform, enable public client flows, and do not use a client secret.

`Need Microsoft Graph login` from `/sync/onenote`:
Open `/auth/login`, complete Microsoft login, then retry sync.

Consent blocked by UCSD:
Send `docs/UCSD_IT_APPROVAL_REQUEST.md` to UCSD IT and request delegated
read-only Notes approval.

OneNote sync still fails after login:
Confirm the account has a OneNote license, the notebooks are accessible, and
the app has delegated `Notes.Read` permission.
