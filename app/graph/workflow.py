from datetime import datetime
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from app.graph.state import RemediationState
from app.adapters.neon_db import db
from app.adapters.fhir_mcp import fhir_adapter
from app.adapters.icd10_mcp import icd10_adapter
from app.adapters.cms_coverage_mcp import cms_coverage_adapter
from app.adapters.jev_ai import jev_engine
from app.adapters.gemini_llm import gemini_adapter
from app.models import (
    Claim837, Remittance835, NcciPtpEdit, ClinicalEvidence,
    JevNoul, JevScore, AdjudicationOutcome, RemediationAudit
)

def node_icd10_validation(state: RemediationState) -> Dict[str, Any]:
    claim_id = state["claim_id"]
    claim = db.get_claim(claim_id)
    audit = list(state.get("audit_trail", []))

    if not claim:
        audit.append({
            "claim_id": claim_id,
            "step_name": "ICD-10 Code Validation (icd10-codes MCP)",
            "timestamp": datetime.utcnow().isoformat(),
            "detail": f"Claim {claim_id} not found in database.",
            "status": "FAILED"
        })
        return {"audit_trail": audit, "decision": "FAILED"}

    validations = icd10_adapter.validate_claim_diagnoses(claim.diagnosis_codes)
    all_valid = all(v.valid and v.specificity_valid for v in validations)

    summary_str = ", ".join([f"{v.code} ({'Valid' if v.valid else 'Invalid'})" for v in validations])
    audit.append({
        "claim_id": claim_id,
        "step_name": "ICD-10 Code Validation (icd10-codes MCP)",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": f"Validated {len(validations)} diagnosis codes via icd10-codes MCP: {summary_str}. All billable: {all_valid}.",
        "status": "COMPLETED" if all_valid else "WARNING"
    })

    return {
        "claim": claim.model_dump(),
        "icd10_validations": [v.model_dump() for v in validations],
        "audit_trail": audit
    }

def node_cms_coverage_lookup(state: RemediationState) -> Dict[str, Any]:
    claim_dict = state["claim"]
    claim_id = state["claim_id"]
    audit = list(state.get("audit_trail", []))

    cpt_codes = [item["cpt_code"] for item in claim_dict.get("line_items", [])]
    dx_codes = claim_dict.get("diagnosis_codes", [])

    coverage_result = cms_coverage_adapter.evaluate_claim_coverage(cpt_codes, dx_codes)
    policies = coverage_result.get("policies", [])

    policy_titles = [f"{p.get('policy_id')}: {p.get('title')}" for p in policies]
    detail_msg = (
        f"Matched {len(policies)} Medicare Part B Coverage Policies via cms-coverage MCP: {'; '.join(policy_titles)}."
        if policies else "No specific restrictive NCD/LCD found; standard Part B coverage applies."
    )

    audit.append({
        "claim_id": claim_id,
        "step_name": "CMS Coverage & Medical Necessity (cms-coverage MCP)",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": detail_msg,
        "status": "COMPLETED"
    })

    return {
        "cms_coverage": coverage_result,
        "audit_trail": audit
    }

def node_ncci_table_inspection(state: RemediationState) -> Dict[str, Any]:
    claim_id = state["claim_id"]
    claim = Claim837(**state["claim"])
    remit = db.get_remittance(claim_id)
    audit = list(state.get("audit_trail", []))

    cpt_codes = [item.cpt_code for item in claim.line_items]
    col1 = cpt_codes[0] if len(cpt_codes) > 0 else ""
    col2 = cpt_codes[1] if len(cpt_codes) > 1 else ""

    ncci_edit = db.get_ncci_edit(col1, col2) if (col1 and col2) else None
    indicator = ncci_edit.indicator if ncci_edit else 9

    detail = (
        f"NCCI PTP lookup for CPT pair ({col1}, {col2}): Found Indicator {indicator}. "
        f"Rationale: {ncci_edit.rationale if ncci_edit else 'No edit found / not applicable'}."
    )

    audit.append({
        "claim_id": claim_id,
        "step_name": "NCCI PTP Table Inspection (Neon DB)",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": detail,
        "status": "COMPLETED"
    })

    return {
        "remittance": remit.model_dump() if remit else None,
        "ncci_edit": ncci_edit.model_dump() if ncci_edit else None,
        "audit_trail": audit
    }

def node_clinical_ground_truth_verification(state: RemediationState) -> Dict[str, Any]:
    claim_dict = state["claim"]
    claim_id = state["claim_id"]
    audit = list(state.get("audit_trail", []))

    raw_notes = claim_dict.get("clinical_notes", "")
    patient_id = claim_dict.get("patient_id")
    cpt_codes = [item["cpt_code"] for item in claim_dict.get("line_items", [])]

    # Use local-fhir MCP server to extract chart evidence and verbatim quote
    evidence = fhir_adapter.extract_clinical_evidence(
        claim_id=claim_id,
        raw_notes=raw_notes,
        cpt_codes=cpt_codes,
        patient_id=patient_id
    )

    audit.append({
        "claim_id": claim_id,
        "step_name": "Clinical Ground Truth Extraction (local-fhir MCP)",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": f"Extracted operative evidence via local-fhir MCP. Corroboration score: {evidence.corroboration_score}. Verbatim quote: '{evidence.verbatim_sentence}'",
        "status": "COMPLETED"
    })

    return {
        "clinical_evidence": evidence.model_dump(),
        "audit_trail": audit
    }

def node_jev_ai_gate(state: RemediationState) -> Dict[str, Any]:
    claim = Claim837(**state["claim"])
    remit = Remittance835(**state["remittance"]) if state.get("remittance") else None
    ncci_edit = NcciPtpEdit(**state["ncci_edit"]) if state.get("ncci_edit") else None
    evidence = ClinicalEvidence(**state["clinical_evidence"])
    audit = list(state.get("audit_trail", []))

    icd10_validations = state.get("icd10_validations", [])
    cms_coverage = state.get("cms_coverage")

    # 1. Construct TypeSafe Jev Noul Primitive incorporating multi-MCP evidence
    noul = jev_engine.construct_noul(claim, remit, ncci_edit, evidence, icd10_validations, cms_coverage)

    # 2. Compute TypeSafe Jev Score Primitive
    score = jev_engine.evaluate_score(noul, evidence)

    audit.append({
        "claim_id": claim.claim_id,
        "step_name": "TypeSafe Jev AI Multi-MCP Gate Evaluation",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": (
            f"Jev AI synthesized multi-MCP signals & computed overturn confidence: {score.overturn_confidence:.2f} "
            f"(Threshold: 0.85). Action: {score.action}. "
            f"Recommended modifier: -{score.recommended_modifier or 'None'}."
        ),
        "status": "COMPLETED"
    })

    return {
        "jev_noul": noul.model_dump(),
        "jev_score": score.model_dump(),
        "audit_trail": audit
    }

def route_adjudication(state: RemediationState) -> str:
    score_dict = state.get("jev_score", {})
    action = score_dict.get("action", "HITL_INTERRUPT")

    if action == "CONTRACTUAL_WRITE_OFF":
        return "contractual_write_off"
    elif action == "AUTO_APPEND_MODIFIER":
        return "auto_append_modifier"
    else:
        return "hitl_interrupt"

def node_auto_append_modifier(state: RemediationState) -> Dict[str, Any]:
    claim = Claim837(**state["claim"])
    score = JevScore(**state["jev_score"])
    evidence = ClinicalEvidence(**state["clinical_evidence"])
    audit = list(state.get("audit_trail", []))

    modifier = score.recommended_modifier or "25"

    for idx, item in enumerate(claim.line_items):
        if idx > 0 and modifier not in item.modifiers:
            item.modifiers.append(modifier)
        elif len(claim.line_items) == 1 and modifier not in item.modifiers:
            item.modifiers.append(modifier)

    claim.status = "AUTO_REMEDIATED"
    db.save_claim(claim)

    cpt_pairs = " & ".join([item.cpt_code for item in claim.line_items])
    appeal_letter = gemini_adapter.generate_appeal_letter(
        claim_id=claim.claim_id,
        patient_name=claim.patient_name,
        dos=claim.date_of_service,
        payer_name=claim.payer_name,
        cpt_pairs=cpt_pairs,
        modifier=modifier,
        clinical_evidence=evidence.verbatim_sentence,
        verbatim_quote=evidence.verbatim_sentence,
        carc_code="97"
    )

    audit.append({
        "claim_id": claim.claim_id,
        "step_name": "Autonomous Modifier Appending & EDI 837 Regeneration",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": f"Auto-appended Modifier -{modifier} based on Jev AI confidence {score.overturn_confidence:.2f}. Resubmission package generated.",
        "status": "COMPLETED"
    })

    return {
        "claim": claim.model_dump(),
        "modifier_applied": modifier,
        "decision": "AUTO_REMEDIATED",
        "appeal_letter": appeal_letter,
        "resubmission_ready": True,
        "audit_trail": audit
    }

def node_hitl_interrupt(state: RemediationState) -> Dict[str, Any]:
    claim = Claim837(**state["claim"])
    score = JevScore(**state["jev_score"])
    audit = list(state.get("audit_trail", []))

    claim.status = "HITL_REVIEW"
    db.save_claim(claim)

    audit.append({
        "claim_id": claim.claim_id,
        "step_name": "LangGraph HITL Interrupt Triggered",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": (
            f"Denial Category: {score.remediation_category}. Strategy: {score.remediation_strategy}. "
            f"Flagged for Specialist Review with {len(score.available_actions)} dynamic action pathways."
        ),
        "status": "WAITING_FOR_HUMAN"
    })

    return {
        "claim": claim.model_dump(),
        "decision": "HITL_REVIEW",
        "resubmission_ready": False,
        "audit_trail": audit
    }

def node_contractual_write_off(state: RemediationState) -> Dict[str, Any]:
    claim = Claim837(**state["claim"])
    score = JevScore(**state["jev_score"])
    audit = list(state.get("audit_trail", []))

    claim.status = "WRITTEN_OFF"
    db.save_claim(claim)

    audit.append({
        "claim_id": claim.claim_id,
        "step_name": "Contractual Compliance Write-Off",
        "timestamp": datetime.utcnow().isoformat(),
        "detail": f"Write-off evaluated: {score.reasoning}",
        "status": "COMPLETED"
    })

    return {
        "claim": claim.model_dump(),
        "decision": "WRITTEN_OFF",
        "resubmission_ready": False,
        "audit_trail": audit
    }

def node_audit_persist(state: RemediationState) -> Dict[str, Any]:
    claim = Claim837(**state["claim"])
    score = JevScore(**state["jev_score"])
    evidence = ClinicalEvidence(**state["clinical_evidence"])
    ncci_edit = NcciPtpEdit(**state["ncci_edit"]) if state.get("ncci_edit") else None

    remediated_amount = claim.total_billed if state.get("decision") == "AUTO_REMEDIATED" else 0.0

    outcome = AdjudicationOutcome(
        claim_id=claim.claim_id,
        original_billed=claim.total_billed,
        remediated_amount=remediated_amount,
        decision=state.get("decision", "PENDING"),
        modifier_applied=state.get("modifier_applied"),
        ncci_indicator=ncci_edit.indicator if ncci_edit else 9,
        overturn_confidence=score.overturn_confidence,
        audit_risk=score.audit_risk_score,
        action=score.action,
        reasoning=score.reasoning,
        remediation_category=score.remediation_category,
        remediation_strategy=score.remediation_strategy,
        payer_category=getattr(score, "payer_category", None) or getattr(claim, "payer_name", "COMMERCIAL"),
        payer_guidance=getattr(score, "payer_guidance", None),
        root_cause=getattr(score, "root_cause", None),
        available_actions=score.available_actions,
        verbatim_clinical_evidence=evidence.verbatim_sentence,
        icd10_validations=state.get("icd10_validations", []),
        cms_coverage=state.get("cms_coverage"),
        resubmission_ready=state.get("resubmission_ready", False),
        audit_trail=[RemediationAudit(**a) for a in state.get("audit_trail", [])]
    )

    db.save_adjudication(outcome)
    return {"audit_trail": state.get("audit_trail", [])}

def build_remediation_graph() -> StateGraph:
    builder = StateGraph(RemediationState)

    # Add Nodes for all multi-MCP steps
    builder.add_node("icd10_validation", node_icd10_validation)
    builder.add_node("cms_coverage_lookup", node_cms_coverage_lookup)
    builder.add_node("ncci_inspection", node_ncci_table_inspection)
    builder.add_node("clinical_verification", node_clinical_ground_truth_verification)
    builder.add_node("jev_ai_gate", node_jev_ai_gate)
    builder.add_node("auto_append_modifier", node_auto_append_modifier)
    builder.add_node("hitl_interrupt", node_hitl_interrupt)
    builder.add_node("contractual_write_off", node_contractual_write_off)
    builder.add_node("audit_persist", node_audit_persist)

    # Edge Pipeline
    builder.set_entry_point("icd10_validation")
    builder.add_edge("icd10_validation", "cms_coverage_lookup")
    builder.add_edge("cms_coverage_lookup", "ncci_inspection")
    builder.add_edge("ncci_inspection", "clinical_verification")
    builder.add_edge("clinical_verification", "jev_ai_gate")

    builder.add_conditional_edges(
        "jev_ai_gate",
        route_adjudication,
        {
            "auto_append_modifier": "auto_append_modifier",
            "hitl_interrupt": "hitl_interrupt",
            "contractual_write_off": "contractual_write_off"
        }
    )

    builder.add_edge("auto_append_modifier", "audit_persist")
    builder.add_edge("hitl_interrupt", "audit_persist")
    builder.add_edge("contractual_write_off", "audit_persist")
    builder.add_edge("audit_persist", END)

    return builder.compile()

remediation_graph = build_remediation_graph()
