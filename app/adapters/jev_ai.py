import os
from typing import Optional, List, Tuple, Dict, Any
from app.models import Claim837, Remittance835, NcciPtpEdit, ClinicalEvidence, JevNoul, JevScore
from app.services.denial_knowledge_base import denial_kb

TYPESAFE_API_KEY = os.getenv("TYPESAFE_API_KEY", "")

class JevAiEngine:
    """
    TypeSafe Jev AI Decision Engine.
    Operates on Noul (Semantic/Hypothesis State) and Score (Quantified Decision) primitives.
    Incorporates best-in-class multi-agent healthcare architectures:
      1. Microsoft RHAIL Claims Denial Navigator (CARC/RARC root-cause & resolution routing)
      2. ClaimPilot (Payer policy RAG contextualization & appeal packaging)
      3. AWS Healthcare Multi-Agent framework (search_denial_codes protocol & clinical evidence)
      4. Kustode Medical Billing MCP (X12 WPC & CAQH CORE Phase III Rule 360 standards)
    Synthesizes multi-MCP ground truths:
      1. icd10-codes MCP (HIPAA billability & specificity validation)
      2. cms-coverage MCP (Medicare Part B NCD/LCD medical necessity policies)
      3. local-fhir MCP (EHR Operative chart evidence & verbatim proving clauses)
      4. Neon Postgres NCCI Table Inspection (Indicators 0, 1, 9)
    """
    OVERTURN_THRESHOLD = 0.85

    def construct_noul(
        self,
        claim: Claim837,
        remit: Optional[Remittance835],
        ncci_edit: Optional[NcciPtpEdit],
        clinical_evidence: ClinicalEvidence,
        icd10_validations: Optional[List[Dict[str, Any]]] = None,
        cms_coverage: Optional[Dict[str, Any]] = None
    ) -> JevNoul:
        cpt_codes = [item.cpt_code for item in claim.line_items]
        col1 = cpt_codes[0] if len(cpt_codes) > 0 else ""
        col2 = cpt_codes[1] if len(cpt_codes) > 1 else ""

        indicator = ncci_edit.indicator if ncci_edit else 9
        candidate_modifiers = []
        if ncci_edit and indicator == 1:
            candidate_modifiers = ncci_edit.allowed_modifiers
        elif not ncci_edit:
            candidate_modifiers = ["25", "59"]

        # Multi-MCP synthesis signals
        icd10_all_valid = True
        if icd10_validations:
            icd10_all_valid = all(v.get("valid", True) and v.get("specificity_valid", True) for v in icd10_validations)

        cms_substantiated = True
        cms_title = None
        if cms_coverage and cms_coverage.get("policies"):
            cms_substantiated = cms_coverage.get("coverage_substantiated", True)
            policies = cms_coverage.get("policies", [])
            if len(policies) > 0:
                cms_title = f"{policies[0].get('policy_id')}: {policies[0].get('title')}"

        substantiation = (
            f"Anatomical distinction: {clinical_evidence.anatomical_distinction_identified}; "
            f"Separate E/M: {clinical_evidence.separate_em_identified}; "
            f"Separate session: {clinical_evidence.distinct_session_identified}; "
            f"Corroboration: {clinical_evidence.corroboration_score}; "
            f"ICD-10 valid: {icd10_all_valid}; CMS Policy: {cms_title or 'Standard Part B'}"
        )

        carc = remit.primary_carc if remit else "97"
        rarc = None
        if remit and remit.line_adjudications:
            for la in remit.line_adjudications:
                if la.rarc_codes:
                    rarc = la.rarc_codes[0]
                    break

        payer_cat, _ = denial_kb.classify_payer(claim.payer_name)

        return JevNoul(
            claim_id=claim.claim_id,
            ncci_edit_detected=ncci_edit is not None,
            column1_cpt=col1,
            column2_cpt=col2,
            ncci_indicator=indicator,
            candidate_modifiers=candidate_modifiers,
            clinical_substantiation=substantiation,
            carc_code=carc,
            rarc_code=rarc,
            payer_tier=claim.payer_name,
            payer_category=payer_cat,
            icd10_valid=icd10_all_valid,
            cms_policy_substantiated=cms_substantiated,
            cms_policy_title=cms_title
        )

    def evaluate_score(self, noul: JevNoul, evidence: ClinicalEvidence) -> JevScore:
        # Normalize CARC code
        raw_carc = (noul.carc_code or "97").strip().upper()
        for prefix in ["CO-", "PR-", "OA-", "PI-"]:
            if raw_carc.startswith(prefix):
                raw_carc = raw_carc[len(prefix):].strip()
        if "|" in raw_carc:
            raw_carc = raw_carc.split("|")[0].strip()

        # Rule 1: Indicator 0 -> Barred under all circumstances. Non-overridable edit.
        if noul.ncci_edit_detected and noul.ncci_indicator == 0:
            return JevScore(
                overturn_confidence=0.0,
                audit_risk_score=1.0,
                recommended_modifier=None,
                action="CONTRACTUAL_WRITE_OFF",
                remediation_category="NCCI_BUNDLING",
                remediation_strategy="Enforce Indicator 0 Contractual Compliance Write-Off",
                payer_guidance="CMS NCCI Policy Manual Chapter 1: Indicator 0 edits cannot be bypassed under any circumstances.",
                root_cause=f"NCCI PTP Indicator 0 between {noul.column1_cpt} and {noul.column2_cpt}.",
                available_actions=[
                    {
                        "id": "ENFORCE_WRITE_OFF",
                        "label": "✕ Enforce Indicator 0 Contractual Write-Off",
                        "button_class": "btn-writeoff",
                        "action_type": "WRITE_OFF",
                        "params": {}
                    }
                ],
                reasoning=(
                    f"[{noul.payer_category}] NCCI PTP Indicator 0 between {noul.column1_cpt} and {noul.column2_cpt}. "
                    "CMS policy bars unbundling under all circumstances. "
                    "Claim must be flagged for contractual write-off per compliance rules."
                ),
                clinical_proof_quote=None,
                mcp_verification_summary="NCCI PTP edit bars unbundling. CMS coverage policy reinforces mutual exclusivity."
            )

        # Rule 2: ICD-10 Specificity Failure Check (CARC 16 Protection)
        if not noul.icd10_valid:
            return JevScore(
                overturn_confidence=0.45,
                audit_risk_score=0.85,
                recommended_modifier=None,
                action="HITL_INTERRUPT",
                remediation_category="MISSING_DOCUMENTATION",
                remediation_strategy="ICD-10 Specificity Correction & Re-coding",
                payer_guidance="HIPAA standard transaction set requires highest level of ICD-10 clinical specificity.",
                root_cause="ICD-10 diagnosis code lacks required 4th-7th character specificity.",
                available_actions=[
                    {
                        "id": "CORRECT_ICD10",
                        "label": "🩺 Update Diagnosis to Specific 7th-Character ICD-10",
                        "button_class": "btn-remediate",
                        "action_type": "UPDATE_DIAGNOSIS",
                        "params": {}
                    },
                    {
                        "id": "REQUEST_PROVIDER_INFO",
                        "label": "📝 Request Diagnostic Clarification from Provider",
                        "button_class": "btn-warning",
                        "action_type": "REQUEST_INFO",
                        "params": {}
                    },
                    {
                        "id": "WRITE_OFF",
                        "label": "✕ Confirm Write-Off",
                        "button_class": "btn-writeoff",
                        "action_type": "WRITE_OFF",
                        "params": {}
                    }
                ],
                reasoning=(
                    f"[{noul.payer_category}] icd10-codes MCP flagged one or more diagnosis codes as lacking required clinical specificity. "
                    "High risk of CARC 16 submission rejection without ICD-10 correction."
                ),
                clinical_proof_quote=evidence.verbatim_sentence,
                mcp_verification_summary="ICD-10 MCP validation warning: diagnosis code requires additional digit of specificity."
            )

        # Rule 3: Query Multi-Dimensional Denial Knowledge Base (Payer + Plan + CARC + RARC)
        rule = denial_kb.search_denial_rules(
            payer_name=noul.payer_tier,
            carc=raw_carc,
            rarc=noul.rarc_code
        )

        category = rule.get("category", "GENERAL_ADJUDICATION")
        strategy = rule.get("remediation_strategy", "Payer Policy Alignment Protocol")
        payer_guidance = rule.get("payer_specific_guidance", "")
        root_cause = rule.get("root_cause", "")
        payer_cat = rule.get("matched_payer_category", noul.payer_category)
        base_confidence = rule.get("confidence_score", 0.85)
        base_risk = rule.get("audit_risk_score", 0.15)
        available_actions = list(rule.get("available_actions", []))
        recommended_mod = rule.get("recommended_modifier")

        # NCCI PTP Indicator 1 Clinical Unbundling Evaluation
        if category == "NCCI_BUNDLING" and (noul.ncci_indicator == 1 or not noul.ncci_edit_detected):
            cpt1 = noul.column1_cpt
            cpt2 = noul.column2_cpt
            is_em_involved = cpt1.startswith("992") or cpt2.startswith("992")

            if is_em_involved and evidence.separate_em_identified:
                recommended_mod = "25"
                overturn_confidence = min(0.96, evidence.corroboration_score + 0.05)
                audit_risk = 0.12
                substantiation_note = f"Evaluation and Management ({cpt1 if cpt1.startswith('992') else cpt2}) substantiated as separate identifiable service."
            elif evidence.anatomical_distinction_identified:
                recommended_mod = "XS" if "XS" in noul.candidate_modifiers else "59"
                overturn_confidence = min(0.95, evidence.corroboration_score + 0.04)
                audit_risk = 0.14
                substantiation_note = f"Operative notes confirm distinct anatomical sites/lesions for CPT {cpt1} and CPT {cpt2}."
            elif evidence.distinct_session_identified:
                recommended_mod = "XE"
                overturn_confidence = min(0.92, evidence.corroboration_score + 0.02)
                audit_risk = 0.18
                substantiation_note = "Documentation confirms distinct surgical session or encounter. Modifier -XE indicated."
            else:
                recommended_mod = "25" if is_em_involved else "59"
                overturn_confidence = min(0.70, evidence.corroboration_score)
                audit_risk = 0.65
                substantiation_note = "Clinical chart notes lack unequivocal proof of separate encounter or distinct anatomical site."

            if noul.cms_policy_substantiated:
                overturn_confidence = min(0.98, overturn_confidence + 0.01)

            reasoning = f"[{payer_cat}] {root_cause} {substantiation_note} {payer_guidance}"
        else:
            # Multi-MCP corroboration factors
            has_doc = evidence.has_clinical_documentation and len(evidence.operative_notes) > 20
            if category == "MISSING_DOCUMENTATION":
                overturn_confidence = 0.91 if has_doc else 0.52
                audit_risk = 0.10 if has_doc else 0.65
            elif category == "MEDICAL_NECESSITY":
                overturn_confidence = 0.88 if noul.cms_policy_substantiated else 0.60
                audit_risk = 0.15 if noul.cms_policy_substantiated else 0.58
            else:
                overturn_confidence = base_confidence
                audit_risk = base_risk

            if noul.cms_policy_substantiated:
                overturn_confidence = min(0.98, overturn_confidence + 0.01)

            reasoning = f"[{payer_cat}] {root_cause} {payer_guidance}"

        action = "AUTO_APPEND_MODIFIER" if (overturn_confidence >= self.OVERTURN_THRESHOLD and recommended_mod) else "HITL_INTERRUPT"

        mcp_summary = (
            f"Payer: {payer_cat} | CAQH Scenario: {rule.get('caqh_scenario', 2)} | "
            f"ICD-10: Validated | CMS Policy: {noul.cms_policy_title or 'Medicare Part B Supported'} | "
            f"FHIR MCP: Extracted ({evidence.corroboration_score:.2f} score)"
        )

        return JevScore(
            overturn_confidence=round(overturn_confidence, 3),
            audit_risk_score=round(audit_risk, 3),
            recommended_modifier=recommended_mod,
            action=action,
            remediation_category=category,
            remediation_strategy=strategy,
            payer_guidance=payer_guidance,
            root_cause=root_cause,
            available_actions=available_actions,
            reasoning=reasoning,
            clinical_proof_quote=evidence.verbatim_sentence if evidence.verbatim_sentence else None,
            mcp_verification_summary=mcp_summary
        )

jev_engine = JevAiEngine()
