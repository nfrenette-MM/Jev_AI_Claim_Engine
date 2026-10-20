import os
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Body, Query, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.adapters.neon_db import db
from app.graph.workflow import remediation_graph
from app.adapters.icd10_mcp import icd10_adapter
from app.adapters.cms_coverage_mcp import cms_coverage_adapter
from app.adapters.fhir_mcp import fhir_adapter
from app.adapters.databricks_adapter import DatabricksAdapter
from app.services.ingestion_service import ingestion_service
from app.models import (
    Claim837, Remittance835, NcciPtpEdit, AdjudicationOutcome,
    RemediationAudit, ClaimLineItem, LineAdjudication
)
from app.adapters.gemini_llm import gemini_adapter
from app.services.denial_knowledge_base import denial_kb

databricks_adapter = DatabricksAdapter()

app = FastAPI(
    title="JEV AI Claim Engine",
    description="Autonomous RCM Healthcare Claims Prediction & Remediation Platform (Multi-MCP Enabled)",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend template not found")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

@app.get("/api/metrics")
async def get_metrics():
    return db.get_metrics()

@app.get("/api/claims")
async def get_claims():
    claims = db.get_all_claims()
    results = []
    for c in claims:
        remit = db.get_remittance(c.claim_id)
        adj = db.get_adjudication(c.claim_id)
        results.append({
            "claim": c.model_dump(),
            "remittance": remit.model_dump() if remit else None,
            "adjudication": adj.model_dump() if adj else None
        })
    return results

@app.post("/api/claims/clear")
async def clear_claims_queue():
    """Clears all claims, remittances, and adjudications from the queue for fresh live demonstration."""
    res = db.clear_all_claims()
    return {
        "status": "success",
        "message": f"Claim queue cleared. Removed {res['deleted_claims']} claims and {res['deleted_adjudications']} adjudications.",
        "deleted_claims": res["deleted_claims"],
        "deleted_adjudications": res["deleted_adjudications"],
        "metrics": db.get_metrics()
    }

@app.post("/api/claims/reload-demo")
async def reload_demo_claims():
    """Clears the queue and seeds the fresh demo claims in PENDING status for real-time demonstration."""
    from data.seed_data import seed_database
    db.clear_all_claims()
    seed_database()
    claims = db.get_all_claims()
    return {
        "status": "success",
        "message": f"Successfully reloaded {len(claims)} demo claims in PENDING state.",
        "claims_count": len(claims),
        "metrics": db.get_metrics()
    }

@app.post("/api/claims/move-carc45-writeoff")
async def move_carc45_to_written_off():
    """
    Moves all CARC 45 (Contractual Allowance / Fee Schedule) claims to WRITTEN_OFF
    work queue so payment posters can review and bulk adjust them off.
    """
    res = db.move_carc45_to_written_off()
    return {
        "status": "success",
        "message": f"Successfully moved {res['count']} CARC 45 claims (${res['total_dollars']:,.2f}) to Written Off work queue.",
        "count": res["count"],
        "total_dollars": res["total_dollars"],
        "metrics": db.get_metrics()
    }

@app.post("/api/claims/bulk-post-contractual")
async def bulk_post_contractual():
    """
    Executes bulk contractual adjustment posting for all CARC 45 claims in WRITTEN_OFF.
    Records payment poster audit timestamp and confirmation.
    """
    res = db.bulk_post_contractual_adjustments()
    return {
        "status": "success",
        "message": f"Successfully posted contractual adjustments for {res['count']} claims (${res['total_dollars']:,.2f}).",
        "count": res["count"],
        "total_dollars": res["total_dollars"],
        "metrics": db.get_metrics()
    }

@app.get("/api/claims/export-carc45-csv")
async def export_carc45_csv():
    """
    Exports all CARC 45 contractual allowance claims as a clean CSV batch for PM posting.
    """
    import io
    import csv
    from fastapi.responses import Response

    records = db.get_carc45_claims_for_export()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Claim ID", "Date of Service", "Patient Name", "Patient ID",
        "Payer Name", "Payer ID", "CPT Codes", "Total Billed", "Contractual Adjustment",
        "Status", "Primary CARC", "Denial Reason", "Poster Action"
    ])
    for r in records:
        writer.writerow([
            r["claim_id"],
            r["date_of_service"],
            r["patient_name"],
            r["patient_id"],
            r["payer_name"],
            r["payer_id"],
            r["cpt_codes"],
            f"{r['total_billed']:.2f}",
            f"{r['total_billed']:.2f}",
            r["status"],
            r["primary_carc"],
            r["primary_reason"],
            "APPROVED_CONTRACTUAL_WRITE_OFF"
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=CARC45_Contractual_Adjustments_Batch.csv"}
    )

@app.get("/api/claims/{claim_id}")
async def get_claim_detail(claim_id: str):
    claim = db.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    remit = db.get_remittance(claim_id)
    adj = db.get_adjudication(claim_id)

    # Perform real-time MCP validation if not yet adjudicated
    icd10_vals = icd10_adapter.validate_claim_diagnoses(claim.diagnosis_codes)
    cpt_codes = [li.cpt_code for li in claim.line_items]
    cms_cov = cms_coverage_adapter.evaluate_claim_coverage(cpt_codes, claim.diagnosis_codes)
    fhir_patient = fhir_adapter.get_patient(claim.patient_id)

    return {
        "claim": claim.model_dump(),
        "remittance": remit.model_dump() if remit else None,
        "adjudication": adj.model_dump() if adj else None,
        "mcp_data": {
            "icd10_validations": [v.model_dump() for v in icd10_vals],
            "cms_coverage": cms_cov,
            "fhir_patient": fhir_patient
        }
    }

@app.post("/api/remediate/{claim_id}")
async def remediate_claim(claim_id: str):
    claim = db.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    initial_state = {
        "claim_id": claim_id,
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
    outcome = db.get_adjudication(claim_id)
    updated_claim = db.get_claim(claim_id)

    return {
        "status": "success",
        "decision": final_state.get("decision"),
        "modifier_applied": final_state.get("modifier_applied"),
        "appeal_letter": final_state.get("appeal_letter"),
        "audit_trail": final_state.get("audit_trail", []),
        "adjudication": outcome.model_dump() if outcome else None,
        "claim": updated_claim.model_dump() if updated_claim else None,
        "mcp_data": {
            "icd10_validations": final_state.get("icd10_validations", []),
            "cms_coverage": final_state.get("cms_coverage")
        }
    }

@app.post("/api/remediate-all")
async def remediate_all(all_claims: bool = Query(True)):
    claims = db.get_all_claims()
    results = []
    for c in claims:
        if all_claims or c.status == "PENDING":
            initial_state = {
                "claim_id": c.claim_id,
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
            results.append({
                "claim_id": c.claim_id,
                "decision": final_state.get("decision"),
                "modifier": final_state.get("modifier_applied")
            })
    return {"remediated_count": len(results), "items": results, "metrics": db.get_metrics()}

@app.post("/api/human-decision")
async def record_human_decision(payload: Dict[str, Any] = Body(...)):
    claim_id = payload.get("claim_id")
    action = payload.get("action")  # Dynamic actions: APPROVE_MODIFIER, SUBMIT_APPEAL, ATTACH_DOCUMENTATION, RETRO_AUTH, COB_REROUTE, etc.
    params = payload.get("params") or {}
    modifier = payload.get("modifier") or params.get("modifier") or "25"
    notes = payload.get("notes", f"Adjudicated by specialist (Action: {action})")

    claim = db.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    outcome = db.get_adjudication(claim_id)
    audit = outcome.audit_trail if outcome else []

    if action == "APPROVE_MODIFIER":
        for idx, item in enumerate(claim.line_items):
            if idx > 0 and modifier not in item.modifiers:
                item.modifiers.append(modifier)
            elif len(claim.line_items) == 1 and modifier not in item.modifiers:
                item.modifiers.append(modifier)
        claim.status = "AUTO_REMEDIATED"
        decision = "AUTO_REMEDIATED"
        remediated_amt = claim.total_billed
        resubmission = True
        detail_msg = f"Specialist appended Modifier -{modifier}. Corrected EDI 837 claim regenerated."
    elif action in ["SUBMIT_APPEAL", "RESUBMIT_PROOF", "ATTACH_DOCUMENTATION", "RETRO_AUTH", "COB_REROUTE", "UPDATE_DIAGNOSIS"]:
        claim.status = "AUTO_REMEDIATED"
        decision = "AUTO_REMEDIATED"
        remediated_amt = claim.total_billed
        resubmission = True
        detail_msg = f"Specialist executed action '{action}' (Params: {params}). Claim resubmission package prepared."
    elif action in ["POST_ADJUSTMENT", "RECONCILE_DUPLICATE"]:
        claim.status = "AUTO_REMEDIATED"
        decision = "RESOLVED"
        remediated_amt = 0.0
        resubmission = False
        detail_msg = f"Specialist resolved claim via '{action}'. Contractual ledger updated."
    elif action in ["REQUEST_INFO", "PEER_TO_PEER"]:
        claim.status = "HITL_REVIEW"
        decision = "IN_PROGRESS"
        remediated_amt = 0.0
        resubmission = False
        detail_msg = f"Specialist scheduled action '{action}'. Clinical workflow initiated."
    elif action == "WRITE_OFF":
        claim.status = "WRITTEN_OFF"
        decision = "WRITTEN_OFF"
        remediated_amt = 0.0
        resubmission = False
        detail_msg = f"Specialist confirmed contractual write-off of denied balance."
    else:
        claim.status = "DENIED"
        decision = "DENIED"
        remediated_amt = 0.0
        resubmission = False
        detail_msg = f"Specialist recorded action: {action}."

    db.save_claim(claim)

    audit.append(RemediationAudit(
        claim_id=claim_id,
        step_name="Human-In-The-Loop Specialist Decision",
        detail=f"{detail_msg} Notes: {notes}",
        status="RESOLVED"
    ))

    new_outcome = AdjudicationOutcome(
        claim_id=claim.claim_id,
        original_billed=claim.total_billed,
        remediated_amount=remediated_amt,
        decision=decision,
        modifier_applied=modifier if action == "APPROVE_MODIFIER" else (outcome.modifier_applied if outcome else None),
        ncci_indicator=outcome.ncci_indicator if outcome else 1,
        overturn_confidence=1.0 if claim.status == "AUTO_REMEDIATED" else 0.0,
        audit_risk=0.10,
        action=action,
        reasoning=f"Specialist Action: {action}. {notes}",
        remediation_category=outcome.remediation_category if outcome else "NCCI_BUNDLING",
        remediation_strategy=outcome.remediation_strategy if outcome else "",
        payer_category=outcome.payer_category if outcome else "COMMERCIAL",
        payer_guidance=outcome.payer_guidance if outcome else "",
        root_cause=outcome.root_cause if outcome else "",
        available_actions=outcome.available_actions if outcome else [],
        verbatim_clinical_evidence=outcome.verbatim_clinical_evidence if outcome else None,
        icd10_validations=outcome.icd10_validations if outcome else [],
        cms_coverage=outcome.cms_coverage if outcome else None,
        resubmission_ready=resubmission,
        audit_trail=audit
    )
    db.save_adjudication(new_outcome)

    return {"status": "success", "claim": claim.model_dump(), "adjudication": new_outcome.model_dump()}

@app.get("/api/denial-rules")
async def get_all_denial_rules():
    """
    Returns the comprehensive CARC/RARC crosswalk matrix synthesized from
    Microsoft RHAIL, ClaimPilot, AWS Healthcare Agents, and Kustode MCP.
    """
    rules = denial_kb.get_all_rules()
    return {"status": "success", "total_rules": len(rules), "rules": rules}

@app.get("/api/denial-lookup")
async def lookup_denial_guidance(
    payer: str = Query("Commercial", description="Payer name (e.g. Medicare, Aetna, Workers Comp)"),
    carc: str = Query(..., description="CARC code (e.g. 29, 16, 50, 197, 4, 97)"),
    rarc: Optional[str] = Query(None, description="Optional RARC code (e.g. N211, N225, M38, N54)"),
    group_code: Optional[str] = Query("CO", description="Group code (CO, PR, OA, PI)")
):
    """
    Multi-dimensional lookup of payer/plan/carc/rarc to return the tailored root cause,
    clinical evidence requirements, and agent dynamic action pathway.
    """
    rule = denial_kb.search_denial_rules(payer_name=payer, carc=carc, rarc=rarc, group_code=group_code or "CO")
    return {"status": "success", "query": {"payer": payer, "carc": carc, "rarc": rarc, "group_code": group_code}, "rule": rule}

@app.get("/api/ncci-lookup")
async def ncci_lookup(cpt1: str, cpt2: str):
    edit = db.get_ncci_edit(cpt1, cpt2)
    if edit:
        return {
            "found": True,
            "column1_cpt": edit.column1_cpt,
            "column2_cpt": edit.column2_cpt,
            "indicator": edit.indicator,
            "indicator_label": "Indicator 0: Barred Unbundling (Contractual Write-off)" if edit.indicator == 0 else "Indicator 1: Permissible with Modifier (-25, -59, -XS, -XE)",
            "effective_date": edit.effective_date,
            "rationale": edit.rationale,
            "allowed_modifiers": edit.allowed_modifiers
        }
    return {
        "found": False,
        "column1_cpt": cpt1,
        "column2_cpt": cpt2,
        "indicator": 9,
        "indicator_label": "Indicator 9: No Active NCCI Conflict / Not Applicable",
        "effective_date": None,
        "rationale": "No specific CMS procedure-to-procedure conflict exists between these CPT codes.",
        "allowed_modifiers": []
    }

# ==================== Dedicated Anthropic MCP Endpoints ====================

@app.get("/api/mcp/icd10/validate")
async def mcp_validate_icd10(code: str = Query(..., description="ICD-10-CM diagnosis code")):
    """Invokes Anthropic icd10-codes MCP validation tool."""
    result = icd10_adapter.validate_code(code)
    return result.model_dump()

@app.get("/api/mcp/cms/coverage")
async def mcp_search_cms_coverage(cpt: str = Query(..., description="CPT/HCPCS procedure code")):
    """Invokes Anthropic cms-coverage MCP policy search tool."""
    policies = cms_coverage_adapter.search_coverage_by_cpt(cpt)
    return {
        "cpt_code": cpt,
        "count": len(policies),
        "policies": [p.model_dump() for p in policies]
    }

@app.get("/api/mcp/fhir/patient/{patient_id}")
async def mcp_get_fhir_patient(patient_id: str):
    """Invokes local-fhir MCP server to retrieve patient chart, conditions, and notes."""
    patient = fhir_adapter.get_patient(patient_id)
    conditions = fhir_adapter.get_conditions(patient_id)
    notes = fhir_adapter.get_clinical_notes(patient_id)
    return {
        "patient": patient,
        "conditions": conditions,
        "notes": notes
    }

@app.post("/api/claims/create")
async def create_claim(payload: Dict[str, Any] = Body(...)):
    claim_id = payload.get("claim_id", f"CLM-{os.urandom(3).hex().upper()}")
    claim = Claim837(
        claim_id=claim_id,
        patient_id=payload.get("patient_id", "PAT-99001"),
        patient_name=payload.get("patient_name", "Jane Doe"),
        dob=payload.get("dob", "1975-01-01"),
        payer_id=payload.get("payer_id", "PAYER-01"),
        payer_name=payload.get("payer_name", "Medicare Part B"),
        date_of_service=payload.get("date_of_service", "2026-09-01"),
        rendering_npi=payload.get("rendering_npi", "1992019283"),
        billing_npi=payload.get("billing_npi", "1023948512"),
        diagnosis_codes=payload.get("diagnosis_codes", ["I10"]),
        line_items=[ClaimLineItem(**li) for li in payload.get("line_items", [])],
        total_billed=float(payload.get("total_billed", 250.0)),
        clinical_notes=payload.get("clinical_notes", ""),
        status="PENDING"
    )
    db.save_claim(claim)
    db.save_remittance(Remittance835(
        claim_id=claim_id,
        remittance_id=f"REM-{os.urandom(3).hex().upper()}",
        check_number=f"CHK-{os.urandom(4).hex().upper()}",
        adjudication_date="2026-09-10",
        total_billed=claim.total_billed,
        total_paid=0.0,
        patient_responsibility=0.0,
        primary_carc="97",
        primary_reason="CARC 97: Service bundled under NCCI PTP edits",
        line_adjudications=[]
    ))
    return {"status": "success", "claim": claim.model_dump()}

# ==========================================
# EDI 837 / 835 Ingestion Endpoints
# ==========================================

@app.post("/api/ingest/upload")
async def ingest_upload(
    files: List[UploadFile] = File(...),
    auto_remediate: bool = Query(False)
):
    """
    Accepts one-off or batch uploaded 837 Claims or 835 Remittances
    in ANSI ASC X12 (.edi, .x12, .txt) or JSON format.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for ingestion.")

    summary_list = []
    total_claims = 0
    total_remittances = 0

    for file in files:
        try:
            content_bytes = await file.read()
            try:
                raw_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw_text = content_bytes.decode("latin-1")

            ingest_result = ingestion_service.ingest_content(
                raw_content=raw_text,
                filename=file.filename or "upload.edi",
                auto_remediate=auto_remediate
            )
            total_claims += ingest_result.get("claims_ingested", ingest_result.get("claims_ingested_count", 0))
            total_remittances += ingest_result.get("remittances_ingested", ingest_result.get("remittances_ingested_count", 0))
            summary_list.append(ingest_result)
        except Exception as e:
            summary_list.append({
                "filename": file.filename,
                "status": "ERROR",
                "error": str(e)
            })

    return {
        "status": "SUCCESS",
        "files_processed": len(files),
        "total_claims_ingested": total_claims,
        "total_remittances_ingested": total_remittances,
        "results": summary_list,
        "metrics": db.get_metrics()
    }

@app.post("/api/ingest/bulk")
async def ingest_bulk(auto_remediate: bool = Query(False)):
    """
    Scans data/ingest/ for dropped EDI 837/835 files, parses them,
    persists records, archives processed files to data/ingest/archive/,
    and optionally executes autonomous JEV AI remediation.
    """
    result = ingestion_service.ingest_bulk_directory(auto_remediate=auto_remediate)
    return result

@app.get("/api/ingest/status")
async def ingest_status():
    """Returns queue status of data/ingest/ dropzone and archival counts."""
    return ingestion_service.get_ingest_status()

# ==========================================
# Databricks Lakehouse & MCP Endpoints
# ==========================================

@app.get("/api/mcp/databricks/status")
async def databricks_status():
    """Verify connectivity status to Databricks SQL Warehouse and Unity Catalog."""
    return databricks_adapter.test_connection()

@app.post("/api/mcp/databricks/sync")
async def databricks_sync(payload: Dict[str, Any] = Body(default={})):
    """
    Syncs remediated claims and modifier determinations
    into Databricks Gold table `claims_rcm.remediated_claims_gold`.
    """
    claim_id = payload.get("claim_id")
    if claim_id:
        outcome = db.get_adjudication(claim_id)
        if not outcome:
            raise HTTPException(status_code=404, detail=f"No adjudication found for claim {claim_id}")
        return databricks_adapter.sync_remediated_claim(outcome)
    else:
        return databricks_adapter.sync_all_remediated()

@app.get("/api/mcp/databricks/volumes")
async def databricks_volumes(volume_path: Optional[str] = Query(None)):
    """Lists raw EDI files stored in Databricks Volumes or dropzone directory."""
    files = databricks_adapter.list_volume_edi_files(volume_path)
    return {
        "volume_path": volume_path or f"/Volumes/{databricks_adapter.catalog}/{databricks_adapter.schema}/raw_edi/",
        "files_count": len(files),
        "files": files
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

