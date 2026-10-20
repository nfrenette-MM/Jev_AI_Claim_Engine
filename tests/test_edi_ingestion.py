import os
import shutil
from pathlib import Path

from app.services.edi_parser import edi_parser
from app.services.ingestion_service import ingestion_service
from app.adapters.neon_db import db
from app.adapters.databricks_adapter import DatabricksAdapter
from servers.databricks.server import handle_tool_call

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_edi"
INGEST_DIR = Path(__file__).resolve().parent.parent / "data" / "ingest"

def test_837p_edi_parsing():
    sample_837 = SAMPLE_DIR / "claim_837p_sample.edi"
    assert sample_837.exists(), "Sample 837 file must exist"
    
    with open(sample_837, "r") as f:
        content = f.read()

    result = edi_parser.parse(content, filename=sample_837.name)
    assert result.raw_type == "X12_837"
    assert len(result.claims) == 1

    claim = result.claims[0]
    assert claim.claim_id == "CLM-EDI-1001"
    assert "MARCUS" in claim.patient_name
    assert claim.dob == "1972-06-15"
    assert claim.payer_name == "BCBS OF TEXAS"
    assert len(claim.line_items) == 2
    assert claim.line_items[0].cpt_code == "99214"
    assert claim.line_items[1].cpt_code == "11102"
    assert claim.total_billed == 410.0
    print("✓ 837P EDI parsing verified successfully.")

def test_835_edi_parsing():
    sample_835 = SAMPLE_DIR / "remittance_835_sample.edi"
    assert sample_835.exists(), "Sample 835 file must exist"
    
    with open(sample_835, "r") as f:
        content = f.read()

    result = edi_parser.parse(content, filename=sample_835.name)
    assert result.raw_type == "X12_835"
    assert len(result.remittances) == 1

    remit = result.remittances[0]
    assert remit.claim_id == "CLM-EDI-1001"
    assert remit.check_number == "CHK-9988221"
    assert remit.total_billed == 410.0
    assert remit.total_paid == 140.0
    assert remit.primary_carc == "97"
    assert "bundled" in remit.primary_reason.lower() or "included" in remit.primary_reason.lower()
    print("✓ 835 EDI Remittance parsing verified successfully.")

def test_bulk_directory_ingest_and_archive():
    sample_837 = SAMPLE_DIR / "claim_837p_sample.edi"
    test_target = INGEST_DIR / "test_automated_drop.edi"
    shutil.copy(str(sample_837), str(test_target))

    assert test_target.exists(), "Dropped file must exist in data/ingest/"

    # Check status
    status = ingestion_service.get_ingest_status()
    assert "test_automated_drop.edi" in status["pending_files"]

    # Process bulk drop
    result = ingestion_service.process_bulk_directory(auto_remediate=False)
    assert result["processed_count"] >= 1
    assert not test_target.exists(), "File should be moved out of data/ingest/"

    # Check archive
    archive_dir = INGEST_DIR / "archive"
    archived_files = [f.name for f in archive_dir.iterdir() if "test_automated_drop.edi" in f.name]
    assert len(archived_files) >= 1, "File must be archived with timestamp"
    print("✓ Bulk dropzone processing and archival verified successfully.")

def test_databricks_adapter():
    adapter = DatabricksAdapter()
    
    # 1. Test health check
    health = adapter.test_connection()
    assert health["status"] in ["connected_live", "connected_simulated"]
    assert "claims_837_bronze" in health["tables"][0]

    # 2. List claims
    claims = adapter.list_claims(limit=5)
    assert len(claims) > 0

    # 3. Get claim details
    details = adapter.get_claim_details("CLM-EDI-1001")
    assert details is not None
    assert details["claim"]["claim_id"] == "CLM-EDI-1001"

    # 4. Volume files
    volumes = adapter.list_volume_edi_files()
    assert len(volumes) >= 1

    # 5. Execute SQL
    sql_result = adapter.execute_sql("SELECT * FROM main.claims_rcm.claims_837_bronze LIMIT 5")
    assert sql_result["success"] is True
    assert len(sql_result["rows"]) > 0
    print("✓ DatabricksAdapter operations verified successfully.")

def test_databricks_mcp_server_tools():
    # 1. Health check tool
    health_res = handle_tool_call("databricks_health_check", {})
    assert "status" in health_res

    # 2. List claims tool
    claims_res = handle_tool_call("databricks_list_claims", {"limit": 3})
    assert claims_res["count"] > 0

    # 3. Get claim details tool
    details_res = handle_tool_call("databricks_get_claim_details", {"claim_id": "CLM-EDI-1001"})
    assert details_res["claim"]["claim_id"] == "CLM-EDI-1001"

    # 4. Volume list tool
    vol_res = handle_tool_call("databricks_volume_list_edi", {})
    assert vol_res["total_files"] >= 1

    # 5. Sync tool
    sync_res = handle_tool_call("databricks_sync_remediated_claims", {})
    assert "synced_count" in sync_res
    print("✓ Databricks MCP Server tool handlers verified successfully.")

if __name__ == "__main__":
    test_837p_edi_parsing()
    test_835_edi_parsing()
    test_bulk_directory_ingest_and_archive()
    test_databricks_adapter()
    test_databricks_mcp_server_tools()
    print("\n🎉 ALL EDI INGESTION & DATABRICKS MCP TESTS PASSED!")
