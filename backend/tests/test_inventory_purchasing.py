"""Tests for inventory and purchasing foundation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import main
from app.config import Settings
from app.experiments import Experiment
from app.storage import SQLiteStore


class InventoryPurchasingTests(unittest.TestCase):
    """Inventory and purchasing should support local lab operations."""

    def _settings(self, tmpdir: str) -> Settings:
        return Settings(database_url=f"sqlite:///{Path(tmpdir) / 'researchos.db'}")

    def test_inventory_crud_and_methods_citation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = self._settings(tmpdir)
            store = SQLiteStore(settings=settings)
            resource = store.save_resource(
                resource_type="antibody",
                name="Anti-BRN3B",
                vendor="DemoBio",
                catalog_number="AB-123",
                rrid="RRID:AB_123",
            )
            item = store.save_inventory_item(
                name="Anti-BRN3B",
                category="antibody",
                vendor="DemoBio",
                catalog_number="AB-123",
                lot_number="LOT-85",
                rrid="RRID:AB_123",
                quantity=1,
                reorder_threshold=2,
                linked_resource_id=str(resource["resource_id"]),
            )
            listed = store.list_inventory_items(vendor="DemoBio")
            updated = store.save_inventory_item(
                item_id=str(item["item_id"]),
                name="Anti-BRN3B",
                category="antibody",
                vendor="DemoBio",
                catalog_number="AB-123",
                lot_number="LOT-86",
            )
            deleted = store.delete_inventory_item(str(item["item_id"]))

        self.assertEqual(len(listed), 1)
        self.assertEqual(updated["lot_number"], "LOT-86")
        self.assertTrue(deleted)

    def test_purchase_crud_and_api_csv_import_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                created = main.create_purchase(
                    main.PurchaseRecordRequest(
                        item_name="SAG",
                        vendor="DemoChem",
                        catalog_number="SAG-001",
                        purchase_date="2026-07-08",
                        cost=125.5,
                        quantity=1,
                        grant_or_funding_source="Demo Grant",
                        purchaser="Nathan",
                        oracle_po_number="PO-85",
                        status="ordered",
                    )
                )
                listed = main.purchases(vendor=None, grant_or_funding_source=None, status=None, query=None, workspace_id=None)
                exported = main.export_purchases_csv(workspace_id=None)
                imported = main.import_purchases_csv(
                    main.PurchaseCsvImportRequest(
                        csv_text="PO Number,Supplier,Item,Amount,Grant,Buyer\nPO-86,DemoBio,Anti-SIX6,88.00,Vision Grant,Nathan\n"
                    )
                )
                preview = main.preview_purchases_import(
                    main.PurchaseImportPreviewRequest(
                        csv_text="Item Description,Supplier,Catalog #,Order Date,Total Cost,Qty,Project/Grant,Requester,PO Number,Invoice Number,Status\n"
                        "Anti-BRN3B,DemoBio,AB-123,2026-07-08,99.5,2,Demo Grant,Nathan,PO-87,INV-1,received\n"
                    )
                )
                mapped = main.import_purchases_mapped_csv(
                    main.PurchaseMappedCsvImportRequest(
                        csv_text="Description,Supplier,Part Number,Amount,Project,PO\nAnti-RAX,DemoBio,RAX-1,45.00,Vision Grant,PO-88\n",
                        mapping={
                            "item_name": "Description",
                            "vendor": "Supplier",
                            "catalog_number": "Part Number",
                            "cost": "Amount",
                            "grant_or_funding_source": "Project",
                            "oracle_po_number": "PO",
                        },
                    )
                )
                template = main.create_purchase_import_template(
                    main.PurchaseImportTemplateRequest(
                        name="Demo Lab Template",
                        mapping={"item_name": "Description", "vendor": "Supplier"},
                    )
                )
                templates = main.purchase_import_templates(workspace_id=None)
                detail = main.purchase_detail(created.purchase_id)
            finally:
                main.settings = original_settings

        self.assertEqual(len(listed), 1)
        self.assertIn("SAG", exported.body.decode("utf-8"))
        self.assertEqual(imported["imported_count"], 1)
        self.assertEqual(preview["suggested_mapping"]["item_name"], "Item Description")
        self.assertEqual(preview["suggested_mapping"]["oracle_po_number"], "PO Number")
        self.assertEqual(mapped["imported_count"], 1)
        self.assertEqual(mapped["records"][0]["oracle_po_number"], "PO-88")
        self.assertTrue(any(item.template_id == "default:oracle_purchasing_export" for item in templates))
        self.assertTrue(any(item.template_id == template.template_id for item in templates))
        self.assertEqual(detail.oracle_po_number, "PO-85")

    def test_inventory_api_and_export_methods_citation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                item = main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="Anti-SIX6",
                        category="antibody",
                        vendor="DemoBio",
                        catalog_number="SIX6-001",
                        lot_number="LOT-SIX6",
                        rrid="RRID:AB_SIX6",
                        quantity=2,
                        reorder_threshold=1,
                    )
                )
                listed = main.inventory_items(vendor=None, category=None, storage_location=None, query=None, workspace_id=None)
                citation = main.inventory_methods_citation(item.item_id)
                exported = main.export_inventory_csv(workspace_id=None)
            finally:
                main.settings = original_settings

        self.assertEqual(len(listed), 1)
        self.assertIn("RRID:AB_SIX6", citation["methods_citation"])
        self.assertIn("Anti-SIX6", exported.body.decode("utf-8"))

    def test_methods_reagent_builder_and_experiment_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                store = SQLiteStore(settings=main.settings)
                resource = store.save_resource(
                    resource_type="antibody",
                    name="BRN3B",
                    vendor="DemoBio",
                    catalog_number="BRN3B-1",
                    rrid="RRID:AB_BRN3B",
                    concentration="1:500",
                    units="dilution",
                )
                item = main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="BRN3B antibody",
                        category="antibody",
                        vendor="DemoBio",
                        catalog_number="BRN3B-1",
                        lot_number="LOT-BRN3B",
                        rrid="RRID:AB_BRN3B",
                        linked_resource_id=str(resource["resource_id"]),
                    )
                )
                store.upsert_experiment(
                    Experiment(
                        id="experiment:methods",
                        source_document_id="doc:methods",
                        source_provider="markdown",
                        title="BRN3B staining",
                        experiment_id="NK_METHODS",
                        markers=["BRN3B"],
                    )
                )
                built = main.build_methods_reagents(
                    main.ReagentMethodsRequest(inventory_item_ids=[item.item_id], style="paper")
                )
                reagents = main.experiment_reagents("experiment:methods", workspace_id=None)
                materials = main.experiment_methods_materials("experiment:methods")
            finally:
                main.settings = original_settings

        self.assertIn("BRN3B antibody", built["text"])
        self.assertIn("RRID:AB_BRN3B", built["text"])
        self.assertEqual(len(reagents["inventory_items"]), 1)
        self.assertIn("LOT-BRN3B", materials["text"])
        self.assertEqual(materials["warnings"], [])


if __name__ == "__main__":
    unittest.main()
