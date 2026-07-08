"""Role-aware permission scaffolding for ResearchOS.

This module intentionally provides coarse, deterministic checks without broad
enforcement. It prepares ResearchOS for future lab workspaces, ownership, and
Microsoft/UCSD identity mapping while preserving local demo mode.
"""

from __future__ import annotations

from typing import Any, Literal

from app.users import permissions_for_role

ResourceType = Literal[
    "experiments",
    "assets",
    "notebooks",
    "papers",
    "workflows",
    "sessions",
    "users",
    "settings",
]

RESOURCE_TYPES: list[ResourceType] = [
    "experiments",
    "assets",
    "notebooks",
    "papers",
    "workflows",
    "sessions",
    "users",
    "settings",
]

RESEARCH_RESOURCE_TYPES = {"experiments", "assets", "notebooks", "papers", "workflows", "sessions"}
ADMIN_RESOURCE_TYPES = {"users", "settings"}


def can_admin(user: dict[str, Any]) -> bool:
    """Return whether the user has admin privileges."""

    role = str(user.get("role") or "viewer")
    return bool(permissions_for_role(role).get("can_admin"))


def can_view_resource(user: dict[str, Any], resource: str | dict[str, Any]) -> bool:
    """Return whether a user can view a resource type or resource object."""

    role = str(user.get("role") or "viewer")
    resource_type = _resource_type(resource)
    if role == "admin":
        return True
    if role in {"researcher", "viewer"}:
        return resource_type in RESEARCH_RESOURCE_TYPES
    return False


def can_edit_resource(user: dict[str, Any], resource: str | dict[str, Any]) -> bool:
    """Return whether a user can edit a resource type or resource object."""

    role = str(user.get("role") or "viewer")
    resource_type = _resource_type(resource)
    if role == "admin":
        return True
    if role == "researcher":
        return resource_type in RESEARCH_RESOURCE_TYPES
    return False


def resource_permissions(user: dict[str, Any]) -> dict[str, dict[str, bool]]:
    """Return a per-resource permission matrix."""

    return {
        resource_type: {
            "can_view": can_view_resource(user, resource_type),
            "can_edit": can_edit_resource(user, resource_type),
            "can_admin": can_admin(user) if resource_type in ADMIN_RESOURCE_TYPES else False,
        }
        for resource_type in RESOURCE_TYPES
    }


def permission_summary(user: dict[str, Any]) -> dict[str, Any]:
    """Return user-facing permission metadata."""

    role = str(user.get("role") or "viewer")
    return {
        "role": role,
        "global_permissions": permissions_for_role(role),
        "resource_permissions": resource_permissions(user),
        "resource_types": list(RESOURCE_TYPES),
        "enforcement": {
            "mode": "scaffold",
            "admin_enforced_for": ["users", "settings"],
            "research_resources": sorted(RESEARCH_RESOURCE_TYPES),
            "note": "Most research routes currently return permission metadata but are not strictly enforced.",
        },
    }


def attach_permission_metadata(record: dict[str, Any], user: dict[str, Any], resource_type: ResourceType) -> dict[str, Any]:
    """Attach permission metadata to an API record without enforcing access."""

    return {
        **record,
        "owner_user_id": record.get("owner_user_id") or record.get("created_by"),
        "created_by": record.get("created_by") or record.get("owner_user_id"),
        "permissions": {
            "can_view": can_view_resource(user, resource_type),
            "can_edit": can_edit_resource(user, resource_type),
            "can_admin": can_admin(user),
        },
    }


def _resource_type(resource: str | dict[str, Any]) -> str:
    if isinstance(resource, str):
        return resource
    return str(resource.get("resource_type") or resource.get("type") or resource.get("asset_type") or "")

