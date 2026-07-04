# Azure App Setup for ResearchOS OneNote Access

This guide explains how to register a Microsoft Entra ID app so ResearchOS can
use delegated Microsoft Graph login for read-only OneNote metadata access.

ResearchOS does not need a client secret for the current local delegated login
scaffold. Do not commit secrets, tokens, or real `.env` files.

## 1. Open App Registrations

1. Go to the Azure Portal: `https://portal.azure.com`
2. Open **Microsoft Entra ID**.
3. Select **App registrations**.
4. Select **New registration**.

## 2. Create the Registration

Use these values:

- **Name**: `ResearchOS Local Dev`
- **Supported account types**:
  - **Single tenant**: recommended for a lab, company, university, or other
    organization where everyone signs in with the same Microsoft Entra tenant.
  - **Multitenant**: useful if ResearchOS should support multiple organizations.
  - **Personal Microsoft accounts only**: useful for personal OneNote testing.
  - **Accounts in any organizational directory and personal Microsoft accounts**:
    useful for prototypes, but review this before using it in a lab setting.

For a lab or organization, choose single-tenant unless there is a clear reason
to support external tenants. For a quick prototype, using `common` as the tenant
in `.env` is acceptable.

## 3. Configure Redirect URI

In the registration form, add a redirect URI:

- Platform: **Web** or public-client/native option appropriate for local testing.
- Redirect URI: `http://localhost:8001/auth/callback`

The redirect URI in Azure must exactly match `MICROSOFT_REDIRECT_URI` in `.env`.
If the backend runs on a different port, update both Azure and `.env`.

## 4. Copy IDs

After creating the app registration:

1. Open the app registration overview page.
2. Copy **Application (client) ID** into `MICROSOFT_CLIENT_ID`.
3. Copy **Directory (tenant) ID** into `MICROSOFT_TENANT_ID`.

For prototype login across account types, `MICROSOFT_TENANT_ID=common` can be
used instead of a specific tenant ID.

## 5. Add Microsoft Graph API Permissions

Open **API permissions** for the app registration.

Add delegated Microsoft Graph permissions:

- `User.Read`
- `Notes.Read`

These are read-only delegated permissions. They allow ResearchOS to identify the
signed-in user and read OneNote notebooks, sections, and pages through Microsoft
Graph. Do not add write permissions for the current MVP.

Depending on your tenant settings, an administrator may need to grant consent.

## 6. Update `.env`

From the repository root, copy the example file if needed:

```bash
cp .env.example .env
```

Set the Microsoft Graph values:

```bash
MICROSOFT_CLIENT_ID=<application-client-id>
MICROSOFT_TENANT_ID=<directory-tenant-id-or-common>
MICROSOFT_REDIRECT_URI=http://localhost:8001/auth/callback
GRAPH_SCOPES="User.Read Notes.Read"
```

If you run the API on port `8000`, use:

```bash
MICROSOFT_REDIRECT_URI=http://localhost:8000/auth/callback
```

The redirect URI must match the Azure app registration exactly.

## 7. Run the Backend

From the repository root:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

If the virtual environment does not exist yet:

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

## 8. Test Login and OneNote Listing

Check auth status before login:

```bash
curl http://127.0.0.1:8001/auth/status
```

Open login in a browser:

```text
http://127.0.0.1:8001/auth/login
```

After Microsoft redirects back to ResearchOS, check status again:

```bash
curl http://127.0.0.1:8001/auth/status
```

List notebooks:

```bash
curl http://127.0.0.1:8001/onenote/notebooks
```

List sections and pages:

```bash
curl http://127.0.0.1:8001/onenote/sections
curl http://127.0.0.1:8001/onenote/pages
```

Optional scoped requests:

```bash
curl "http://127.0.0.1:8001/onenote/sections?notebook_id=<notebook-id>"
curl "http://127.0.0.1:8001/onenote/pages?section_id=<section-id>"
```

## 9. Troubleshooting

### Redirect URI mismatch

Symptom: Microsoft login shows an error such as `AADSTS50011`.

Fix: Make sure the Azure redirect URI exactly matches `.env`:

```bash
MICROSOFT_REDIRECT_URI=http://localhost:8001/auth/callback
```

Check protocol, host, port, and path.

### Missing token

Symptom: OneNote endpoints return a message like:

```text
Microsoft Graph is not connected. Visit /auth/login first, then retry.
```

Fix: Open `/auth/login` in a browser and complete Microsoft sign-in. The current
development token cache is in memory, so restarting the backend requires login
again.

### Invalid client ID

Symptom: Microsoft login reports that the application cannot be found.

Fix: Copy **Application (client) ID**, not the object ID, into
`MICROSOFT_CLIENT_ID`.

### Wrong tenant

Symptom: Login works for some accounts but not others, or Microsoft reports that
the user is not in the tenant.

Fix: Use the correct **Directory (tenant) ID** for single-tenant apps. For early
prototype testing, try:

```bash
MICROSOFT_TENANT_ID=common
```

### Missing permissions or consent

Symptom: Graph returns permission or consent errors when listing notebooks.

Fix: Confirm delegated Microsoft Graph permissions include:

- `User.Read`
- `Notes.Read`

Then grant user or admin consent as required by the tenant.

### Empty notebook list

Symptom: `/onenote/notebooks` returns an empty list.

Fix: Confirm the signed-in Microsoft account has OneNote notebooks and that the
account used during login is the same account where those notebooks exist.

### Localhost port mismatch

Symptom: Login succeeds in Azure but the browser cannot return to ResearchOS.

Fix: Start Uvicorn on the same port configured in Azure and `.env`:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```
