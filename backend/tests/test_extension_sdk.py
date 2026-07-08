"""Tests for the ResearchOS Extension SDK."""

from __future__ import annotations

import unittest

from app.extensions import ExtensionManager, ExtensionManifest, create_default_extension_manager


class ExtensionSdkTests(unittest.TestCase):
    """Extension SDK registration should stay deterministic and strict."""

    def test_registration_and_contributions(self) -> None:
        manager = ExtensionManager()
        manager.register_extension(
            ExtensionManifest(
                extension_id="example.pubmed",
                name="PubMed Extension",
                version="0.1.0",
                author="ResearchOS Tests",
                capabilities=["provider", "importer", "page"],
            )
        )
        manager.register_provider("example.pubmed", "pubmed", title="PubMed")
        manager.register_importer("example.pubmed", "import_pubmed", endpoint="/providers/pubmed/import")

        status = manager.status()
        self.assertEqual(status["installed_count"], 1)
        extension = status["extensions"][0]
        self.assertEqual(extension["extension_id"], "example.pubmed")
        self.assertEqual(extension["contributions"]["providers"][0]["id"], "pubmed")
        self.assertEqual(extension["contributions"]["importers"][0]["endpoint"], "/providers/pubmed/import")

    def test_duplicate_extension_detection(self) -> None:
        manager = ExtensionManager()
        manifest = ExtensionManifest(
            extension_id="example.graphpad",
            name="GraphPad Extension",
            version="0.1.0",
            author="ResearchOS Tests",
        )
        manager.register_extension(manifest)
        with self.assertRaises(ValueError):
            manager.register_extension(manifest)

    def test_duplicate_contribution_detection(self) -> None:
        manager = ExtensionManager()
        manager.register_extension(
            ExtensionManifest(
                extension_id="example.microscopy",
                name="Microscopy Extension",
                version="0.1.0",
                author="ResearchOS Tests",
            )
        )
        manager.register_provider("example.microscopy", "images")
        with self.assertRaises(ValueError):
            manager.register_provider("example.microscopy", "images")

    def test_dependency_validation(self) -> None:
        manager = ExtensionManager()
        with self.assertRaises(ValueError):
            manager.register_extension(
                ExtensionManifest(
                    extension_id="example.child",
                    name="Dependent Extension",
                    version="0.1.0",
                    author="ResearchOS Tests",
                    dependencies=["example.parent"],
                )
            )

    def test_enable_disable(self) -> None:
        manager = ExtensionManager()
        manager.register_extension(
            ExtensionManifest(
                extension_id="example.toggle",
                name="Toggle Extension",
                version="0.1.0",
                author="ResearchOS Tests",
            )
        )
        self.assertTrue(manager.disable_extension("example.toggle"))
        self.assertFalse(manager.status()["extensions"][0]["enabled"])
        self.assertTrue(manager.enable_extension("example.toggle"))
        self.assertTrue(manager.status()["extensions"][0]["enabled"])

    def test_default_builtin_extensions_load(self) -> None:
        manager = create_default_extension_manager()
        status = manager.status()
        ids = {extension["extension_id"] for extension in status["extensions"]}
        self.assertIn("builtin.onenote", ids)
        self.assertIn("builtin.graphpad", ids)
        self.assertIn("builtin.microscopy", ids)
        self.assertGreaterEqual(status["enabled_count"], 3)


if __name__ == "__main__":
    unittest.main()
