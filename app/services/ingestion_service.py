import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.edi_parser import edi_parser, EdiParseResult
from app.adapters.neon_db import db
from app.graph.workflow import remediation_graph

INGEST_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ingest"
ARCHIVE_DIR = INGEST_DIR / "archive"

class IngestionService:
    """
    Ingestion Service for Healthcare EDI 837 Claims and 835 Remittances.
    Supports:
    1. Single file or multi-file uploads via REST API / Front-End UI.
    2. Bulk file drops in data/ingest/ with automatic archiving.
    3. Optional auto-trigger of the LangGraph multi-MCP remediation workflow.
    """

    def __init__(self):
        self.ingest_dir = INGEST_DIR
        self.archive_dir = ARCHIVE_DIR
        self.ingest_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def ingest_content(
        self,
        raw_content: str,
        filename: str = "upload.edi",
        auto_remediate: bool = False
    ) -> Dict[str, Any]:
        result: EdiParseResult = edi_parser.parse(raw_content, filename=filename)

        ingested_claim_ids = []
        ingested_remit_ids = []
        remediated_results = []

        # 1. Save 837 Claims
        for claim in result.claims:
            db.save_claim(claim)
            ingested_claim_ids.append(claim.claim_id)

            if auto_remediate:
                initial_state = {
                    "claim_id": claim.claim_id,
                    "claim": None,
                    "remittance": None,
                    "icd10_validations": None,
                    "cms_coverage": None,
                    "ncci_edit": None,
                    "clinical_evidence": None,
                    "jev_noul": None,
                    "jev_score": None,
                    "modifier_applied": None,
                    "decision": None,
                    "human_approved": None,
                    "appeal_letter": None,
                    "audit_trail": [],
                    "resubmission_ready": False
                }
                final_state = remediation_graph.invoke(initial_state)
                remediated_results.append({
                    "claim_id": claim.claim_id,
                    "decision": final_state.get("decision"),
                    "modifier": final_state.get("modifier_applied")
                })

        # 2. Save 835 Remittances
        for remit in result.remittances:
            db.save_remittance(remit)
            ingested_remit_ids.append(remit.claim_id)

        return {
            "success": len(result.errors) == 0 or len(ingested_claim_ids) > 0 or len(ingested_remit_ids) > 0,
            "filename": filename,
            "format_detected": result.raw_type,
            "claims_ingested": len(ingested_claim_ids),
            "claim_ids": ingested_claim_ids,
            "remittances_ingested": len(ingested_remit_ids),
            "remittance_claim_ids": ingested_remit_ids,
            "remediated": remediated_results,
            "errors": result.errors,
            "timestamp": datetime.utcnow().isoformat()
        }

    def process_bulk_directory(self, auto_remediate: bool = False) -> Dict[str, Any]:
        """Scans data/ingest/ for dropped EDI/JSON files, ingests them, and archives them."""
        self.ingest_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        supported_extensions = {".edi", ".x12", ".txt", ".837", ".835", ".json", ".csv"}
        files_to_process = [
            f for f in self.ingest_dir.iterdir()
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]

        if not files_to_process:
            return {
                "message": "No dropped files found in ingestion directory.",
                "directory": str(self.ingest_dir),
                "processed_count": 0,
                "items": []
            }

        batch_summary = []
        total_claims = 0
        total_remits = 0

        for file_path in files_to_process:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                ingest_res = self.ingest_content(content, filename=file_path.name, auto_remediate=auto_remediate)
                batch_summary.append(ingest_res)
                total_claims += ingest_res["claims_ingested"]
                total_remits += ingest_res["remittances_ingested"]

                # Archive file with timestamp
                ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                dest = self.archive_dir / f"{ts}_{file_path.name}"
                shutil.move(str(file_path), str(dest))
            except Exception as e:
                batch_summary.append({
                    "filename": file_path.name,
                    "success": False,
                    "error": str(e)
                })

        return {
            "message": f"Successfully processed {len(files_to_process)} dropped files.",
            "processed_count": len(files_to_process),
            "total_claims_ingested": total_claims,
            "total_remittances_ingested": total_remits,
            "items": batch_summary,
            "metrics": db.get_metrics()
        }

    # Alias for flexibility
    ingest_bulk_directory = process_bulk_directory

    def get_ingest_status(self) -> Dict[str, Any]:
        pending_files = [
            f.name for f in self.ingest_dir.iterdir()
            if f.is_file() and f.suffix.lower() in {".edi", ".x12", ".txt", ".837", ".835", ".json", ".csv"}
        ]
        archived_count = len([f for f in self.archive_dir.iterdir() if f.is_file()])
        metrics = db.get_metrics()

        return {
            "ingest_directory": str(self.ingest_dir),
            "pending_drop_files_count": len(pending_files),
            "pending_files": pending_files,
            "archived_files_count": archived_count,
            "database_total_claims": metrics.get("total_claims", 0),
            "database_auto_remediated": metrics.get("auto_remediated_count", 0)
        }

ingestion_service = IngestionService()
