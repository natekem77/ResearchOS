"""Extension registry for ResearchOS SDK contributions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.extensions.models import Extension, ExtensionManifest


@dataclass
class ExtensionRegistry:
    """In-memory registry of installed extensions and contributions."""

    extensions: dict[str, Extension] = field(default_factory=dict)

    def register_extension(self, manifest: ExtensionManifest, enabled: bool = True) -> Extension:
        """Install one extension manifest."""

        if manifest.extension_id in self.extensions:
            raise ValueError(f"Extension already registered: {manifest.extension_id}")
        missing = [dependency for dependency in manifest.dependencies if dependency not in self.extensions]
        if missing:
            raise ValueError(f"Missing extension dependencies for {manifest.extension_id}: {', '.join(missing)}")
        extension = Extension(manifest=manifest, enabled=enabled)
        self.extensions[manifest.extension_id] = extension
        return extension

    def get(self, extension_id: str) -> Extension | None:
        """Return one extension."""

        return self.extensions.get(extension_id)

    def list_extensions(self) -> list[Extension]:
        """Return installed extensions sorted by display name."""

        return sorted(self.extensions.values(), key=lambda extension: extension.manifest.name.lower())

    def enable(self, extension_id: str) -> bool:
        """Enable an installed extension."""

        extension = self.get(extension_id)
        if extension is None:
            return False
        extension.enabled = True
        return True

    def disable(self, extension_id: str) -> bool:
        """Disable an installed extension."""

        extension = self.get(extension_id)
        if extension is None:
            return False
        extension.enabled = False
        return True

    def register_contribution(self, extension_id: str, bucket: str, contribution_id: str, payload: dict[str, Any]) -> None:
        """Register one extension contribution and prevent duplicate IDs."""

        extension = self.extensions.get(extension_id)
        if extension is None:
            raise LookupError(f"Extension not registered: {extension_id}")
        contributions = getattr(extension, bucket)
        if contribution_id in contributions:
            raise ValueError(f"Duplicate {bucket[:-1]} contribution: {contribution_id}")
        contributions[contribution_id] = {"id": contribution_id, **payload}


@dataclass
class ExtensionManager:
    """Public SDK facade used by built-ins and future external extensions."""

    registry: ExtensionRegistry = field(default_factory=ExtensionRegistry)

    def register_extension(self, manifest: ExtensionManifest, enabled: bool = True) -> Extension:
        """Register an extension manifest."""

        return self.registry.register_extension(manifest, enabled=enabled)

    def register_provider(self, extension_id: str, provider_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "providers", provider_id, metadata)

    def register_agent(self, extension_id: str, agent_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "agents", agent_id, metadata)

    def register_command(self, extension_id: str, command_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "commands", command_id, metadata)

    def register_page(self, extension_id: str, page_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "pages", page_id, metadata)

    def register_importer(self, extension_id: str, importer_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "importers", importer_id, metadata)

    def register_exporter(self, extension_id: str, exporter_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "exporters", exporter_id, metadata)

    def register_background_job(self, extension_id: str, job_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "background_jobs", job_id, metadata)

    def register_widget(self, extension_id: str, widget_id: str, **metadata: Any) -> None:
        self.registry.register_contribution(extension_id, "widgets", widget_id, metadata)

    def enable_extension(self, extension_id: str) -> bool:
        return self.registry.enable(extension_id)

    def disable_extension(self, extension_id: str) -> bool:
        return self.registry.disable(extension_id)

    def list_extensions(self) -> list[dict[str, Any]]:
        return [extension.as_dict() for extension in self.registry.list_extensions()]

    def status(self) -> dict[str, Any]:
        extensions = self.list_extensions()
        return {
            "installed_count": len(extensions),
            "enabled_count": sum(1 for extension in extensions if extension["enabled"]),
            "extensions": extensions,
            "marketplace": {
                "status": "placeholder",
                "message": "Future ResearchOS extension marketplace is not implemented yet.",
            },
        }
