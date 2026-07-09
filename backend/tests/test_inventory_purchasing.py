"""Tests for inventory and purchasing foundation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
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

    def test_inventory_status_and_purchase_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="Low stock SAG",
                        category="compound",
                        quantity=1,
                        reorder_threshold=2,
                        expiration_date=(date.today() + timedelta(days=20)).isoformat(),
                    )
                )
                main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="Expired antibody",
                        category="antibody",
                        quantity=5,
                        reorder_threshold=1,
                        expiration_date=(date.today() - timedelta(days=1)).isoformat(),
                    )
                )
                main.create_purchase(
                    main.PurchaseRecordRequest(
                        item_name="SAG",
                        vendor="DemoChem",
                        cost=100,
                        quantity=2,
                        grant_or_funding_source="Grant A",
                        purchase_date="2026-07-08",
                    )
                )
                main.create_purchase(
                    main.PurchaseRecordRequest(
                        item_name="BRN3B",
                        vendor="DemoBio",
                        cost=50,
                        quantity=1,
                        grant_or_funding_source="Grant B",
                        purchase_date="2026-07-09",
                    )
                )
                status = main.inventory_status(workspace_id=None)
                reorder = main.inventory_reorder_needed(workspace_id=None)
                expiring = main.inventory_expiring(days=30, workspace_id=None)
                summary = main.purchases_summary(workspace_id=None)
                by_grant = main.purchases_by_grant(workspace_id=None)
            finally:
                main.settings = original_settings

        self.assertEqual(status["low_stock_count"], 1)
        self.assertEqual(status["reorder_needed_count"], 1)
        self.assertEqual(status["expired_count"], 1)
        self.assertEqual(status["expiring_windows"]["30_days"], 1)
        self.assertEqual(reorder["count"], 1)
        self.assertEqual(expiring["count"], 2)
        self.assertEqual(summary["total_spend"], 150.0)
        self.assertEqual(summary["spend_by_vendor"][0]["name"], "DemoChem")
        self.assertEqual(by_grant["grants"][0]["name"], "Grant A")

    def test_inventory_usage_tracking_and_methods_prefer_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                store = SQLiteStore(settings=main.settings)
                resource = store.save_resource(resource_type="compound", name="SAG", vendor="DemoChem", catalog_number="SAG-1")
                item = main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="SAG aliquot",
                        category="compound",
                        vendor="DemoChem",
                        catalog_number="SAG-1",
                        quantity=2,
                        linked_resource_id=str(resource["resource_id"]),
                    )
                )
                store.upsert_experiment(
                    Experiment(
                        id="experiment:usage",
                        source_document_id="doc:usage",
                        source_provider="markdown",
                        title="SAG usage experiment",
                        experiment_id="NK_USAGE",
                        compounds=["SAG"],
                    )
                )
                usage = main.record_experiment_inventory_usage(
                    "NK_USAGE",
                    main.InventoryUsageRequest(
                        inventory_item_id=item.item_id,
                        amount_used=0.5,
                        units="vial",
                        purpose="SAG treatment",
                        decrement_quantity=True,
                    ),
                )
                item_usage = main.inventory_item_usage(item.item_id, workspace_id=None)
                experiment_usage = main.experiment_inventory_usage("experiment:usage", workspace_id=None)
                materials = main.experiment_methods_materials("NK_USAGE")
                updated_item = store.get_inventory_item(item.item_id)
                resource_usages = store.resource_usages(str(resource["resource_id"]))
            finally:
                main.settings = original_settings

        self.assertEqual(usage.inventory_item_name, "SAG aliquot")
        self.assertEqual(len(item_usage), 1)
        self.assertEqual(len(experiment_usage), 1)
        self.assertIn("SAG aliquot", materials["text"])
        self.assertEqual(updated_item["quantity"], 1.5)
        self.assertTrue(any(record["usage_type"] == "inventory_used" for record in resource_usages))

    def test_inventory_barcode_lookup_and_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                item = main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="Barcode SAG",
                        category="compound",
                        vendor="DemoChem",
                        catalog_number="SAG-BC",
                        lot_number="LOT-BC",
                        expiration_date="2027-01-01",
                        storage_location="-20C",
                    )
                )
                assigned = main.assign_inventory_code(
                    item.item_id,
                    main.InventoryCodeAssignmentRequest(
                        barcode="BC-SAG-001",
                        qr_code="QR-SAG-001",
                        internal_label="NK-SAG-A1",
                        freezer_box="Box A",
                        freezer_position="A1",
                        shelf="Shelf 2",
                        room="Lab 310",
                    ),
                )
                looked_up = main.inventory_lookup(code="QR-SAG-001", workspace_id=None)
                label = main.inventory_label(item.item_id)
                listed = main.inventory_items(vendor=None, category=None, storage_location=None, query="NK-SAG-A1", workspace_id=None)
            finally:
                main.settings = original_settings

        self.assertEqual(assigned.barcode, "BC-SAG-001")
        self.assertEqual(looked_up.item_id, item.item_id)
        self.assertEqual(label["code_value"], "QR-SAG-001")
        self.assertIn("Box A / A1", label["storage_detail"])
        self.assertEqual(len(listed), 1)

    def test_purchase_request_workflow_and_inventory_reorder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                item = main.create_inventory_item(
                    main.InventoryItemRequest(
                        name="Low stock BMP4",
                        category="growth factor",
                        vendor="DemoBio",
                        catalog_number="BMP4-1",
                        quantity=1,
                        reorder_threshold=2,
                        price=88.0,
                    )
                )
                reorder = main.request_inventory_reorder(item.item_id)
                submitted = main.submit_purchase_request(reorder.request_id)
                approved = main.approve_purchase_request(reorder.request_id)
                ordered = main.mark_purchase_request_ordered(reorder.request_id)
                received = main.mark_purchase_request_received(
                    reorder.request_id,
                    main.PurchaseRequestReceiveRequest(update_inventory_quantity=True),
                )
                created = main.create_purchase_request(
                    main.PurchaseRequestRequest(
                        item_name="New reagent",
                        vendor="DemoChem",
                        quantity_requested=3,
                        estimated_cost=45,
                        status="submitted",
                    )
                )
                listed = main.purchase_requests(status=None, query=None, linked_inventory_item_id=None, workspace_id=None)
                detail = main.purchase_request_detail(created.request_id)
                exported = main.export_purchase_requests_csv(workspace_id=None)
                updated_item = SQLiteStore(settings=main.settings).get_inventory_item(item.item_id)
            finally:
                main.settings = original_settings

        self.assertEqual(reorder.linked_inventory_item_id, item.item_id)
        self.assertEqual(submitted.status, "submitted")
        self.assertEqual(approved.status, "approved")
        self.assertEqual(ordered.status, "ordered")
        self.assertEqual(received.status, "received")
        self.assertEqual(updated_item["quantity"], 3.0)
        self.assertEqual(detail.item_name, "New reagent")
        self.assertEqual(len(listed), 2)
        self.assertIn("Low stock BMP4", exported.body.decode("utf-8"))

    def test_receiving_workflow_and_inventory_intake(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_settings = main.settings
            main.settings = self._settings(tmpdir)
            try:
                request = main.create_purchase_request(
                    main.PurchaseRequestRequest(
                        item_name="Received SAG",
                        vendor="DemoChem",
                        catalog_number="SAG-R",
                        quantity_requested=2,
                        status="ordered",
                    )
                )
                received_request = main.mark_purchase_request_received(
                    request.request_id,
                    main.PurchaseRequestReceiveRequest(create_receiving_record=True),
                )
                receiving_records = main.receiving_records(
                    query=None,
                    purchase_request_id=request.request_id,
                    purchase_record_id=None,
                    inventory_item_id=None,
                    workspace_id=None,
                )
                manual = main.create_receiving_record(
                    main.ReceivingRecordRequest(
                        purchase_request_id=request.request_id,
                        item_name="Manual SAG intake",
                        vendor="DemoChem",
                        catalog_number="SAG-R",
                        lot_number="LOT-RECEIVE",
                        quantity_received=3,
                        units="vial",
                        storage_location="-20C",
                        barcode_or_label="SAG-RECEIVE-A1",
                    )
                )
                intake = main.create_or_update_inventory_from_receiving(
                    manual.receiving_id,
                    main.ReceivingInventoryIntakeRequest(update_existing=True),
                )
                exported = main.export_receiving_csv(workspace_id=None)
                detail = main.receiving_detail(manual.receiving_id)
                inventory = main.inventory_items(vendor=None, category=None, storage_location=None, query="SAG-RECEIVE-A1", workspace_id=None)
            finally:
                main.settings = original_settings

        self.assertEqual(received_request.status, "received")
        self.assertEqual(len(receiving_records), 1)
        self.assertEqual(detail.lot_number, "LOT-RECEIVE")
        self.assertEqual(intake["inventory_item"]["quantity"], 3.0)
        self.assertEqual(len(inventory), 1)
        self.assertIn("Manual SAG intake", exported.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
