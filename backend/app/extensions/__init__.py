"""ResearchOS Extension SDK."""

from app.extensions.builtins import create_default_extension_manager
from app.extensions.models import Extension, ExtensionManifest
from app.extensions.registry import ExtensionManager, ExtensionRegistry

__all__ = [
    "Extension",
    "ExtensionManager",
    "ExtensionManifest",
    "ExtensionRegistry",
    "create_default_extension_manager",
]
