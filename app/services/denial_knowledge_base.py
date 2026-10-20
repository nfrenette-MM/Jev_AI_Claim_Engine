import os
import json
from typing import Dict, Any, List, Optional, Tuple

CROSSWALK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "carc_rarc_crosswalk.json")

class DenialKnowledgeBase:
    """
    Healthcare Payer & Denial Reasoning Knowledge Base.
    Incorporates methodologies from:
      1. Microsoft RHAIL Claims Denial Navigator (root cause extraction & resolution routing)
      2. ClaimPilot (payer policy contextualization & appeal letter generation)
      3. AWS Healthcare Multi-Agent framework (search_denial_codes protocol & clinical evidence packaging)
      4. Kustode Medical Billing MCP (X12 WPC & CAQH CORE Phase III Rule 360 standards)
    """

    def __init__(self, crosswalk_file: str = CROSSWALK_PATH):
        self.crosswalk_file = crosswalk_file
        self.rules: List[Dict[str, Any]] = []
        self._load_crosswalk()

    def _load_crosswalk(self):
        if os.path.exists(self.crosswalk_file):
            try:
                with open(self.crosswalk_file, "r") as f:
                    self.rules = json.load(f)
            except Exception as e:
                print(f"[DenialKnowledgeBase] Error loading crosswalk: {e}")
                self.rules = []
        else:
            self.rules = []

    def classify_payer(self, payer_name: str) -> Tuple[str, str]:
        """
        Classifies incoming payer string into standard category and plan type:
        Categories: MEDICARE, MEDICARE_ADVANTAGE, COMMERCIAL, MEDICAID, WORKERS_COMP, AUTO_PIP
        """
        if not payer_name:
            return "COMMERCIAL", "PPO"

        name = payer_name.upper()

        # Workers' Compensation
        if any(w in name for w in ["CORVEL", "SEDGWICK", "NYSIF", "BROADSPIRE", "WORKERS", "W/C", "FECA", "LABOR"]):
            return "WORKERS_COMP", "WC_STATUTORY"

        # Auto PIP / MVA
        if any(w in name for w in ["GEICO", "LIBERTY MUTUAL", "TRAVELERS", "CHUBB", "AUTO", "MVA", "MANUFACTURING - AUTO", "PIP"]):
            return "AUTO_PIP", "PIP_MVA"

        # Medicare Advantage
        if any(w in name for w in ["MEDICARE ADVANTAGE", "AARP MEDICARE", "MCR DUALCARE", "CLOVER", "UCARE", "ESSENCE", "MVP MEDICARE"]):
            return "MEDICARE_ADVANTAGE", "MA_HMO"

        # Traditional Medicare Part B
        if any(w in name for w in ["MEDICARE", "FIRST COAST", "NORIDIAN", "NOVITAS", "PALMETTO", "CEDI", "DMERC"]):
            return "MEDICARE", "PART_B"

        # Medicaid / Managed Medicaid
        if any(w in name for w in ["MEDICAID", "MEDI-CAL", "FIDELIS", "MOLINA", "CENTENE", "AMERIGROUP", "HORIZON NJ HEALTH", "LA CARE", "AFFINITY", "CARESOURCE"]):
            return "MEDICAID", "MANAGED_MEDICAID"

        # Commercial default (Aetna, BCBS, Cigna, UHC, UMR, Meritain, etc.)
        return "COMMERCIAL", "PPO"

    def search_denial_rules(
        self,
        payer_name: str,
        carc: str,
        rarc: Optional[str] = None,
        group_code: str = "CO"
    ) -> Dict[str, Any]:
        """
        Multi-dimensional lookup: Payer Scope + Plan Type + CARC + RARC + Group Code
        Returns tailored strategy, root cause, required evidence, and dynamic next actions.
        """
        payer_cat, plan_type = self.classify_payer(payer_name)
        clean_carc = (carc or "97").strip().upper()
        for prefix in ["CO-", "PR-", "OA-", "PI-"]:
            if clean_carc.startswith(prefix):
                clean_carc = clean_carc[len(prefix):].strip()
        if "|" in clean_carc:
            clean_carc = clean_carc.split("|")[0].strip()

        clean_rarc = rarc.strip().upper() if rarc else None

        # Level 1: Exact match on (payer_category, carc, rarc)
        if clean_rarc:
            for rule in self.rules:
                if (
                    rule.get("payer_category") == payer_cat
                    and rule.get("carc") == clean_carc
                    and rule.get("rarc") == clean_rarc
                ):
                    return self._enrich_rule(rule, payer_cat, plan_type)

        # Level 2: Match on (payer_category, carc) regardless of rarc
        for rule in self.rules:
            if rule.get("payer_category") == payer_cat and rule.get("carc") == clean_carc:
                return self._enrich_rule(rule, payer_cat, plan_type)

        # Level 3: Match on global ALL scope with exact (carc, rarc)
        if clean_rarc:
            for rule in self.rules:
                if (
                    rule.get("payer_category") == "ALL"
                    and rule.get("carc") == clean_carc
                    and rule.get("rarc") == clean_rarc
                ):
                    return self._enrich_rule(rule, payer_cat, plan_type)

        # Level 4: Match on global ALL scope with carc
        for rule in self.rules:
            if rule.get("payer_category") == "ALL" and rule.get("carc") == clean_carc:
                return self._enrich_rule(rule, payer_cat, plan_type)

        # Level 5: Smart dynamic synthesized fallback
        return self._generate_dynamic_fallback(payer_cat, plan_type, clean_carc, clean_rarc)

    def _enrich_rule(self, rule: Dict[str, Any], payer_cat: str, plan_type: str) -> Dict[str, Any]:
        res = dict(rule)
        res["matched_payer_category"] = payer_cat
        res["matched_plan_type"] = plan_type
        return res

    def _generate_dynamic_fallback(
        self,
        payer_cat: str,
        plan_type: str,
        carc: str,
        rarc: Optional[str]
    ) -> Dict[str, Any]:
        """
        Dynamically generates structured guidance for any novel CARC/RARC code
        based on X12 CAQH CORE principles.
        """
        return {
            "rule_id": f"DYNAMIC_{payer_cat}_{carc}_{rarc or 'ANY'}",
            "carc": carc,
            "rarc": rarc,
            "group_code": "CO",
            "payer_category": payer_cat,
            "plan_type": plan_type,
            "matched_payer_category": payer_cat,
            "matched_plan_type": plan_type,
            "category": "GENERAL_ADJUDICATION",
            "caqh_scenario": 2,
            "root_cause": f"Payer {payer_cat} ({plan_type}) adjudicated claim line under CARC {carc} (RARC: {rarc or 'None'}).",
            "remediation_strategy": f"Payer Policy Alignment & Remediation Protocol for CARC {carc}",
            "payer_specific_guidance": f"Review {payer_cat} claim adjustment guidelines for CARC {carc}. Check operative notes and submit corrected billing or formal dispute within payer appeal limits.",
            "required_evidence": "Clinical operative documentation, signed physician order, or corrected claim data.",
            "confidence_score": 0.80,
            "audit_risk_score": 0.20,
            "available_actions": [
                {
                    "id": f"APPEAL_CARC_{carc}",
                    "label": f"📄 File {payer_cat} Formal Appeal (CARC {carc})",
                    "button_class": "btn-remediate",
                    "action_type": "SUBMIT_APPEAL",
                    "params": {"appeal_type": f"CARC_{carc}_OVERTURN"}
                },
                {
                    "id": f"CORRECTED_CLAIM_{carc}",
                    "label": "📤 Resubmit as Corrected Claim (Frequency 7)",
                    "button_class": "btn-accent",
                    "action_type": "SUBMIT_APPEAL",
                    "params": {"appeal_type": "CORRECTED_CLAIM"}
                },
                {
                    "id": "WRITE_OFF",
                    "label": "✕ Confirm Contractual Write-Off",
                    "button_class": "btn-writeoff",
                    "action_type": "WRITE_OFF",
                    "params": {}
                }
            ],
            "appeal_template_key": "GENERAL_APPEAL"
        }

    def get_all_rules(self) -> List[Dict[str, Any]]:
        return self.rules

denial_kb = DenialKnowledgeBase()
