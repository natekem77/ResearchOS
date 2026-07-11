# Lab Accounts and Roles

ResearchOS now has a backend-enforced foundation for multi-user laboratory access. The goal is to support a PI or lab owner, configurable administrators, supervisors, researchers, and guests without relying on frontend-only visibility rules.

## Core Concepts

- **User**: A person who can access ResearchOS. Development mode uses seeded demo users.
- **Lab**: A laboratory workspace containing members, notebooks, experiments, assets, and future shared resources.
- **LabMembership**: Connects a user to a lab with a lab role.
- **LabRole**: A role label such as `owner`, `admin`, `supervisor`, `researcher`, or `guest`.
- **Permission**: A granular action such as `lab.members.manage` or `lab.notebooks.view_all`.
- **Notebook**: A lab notebook owned by a user and private by default.
- **NotebookPermission**: A sharing grant to a user, group, or role.
- **LabGroup**: A group of lab members used for sharing.
- **AuditEvent**: A security-relevant event recorded by the backend.

## Roles

ResearchOS supports these lab roles:

- `owner`: PI/lab owner. May view all lab notebooks, manage members and sharing, and view audit logs.
- `admin`: Configurable administrator. Does not automatically receive notebook view-all access.
- `supervisor`: Future role for project or trainee oversight.
- `researcher`: Owns and manages personal notebooks and can access explicitly shared notebooks.
- `guest`: Can access only explicitly shared resources.

Role labels are not the complete authorization model. Backend decisions use granular permissions and notebook sharing grants through `AuthorizationService`.

## Current Default Permissions

`owner` receives:

- `lab.members.manage`
- `lab.roles.manage`
- `lab.notebooks.view_all`
- `lab.notebooks.comment_all`
- `lab.notebooks.manage_sharing`
- `lab.audit.view`

`admin` currently receives:

- `lab.members.manage`

This is intentional. Admins can help manage the lab without automatically reading every private notebook.

## Demo Accounts

Development mode seeds:

- `user:pi-owner`
- `user:lab-admin`
- `user:researcher-a`
- `user:researcher-b`
- `user:guest`

Local development may select a demo user with the `X-ResearchOS-User` HTTP header. This is only a development scaffold and must not be used as production authentication.

## Future SSO

Future Microsoft/UCSD login should map Microsoft identity claims to ResearchOS users, then map users to lab memberships. OneNote sync tokens and ResearchOS app login should remain separate concepts unless production security review approves a unified model.

