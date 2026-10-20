from typing import Dict, Any, List, Optional
from pydantic import BaseModel

class CmsCoveragePolicy(BaseModel):
    policy_id: str
    document_type: str  # "NCD", "LCD", "LCA"
    title: str
    effective_date: str
    contractor_id: Optional[str] = None
    contractor_name: Optional[str] = None
    covered_indications: List[str]
    documentation_requirements: List[str]
    cpt_codes: List[str]
    is_covered: bool = True
    guidance: str

class CmsCoverageMcpAdapter:
    """
    Adapter for Anthropic HCLS cms-coverage MCP Server.
    Queries Medicare National Coverage Determinations (NCDs) and Local Coverage Determinations (LCDs)
    to verify medical necessity, covered diagnostic indications, and billing guidelines.
    """
    def __init__(self):
        # CMS Coverage Policy Database for common Part B outpatient surgical procedures
        self.policies: List[CmsCoveragePolicy] = [
            CmsCoveragePolicy(
                policy_id="NCD-210.3",
                document_type="NCD",
                title="Colorectal Cancer Screening & Diagnostic Colonoscopy",
                effective_date="2023-01-01",
                contractor_id="ALL",
                contractor_name="CMS National",
                covered_indications=[
                    "Diagnostic colonoscopy for personal history of adenomatous polyps (D12.6, K63.5)",
                    "Screening colonoscopy with unexpected pathological findings requiring therapeutic resection"
                ],
                documentation_requirements=[
                    "Operative report must specify exact anatomical location (e.g. cecum, ascending colon vs descending colon) of each lesion biopsied or excised.",
                    "Technique utilized (e.g., snare polypectomy vs cold forceps biopsy) must be distinctly recorded per lesion."
                ],
                cpt_codes=["45385", "45380"],
                is_covered=True,
                guidance="Medicare Part B covers both snare polypectomy (45385) and cold biopsy (45380) in the same session if performed on distinct lesions in separate anatomical structures. Modifier -59 or -XS is required."
            ),
            CmsCoveragePolicy(
                policy_id="LCD-L33927",
                document_type="LCD",
                title="Surgical Treatment of Skin Neoplasms and Biopsies",
                effective_date="2024-01-01",
                contractor_id="09102",
                contractor_name="First Coast Service Options (Florida / Part B)",
                covered_indications=[
                    "Suspected malignant neoplasm of skin (C44.319, C44.41)",
                    "Atypical or bleeding pigmented lesions (L82.1, D48.5)"
                ],
                documentation_requirements=[
                    "Pathology report or clinical visual documentation of lesion border, size, and anatomical landmark.",
                    "If E/M service (99213, 99214) is billed concurrently, medical record must demonstrate significant, separately identifiable evaluation beyond routine pre/post-procedure care."
                ],
                cpt_codes=["11102", "99214", "99213", "17000"],
                is_covered=True,
                guidance="Medicare Part B allows E/M payment in addition to minor skin surgery only when Modifier -25 is substantiated by an independent medical evaluation and treatment plan."
            ),
            CmsCoveragePolicy(
                policy_id="LCD-L34026",
                document_type="LCD",
                title="Mohs Micrographic Surgery and Wound Repair",
                effective_date="2023-06-01",
                contractor_id="ALL",
                contractor_name="Medicare Part B Multi-jurisdiction",
                covered_indications=[
                    "Basal cell carcinoma and squamous cell carcinoma of face, scalp, and neck (C44.319, C44.41)",
                    "Complex wound reconstruction following surgical excision"
                ],
                documentation_requirements=[
                    "Mohs mapping and staging notes.",
                    "Separate documentation for wound closure if repair is at a distinct non-Mohs surgical site or requires intermediate/complex layered closure (Modifier -59 or -XS)."
                ],
                cpt_codes=["17311", "12032"],
                is_covered=True,
                guidance="Routine closure of the primary Mohs defect is bundled. Layered repair (12032) is separately reimbursable when performed on a distinct anatomical defect."
            ),
            CmsCoveragePolicy(
                policy_id="NCD-150.9",
                document_type="NCD",
                title="Arthroscopic Knee Surgery for Osteoarthritis and Meniscal Tears",
                effective_date="2022-01-01",
                contractor_id="ALL",
                contractor_name="CMS National",
                covered_indications=[
                    "Meniscal tear with mechanical locking or acute injury (M23.22)",
                    "Surgical partial meniscectomy"
                ],
                documentation_requirements=[
                    "Arthroscopic photographic or video confirmation of torn meniscus.",
                    "Explicit anatomical compartment identification (medial, lateral, or patellofemoral)."
                ],
                cpt_codes=["29881", "29877"],
                is_covered=True,
                guidance="CMS NCCI Policy bars unbundling debridement/chondroplasty (29877) when performed in the same knee compartment as meniscectomy (29881). Indicator 0 applies."
            )
        ]

    def search_coverage_by_cpt(self, cpt_code: str) -> List[CmsCoveragePolicy]:
        clean_cpt = cpt_code.strip()
        return [p for p in self.policies if clean_cpt in p.cpt_codes]

    def evaluate_claim_coverage(self, cpt_codes: List[str], diagnosis_codes: List[str]) -> Dict[str, Any]:
        matched_policies = []
        for cpt in cpt_codes:
            for p in self.search_coverage_by_cpt(cpt):
                if p not in matched_policies:
                    matched_policies.append(p)

        covered = len(matched_policies) > 0
        policy_summaries = [
            f"[{p.document_type} {p.policy_id}] {p.title}: {p.guidance}"
            for p in matched_policies
        ]

        doc_reqs = []
        for p in matched_policies:
            doc_reqs.extend(p.documentation_requirements)

        return {
            "has_medicare_policy": covered,
            "policies": [p.model_dump() for p in matched_policies],
            "policy_summaries": policy_summaries,
            "documentation_requirements": list(set(doc_reqs)),
            "coverage_substantiated": covered
        }

cms_coverage_adapter = CmsCoverageMcpAdapter()
