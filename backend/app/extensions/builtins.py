"""Built-in ResearchOS extensions that wrap current provider modules."""

from __future__ import annotations

from app.extensions.models import ExtensionManifest
from app.extensions.registry import ExtensionManager


def create_default_extension_manager() -> ExtensionManager:
    """Register built-in extensions without changing existing provider behavior."""

    manager = ExtensionManager()
    _register_onenote(manager)
    _register_markdown(manager)
    _register_graphpad(manager)
    _register_microscopy(manager)
    _register_spreadsheet(manager)
    _register_literature(manager)
    return manager


def _register_onenote(manager: ExtensionManager) -> None:
    manager.register_extension(
        ExtensionManifest(
            extension_id="builtin.onenote",
            name="OneNote Extension",
            version="0.1.0",
            author="ResearchOS",
            capabilities=["provider", "importer", "command", "page"],
            required_permissions=["Microsoft Graph User.Read", "Microsoft Graph Notes.Read"],
            description="Read-only Microsoft Graph OneNote integration scaffold.",
        )
    )
    manager.register_provider("builtin.onenote", "onenote", title="Microsoft OneNote", read_only=True)
    manager.register_importer("builtin.onenote", "sync_onenote_pages", endpoint="/sync/onenote")
    manager.register_command("builtin.onenote", "connect_onenote", endpoint="/auth/login")
    manager.register_page("builtin.onenote", "onenote_settings", route="#/settings")


def _register_markdown(manager: ExtensionManager) -> None:
    manager.register_extension(
        ExtensionManifest(
            extension_id="builtin.markdown",
            name="Markdown Demo Extension",
            version="0.1.0",
            author="ResearchOS",
            capabilities=["provider", "importer"],
            description="Local Markdown folder provider for demos and development.",
        )
    )
    manager.register_provider("builtin.markdown", "markdown", title="Markdown Notes", local_first=True)
    manager.register_importer("builtin.markdown", "ingest_markdown", endpoint="/ingest/markdown")


def _register_graphpad(manager: ExtensionManager) -> None:
    manager.register_extension(
        ExtensionManifest(
            extension_id="builtin.graphpad",
            name="GraphPad Extension",
            version="0.1.0",
            author="ResearchOS",
            capabilities=["provider", "importer", "widget"],
            description="GraphPad/Prism file discovery and CSV statistics extraction.",
        )
    )
    manager.register_provider("builtin.graphpad", "graphpad", title="GraphPad Prism", local_first=True)
    manager.register_importer("builtin.graphpad", "scan_graphpad_folder", endpoint="/providers/graphpad/scan")
    manager.register_widget("builtin.graphpad", "statistics_cards", page="Statistics")


def _register_microscopy(manager: ExtensionManager) -> None:
    manager.register_extension(
        ExtensionManifest(
            extension_id="builtin.microscopy",
            name="Microscopy Extension",
            version="0.1.0",
            author="ResearchOS",
            capabilities=["provider", "importer", "page", "widget"],
            description="Filename-based microscopy/image asset discovery.",
        )
    )
    manager.register_provider("builtin.microscopy", "microscopy", title="Microscopy Images", local_first=True)
    manager.register_importer("builtin.microscopy", "scan_image_folders", endpoint="/providers/images/scan")
    manager.register_page("builtin.microscopy", "images", route="#/images")


def _register_spreadsheet(manager: ExtensionManager) -> None:
    manager.register_extension(
        ExtensionManifest(
            extension_id="builtin.spreadsheets",
            name="Spreadsheet Extension",
            version="0.1.0",
            author="ResearchOS",
            capabilities=["provider", "importer", "widget"],
            description="Generic quantitative spreadsheet provider.",
        )
    )
    manager.register_provider("builtin.spreadsheets", "spreadsheet", title="Spreadsheets", local_first=True)
    manager.register_importer("builtin.spreadsheets", "scan_spreadsheet_folders", endpoint="/providers/spreadsheets/scan")
    manager.register_widget("builtin.spreadsheets", "compact_quantitative_summary", page="Data")


def _register_literature(manager: ExtensionManager) -> None:
    manager.register_extension(
        ExtensionManifest(
            extension_id="builtin.literature",
            name="Literature Extension",
            version="0.1.0",
            author="ResearchOS",
            capabilities=["provider", "importer", "page"],
            description="Local literature and paper ingestion foundation.",
        )
    )
    manager.register_provider("builtin.literature", "literature", title="Literature", local_first=True)
    manager.register_importer("builtin.literature", "ingest_papers", endpoint="/ingest/papers")
    manager.register_page("builtin.literature", "literature", route="#/literature")
