# Voice-to-Experiment Entry Design

ResearchOS can prototype a dictation-driven workflow for creating structured lab
notebook entries from spoken experiment details.

## Goal

The initial goal is a reviewable draft, not automatic notebook write-back. A
researcher can dictate experiment details on a laptop or phone, generate a
structured entry, review the result, and later save it to the official notebook
after the required Microsoft permissions are approved.

## Dictation Sources

Supported today:

- iPhone dictation pasted into the ResearchOS text area.
- Laptop operating-system dictation pasted or typed into the browser.
- Manually typed rough notes.

Future browser support:

- Browser speech recognition when available.
- Push-to-talk capture in the New Experiment page.
- Speaker/lab member attribution if needed.

## Draft Generation

The `/entries/draft` endpoint accepts:

```json
{"dictation":"Create NK Expt 31. Day 1 SAG plus GRK inhibitor..."}
```

or:

```json
{"notes":"Create NK Expt 31. Day 1 SAG plus GRK inhibitor..."}
```

The parser extracts:

- Title
- Experiment ID
- Date
- Objective
- Cell line
- Organoid batch
- Conditions
- Treatments
- Concentrations
- Timing / differentiation days
- Controls
- Planned readouts
- Observations
- Next steps

The response includes structured JSON, formatted Markdown, confidence, and
missing fields. Regex/local parsing runs first. If an AI provider is configured,
ResearchOS may use it to improve Markdown formatting without inventing missing
facts.

## Review Before Save

Researchers should always review the generated entry before it becomes part of
the official notebook. The UI intentionally shows a preview panel and a disabled
`Save to OneNote` placeholder.

Recommended workflow:

1. Dictate rough experiment details.
2. Generate a structured entry.
3. Review missing fields and confidence.
4. Edit dictation or regenerate if needed.
5. Save only after OneNote write-back permissions and lab policy are approved.

## OneNote Write-Back Requirements

The current OneNote integration is read-only. Writing generated entries back to
OneNote requires separate UCSD IT approval and broader Microsoft Graph
permissions.

Potential delegated permissions:

- `Notes.Create` for creating new pages.
- `Notes.ReadWrite` for reading and writing notebook content.
- Existing login scopes such as `User.Read`, `openid`, `profile`, and
  `offline_access`.

Because write-back changes the official notebook, it should be gated behind:

- UCSD-owned or UCSD-approved Microsoft Entra app registration.
- Explicit lab approval.
- Clear user confirmation before saving.
- Audit-friendly local logs that do not expose secrets.

## Privacy Model

The prototype is local-first. Dictation is sent only to the local FastAPI backend
unless an AI provider is configured. If cloud AI is enabled, dictated notes may
be sent to that provider for formatting, so users should avoid sensitive or
unapproved data until lab policy is defined.
