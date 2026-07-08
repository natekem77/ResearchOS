"""Core models for the ResearchOS Extension SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ExtensionCapability = Literal[
    "provider",
    "agent",
    "command",
    "page",
    "importer",
    "exporter",
    "background_job",
    "widget",
]


@dataclass(frozen=True)
class ExtensionManifest:
    """Declarative metadata required for every ResearchOS extension."""

    extension_id: str
    name: str
    version: str
    author: str
    dependencies: list[str] = field(default_factory=list)
    capabilities: list[ExtensionCapability] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe manifest data."""

        return {
            "extension_id": self.extension_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "dependencies": list(self.dependencies),
            "capabilities": list(self.capabilities),
            "required_permissions": list(self.required_permissions),
            "description": self.description,
        }


@dataclass
class Extension:
    """Installed ResearchOS extension and its registered contributions."""

    manifest: ExtensionManifest
    enabled: bool = True
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)
    commands: dict[str, dict[str, Any]] = field(default_factory=dict)
    pages: dict[str, dict[str, Any]] = field(default_factory=dict)
    importers: dict[str, dict[str, Any]] = field(default_factory=dict)
    exporters: dict[str, dict[str, Any]] = field(default_factory=dict)
    background_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    widgets: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def extension_id(self) -> str:
        """Return stable extension ID."""

        return self.manifest.extension_id

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe extension data for APIs and UI."""

        return {
            **self.manifest.as_dict(),
            "enabled": self.enabled,
            "contributions": {
                "providers": list(self.providers.values()),
                "agents": list(self.agents.values()),
                "commands": list(self.commands.values()),
                "pages": list(self.pages.values()),
                "importers": list(self.importers.values()),
                "exporters": list(self.exporters.values()),
                "background_jobs": list(self.background_jobs.values()),
                "widgets": list(self.widgets.values()),
            },
        }
