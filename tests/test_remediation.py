from app.adapters.neon_db import db
from app.graph.workflow import remediation_graph
from app.models import Claim837, JevScore

def test_workflow_execution():
    print("🧪 Running remediation graph on CLM-2026-901 (E/M + Biopsy)...")
    initial_state = {
        "claim_id": "CLM-2026-901",
        "claim": None,
        "remittance": None,
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
    print("Result decision:", final_state.get("decision"))
    print("Modifier applied:", final_state.get("modifier_applied"))
    print("Audit trail steps:", len(final_state.get("audit_trail", [])))

    assert final_state["decision"] == "AUTO_REMEDIATED"
    assert final_state["modifier_applied"] == "25"
    assert final_state["resubmission_ready"] is True

def test_indicator_zero_writeoff():
    print("🧪 Running remediation graph on CLM-2026-903 (Knee Arthroscopy Indicator 0)...")
    initial_state = {
        "claim_id": "CLM-2026-903",
        "claim": None,
        "remittance": None,
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
    print("Result decision:", final_state.get("decision"))
    assert final_state["decision"] == "WRITTEN_OFF"

def test_hitl_interrupt():
    print("🧪 Running remediation graph on CLM-2026-904 (Ambiguous chart note -> HITL)...")
    initial_state = {
        "claim_id": "CLM-2026-904",
        "claim": None,
        "remittance": None,
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
    print("Result decision:", final_state.get("decision"))
    assert final_state["decision"] == "HITL_REVIEW"

if __name__ == "__main__":
    test_workflow_execution()
    test_indicator_zero_writeoff()
    test_hitl_interrupt()
    print("✅ All workflow tests passed successfully!")
