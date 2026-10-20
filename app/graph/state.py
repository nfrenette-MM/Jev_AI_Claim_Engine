from typing import TypedDict, Optional, List, Dict, Any

class RemediationState(TypedDict):
    claim_id: str
    claim: Optional[Dict[str, Any]]
    remittance: Optional[Dict[str, Any]]
    icd10_validations: Optional[List[Dict[str, Any]]]
    cms_coverage: Optional[Dict[str, Any]]
    ncci_edit: Optional[Dict[str, Any]]
    clinical_evidence: Optional[Dict[str, Any]]
    jev_noul: Optional[Dict[str, Any]]
    jev_score: Optional[Dict[str, Any]]
    modifier_applied: Optional[str]
    decision: Optional[str]  # AUTO_REMEDIATED, HITL_REVIEW, WRITTEN_OFF, DENIED
    human_approved: Optional[bool]
    appeal_letter: Optional[str]
    audit_trail: List[Dict[str, Any]]
    resubmission_ready: bool
