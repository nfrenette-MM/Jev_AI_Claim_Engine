from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime

class ClaimLineItem(BaseModel):
    line_number: int
    cpt_code: str
    description: str
    modifiers: List[str] = Field(default_factory=list)
    units: int = 1
    billed_amount: float
    place_of_service: str = "11"  # 11 = Office, 22 = Outpatient Hospital, etc.
    rendering_npi: Optional[str] = None
    diagnosis_pointers: List[str] = Field(default_factory=lambda: ["1"])

class Claim837(BaseModel):
    claim_id: str
    patient_id: str
    patient_name: str
    dob: str
    payer_id: str
    payer_name: str
    date_of_service: str
    rendering_npi: str
    billing_npi: str
    diagnosis_codes: List[str] = Field(default_factory=list)  # ICD-10 codes
    line_items: List[ClaimLineItem] = Field(default_factory=list)
    total_billed: float
    clinical_notes: str = ""
    status: Literal["PENDING", "AUTO_REMEDIATED", "HITL_REVIEW", "WRITTEN_OFF", "DENIED", "RESOLVED"] = "PENDING"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class LineAdjudication(BaseModel):
    line_number: int
    cpt_code: str
    billed_amount: float
    allowed_amount: float
    paid_amount: float
    carc_codes: List[str] = Field(default_factory=list)  # e.g., ["97"]
    rarc_codes: List[str] = Field(default_factory=list)  # e.g., ["N390"]
    denial_reason: str = ""

class Remittance835(BaseModel):
    claim_id: str
    remittance_id: str
    check_number: str
    adjudication_date: str
    total_billed: float
    total_paid: float
    patient_responsibility: float
    line_adjudications: List[LineAdjudication] = Field(default_factory=list)
    primary_carc: str = "97"
    primary_reason: str = "Service included in the payment/allowance for another service (NCCI Bundling)"

class NcciPtpEdit(BaseModel):
    column1_cpt: str
    column2_cpt: str
    indicator: int  # 0 = Barred under all circumstances (Write-off), 1 = Permissible with modifier, 9 = Not applicable
    effective_date: str = "2024-01-01"
    rationale: str
    allowed_modifiers: List[str] = Field(default_factory=lambda: ["25", "59", "XS", "XE", "XP", "XU"])

class Icd10Validation(BaseModel):
    code: str
    valid: bool
    billable: bool
    short_description: str
    long_description: str
    chapter: str
    category: str
    specificity_valid: bool = True
    carc_16_risk: bool = False
    guidance: str = ""

class CmsPolicyMatch(BaseModel):
    policy_id: str
    document_type: str
    title: str
    is_covered: bool
    guidance: str

class ClinicalEvidence(BaseModel):
    claim_id: str
    has_clinical_documentation: bool = True
    document_type: str = "EHR Operative / Progress Note via local-fhir MCP"
    operative_notes: str = ""
    verbatim_sentence: str = ""
    anatomical_distinction_identified: bool = False
    distinct_session_identified: bool = False
    separate_em_identified: bool = False
    corroboration_score: float = 0.0

class JevNoul(BaseModel):
    """
    TypeSafe Jev AI Noul Primitive:
    Represents the structured hypothesis and semantic representation node of a claim,
    incorporating ICD-10 diagnosis validity, CMS coverage determinations, NCCI edits, and FHIR evidence.
    """
    claim_id: str
    ncci_edit_detected: bool
    column1_cpt: str
    column2_cpt: str
    ncci_indicator: int
    candidate_modifiers: List[str]
    clinical_substantiation: str
    carc_code: str
    rarc_code: Optional[str] = None
    payer_tier: str = "COMMERCIAL"
    payer_category: str = "COMMERCIAL"
    icd10_valid: bool = True
    cms_policy_substantiated: bool = True
    cms_policy_title: Optional[str] = None

class JevScore(BaseModel):
    """
    TypeSafe Jev AI Score Primitive:
    Represents the quantified confidence, risk, and adjudication action.
    """
    overturn_confidence: float = Field(..., ge=0.0, le=1.0)
    audit_risk_score: float = Field(..., ge=0.0, le=1.0)
    recommended_modifier: Optional[str] = None
    action: str = "HITL_INTERRUPT"
    reasoning: str
    remediation_category: str = "NCCI_BUNDLING"
    remediation_strategy: str = ""
    payer_guidance: Optional[str] = None
    root_cause: Optional[str] = None
    available_actions: List[Dict[str, Any]] = Field(default_factory=list)
    clinical_proof_quote: Optional[str] = None
    mcp_verification_summary: Optional[str] = None
    evaluated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

class RemediationAudit(BaseModel):
    claim_id: str
    step_name: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    detail: str
    status: str

class AdjudicationOutcome(BaseModel):
    claim_id: str
    original_billed: float
    remediated_amount: float
    decision: str
    modifier_applied: Optional[str]
    ncci_indicator: int
    overturn_confidence: float
    audit_risk: float
    action: str
    reasoning: str
    remediation_category: str = "NCCI_BUNDLING"
    remediation_strategy: str = ""
    payer_category: Optional[str] = "COMMERCIAL"
    payer_guidance: Optional[str] = None
    root_cause: Optional[str] = None
    available_actions: List[Dict[str, Any]] = Field(default_factory=list)
    verbatim_clinical_evidence: Optional[str] = None
    icd10_validations: List[Dict[str, Any]] = Field(default_factory=list)
    cms_coverage: Optional[Dict[str, Any]] = None
    resubmission_ready: bool
    audit_trail: List[RemediationAudit] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
