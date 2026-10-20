import os
from app.adapters.neon_db import db
from app.models import NcciPtpEdit, Claim837, Remittance835, ClaimLineItem, LineAdjudication

def seed_database():
    print("🌱 Seeding NCCI PTP Edits...")
    
    edits = [
        # E/M with Minor Surgery (Modifier -25 permissible)
        NcciPtpEdit(
            column1_cpt="99214",
            column2_cpt="11102",
            indicator=1,
            effective_date="2024-01-01",
            rationale="Standards of medical/surgical practice; E/M service may be billed with Modifier -25 if significant and separately identifiable.",
            allowed_modifiers=["25"]
        ),
        NcciPtpEdit(
            column1_cpt="99213",
            column2_cpt="17000",
            indicator=1,
            effective_date="2024-01-01",
            rationale="Separate identifiable E/M evaluation may justify Modifier -25 if distinctly documented from procedure.",
            allowed_modifiers=["25"]
        ),
        # Surgical Procedures (Distinct site Modifier -59 or -XS)
        NcciPtpEdit(
            column1_cpt="45385",
            column2_cpt="45380",
            indicator=1,
            effective_date="2024-01-01",
            rationale="Endoscopic procedures bundled unless performed at separate anatomical sites or separate lesions (Modifier -59 or -XS).",
            allowed_modifiers=["59", "XS"]
        ),
        NcciPtpEdit(
            column1_cpt="17311",
            column2_cpt="12032",
            indicator=1,
            effective_date="2024-01-01",
            rationale="Repair bundled with Mohs unless repair is at a distinct site or intermediate/complex closure meets distinct criteria (Modifier -59).",
            allowed_modifiers=["59", "XS"]
        ),
        # Barred Edits (Indicator 0 -> Never unbundled, must write-off)
        NcciPtpEdit(
            column1_cpt="29881",
            column2_cpt="29877",
            indicator=0,
            effective_date="2023-01-01",
            rationale="Knee arthroscopy debridement/chondroplasty bundled into meniscectomy in same compartment under CMS guidelines. Indicator 0: Non-overridable edit.",
            allowed_modifiers=[]
        ),
        NcciPtpEdit(
            column1_cpt="80053",
            column2_cpt="82565",
            indicator=0,
            effective_date="2022-01-01",
            rationale="Serum creatinine is an elemental constituent of Comprehensive Metabolic Panel (80053). Indicator 0: Cannot be unbundled.",
            allowed_modifiers=[]
        ),
        NcciPtpEdit(
            column1_cpt="43239",
            column2_cpt="43235",
            indicator=0,
            effective_date="2023-01-01",
            rationale="Diagnostic EGD (43235) is inherently included in EGD with biopsy (43239). Indicator 0.",
            allowed_modifiers=[]
        )
    ]

    for edit in edits:
        db.upsert_ncci_edit(edit)

    print("📄 Seeding EDI 837 Claims and 835 Remittances...")

    # Claim 1: E/M 99214 + 11102 (Tangible distinct E/M -> Auto Remediate with -25)
    c1 = Claim837(
        claim_id="CLM-2026-901",
        patient_id="PAT-10842",
        patient_name="Eleanor Vance",
        dob="1968-04-14",
        payer_id="MEDICARE-FL",
        payer_name="First Coast Service Options (Medicare Part B)",
        date_of_service="2026-08-10",
        rendering_npi="1942083411",
        billing_npi="1023948512",
        diagnosis_codes=["L82.1", "C44.319", "I10"],
        line_items=[
            ClaimLineItem(
                line_number=1,
                cpt_code="99214",
                description="Office/outpatient visit est patient moderate mdm 30-39 min",
                modifiers=[],
                billed_amount=195.00
            ),
            ClaimLineItem(
                line_number=2,
                cpt_code="11102",
                description="Tangential biopsy of skin single lesion",
                modifiers=[],
                billed_amount=165.00
            )
        ],
        total_billed=360.00,
        clinical_notes="""CLINICAL PROGRESS NOTE:
Patient presents for comprehensive 6-month chronic hypertension and hyperlipidemia medication management review. Blood pressure today 142/88. Renal panel reviewed and stable. Dose of Lisinopril adjusted to 20mg daily.
SEPARATE CONCERN IDENTIFIED:
During the routine physical examination, patient noted a bleeding, irregular pearly papule on the left nasal ala noticed 3 weeks ago. Exam confirms 6mm friable lesion suspicious for basal cell carcinoma. Discussed risks/benefits of immediate tangential punch biopsy. Separate written consent obtained. Biopsy performed of left nasal ala lesion under 1% lidocaine with epinephrine.
Hemostasis achieved. Specimen sent to dermatopathology. Separate and distinct evaluation time: 25 minutes for chronic disease management; biopsy completed thereafter.""",
        status="PENDING"
    )
    db.save_claim(c1)
    db.save_remittance(Remittance835(
        claim_id="CLM-2026-901",
        remittance_id="REM-89210",
        check_number="CHK-9912041",
        adjudication_date="2026-08-22",
        total_billed=360.00,
        total_paid=142.50,
        patient_responsibility=35.50,
        primary_carc="97",
        primary_reason="CARC 97: The benefit for this service is included in the payment/allowance for another service.",
        line_adjudications=[
            LineAdjudication(line_number=1, cpt_code="99214", billed_amount=195.00, allowed_amount=178.00, paid_amount=142.50),
            LineAdjudication(line_number=2, cpt_code="11102", billed_amount=165.00, allowed_amount=0.00, paid_amount=0.00,
                             carc_codes=["97"], rarc_codes=["N390"], denial_reason="NCCI PTP edit: Procedure unbundled without modifier -25 on E/M service")
        ]
    ))

    # Claim 2: Colonoscopy 45385 + 45380 (Distinct anatomical site -> Auto Remediate with -59 / -XS)
    c2 = Claim837(
        claim_id="CLM-2026-902",
        patient_id="PAT-40291",
        patient_name="Arthur Pendelton",
        dob="1955-11-23",
        payer_id="UHC-COMM",
        payer_name="UnitedHealthcare Commercial",
        date_of_service="2026-08-14",
        rendering_npi="1487291032",
        billing_npi="1023948512",
        diagnosis_codes=["D12.6", "K63.5"],
        line_items=[
            ClaimLineItem(
                line_number=1,
                cpt_code="45385",
                description="Colonoscopy flexible with removal of tumor polyp by snare technique",
                modifiers=[],
                billed_amount=1250.00
            ),
            ClaimLineItem(
                line_number=2,
                cpt_code="45380",
                description="Colonoscopy flexible with single or multiple biopsy",
                modifiers=[],
                billed_amount=680.00
            )
        ],
        total_billed=1930.00,
        clinical_notes="""OPERATIVE REPORT - COLONOSCOPY:
Preoperative Diagnosis: Screening / history of adenomatous polyps.
Procedure: The Olympus adult colonoscope was introduced through the anus and advanced to the cecum.
FINDINGS:
1. In the cecum/ascending colon at 75 cm, a 15mm pedunculated polyp was identified. Successfully resected using hot snare electrocautery (CPT 45385). Complete retrieval.
2. In the descending colon at 35 cm, a completely separate, distinct 4mm flat erythematous mucosal patch was identified. Cold forceps biopsy performed (CPT 45380).
Documented distinct anatomical sites: Lesion 1 in ascending colon (snare), Lesion 2 in descending colon (forceps biopsy).""",
        status="PENDING"
    )
    db.save_claim(c2)
    db.save_remittance(Remittance835(
        claim_id="CLM-2026-902",
        remittance_id="REM-89211",
        check_number="CHK-4820192",
        adjudication_date="2026-08-25",
        total_billed=1930.00,
        total_paid=780.00,
        patient_responsibility=120.00,
        primary_carc="97",
        primary_reason="CARC 97: Bundled procedure without distinct anatomical modifier.",
        line_adjudications=[
            LineAdjudication(line_number=1, cpt_code="45385", billed_amount=1250.00, allowed_amount=900.00, paid_amount=780.00),
            LineAdjudication(line_number=2, cpt_code="45380", billed_amount=680.00, allowed_amount=0.00, paid_amount=0.00,
                             carc_codes=["97"], rarc_codes=["CO-97"], denial_reason="NCCI PTP edit: 45380 bundled with 45385")
        ]
    ))

    # Claim 3: Knee Arthroscopy 29881 + 29877 (Indicator 0 -> Barred -> Contractual Write-off)
    c3 = Claim837(
        claim_id="CLM-2026-903",
        patient_id="PAT-59182",
        patient_name="Marcus Brody",
        dob="1982-02-09",
        payer_id="AETNA-01",
        payer_name="Aetna Open Choice PPO",
        date_of_service="2026-08-16",
        rendering_npi="1720194821",
        billing_npi="1023948512",
        diagnosis_codes=["M23.22", "M17.11"],
        line_items=[
            ClaimLineItem(
                line_number=1,
                cpt_code="29881",
                description="Arthroscopy knee surgical with meniscectomy medial or lateral",
                modifiers=[],
                billed_amount=2400.00
            ),
            ClaimLineItem(
                line_number=2,
                cpt_code="29877",
                description="Arthroscopy knee surgical debridement/shaving articular cartilage chondroplasty",
                modifiers=[],
                billed_amount=950.00
            )
        ],
        total_billed=3350.00,
        clinical_notes="""OPERATIVE REPORT - RIGHT KNEE ARTHROSCOPY:
Patient with medial meniscus tear and localized grade III chondromalacia of the medial femoral condyle.
Diagnostic arthroscopy performed. In the medial compartment, a complex tear of the posterior horn of the medial meniscus was identified. Partial medial meniscectomy performed with shaver. Articular cartilage debridement/chondroplasty performed in the same medial compartment. No pathology identified in patellofemoral or lateral compartments.""",
        status="PENDING"
    )
    db.save_claim(c3)
    db.save_remittance(Remittance835(
        claim_id="CLM-2026-903",
        remittance_id="REM-89212",
        check_number="CHK-7102941",
        adjudication_date="2026-08-28",
        total_billed=3350.00,
        total_paid=1650.00,
        patient_responsibility=200.00,
        primary_carc="97",
        primary_reason="CARC 97: Chondroplasty in same compartment bundled into meniscectomy. Indicator 0.",
        line_adjudications=[
            LineAdjudication(line_number=1, cpt_code="29881", billed_amount=2400.00, allowed_amount=1850.00, paid_amount=1650.00),
            LineAdjudication(line_number=2, cpt_code="29877", billed_amount=950.00, allowed_amount=0.00, paid_amount=0.00,
                             carc_codes=["97"], rarc_codes=["M80"], denial_reason="NCCI PTP Indicator 0: Mutual exclusivity edit, cannot bypass with modifier")
        ]
    ))

    # Claim 4: E/M 99213 + 17000 (Ambiguous chart note -> Confidence 0.68 -> HITL Interrupt)
    c4 = Claim837(
        claim_id="CLM-2026-904",
        patient_id="PAT-77210",
        patient_name="Dorothy Gale",
        dob="1974-09-02",
        payer_id="BCBS-TX",
        payer_name="Blue Cross Blue Shield of Texas",
        date_of_service="2026-08-18",
        rendering_npi="1942083411",
        billing_npi="1023948512",
        diagnosis_codes=["L57.0", "Z79.899"],
        line_items=[
            ClaimLineItem(
                line_number=1,
                cpt_code="99213",
                description="Office visit est patient low-moderate mdm",
                modifiers=[],
                billed_amount=140.00
            ),
            ClaimLineItem(
                line_number=2,
                cpt_code="17000",
                description="Destruction premalignant lesion actinic keratosis first",
                modifiers=[],
                billed_amount=110.00
            )
        ],
        total_billed=250.00,
        clinical_notes="""CLINICAL NOTE:
Patient in for follow up actinic keratosis. Lesion on right cheek frozen with liquid nitrogen for 10 seconds. Patient tolerated well. Will follow up in 6 months.""",
        status="PENDING"
    )
    db.save_claim(c4)
    db.save_remittance(Remittance835(
        claim_id="CLM-2026-904",
        remittance_id="REM-89213",
        check_number="CHK-3019842",
        adjudication_date="2026-08-30",
        total_billed=250.00,
        total_paid=85.00,
        patient_responsibility=15.00,
        primary_carc="97",
        primary_reason="CARC 97: Evaluation and management service bundled into minor surgical procedure.",
        line_adjudications=[
            LineAdjudication(line_number=1, cpt_code="99213", billed_amount=140.00, allowed_amount=0.00, paid_amount=0.00,
                             carc_codes=["97"], rarc_codes=["CO-97"], denial_reason="Modifier -25 required for separate E/M"),
            LineAdjudication(line_number=2, cpt_code="17000", billed_amount=110.00, allowed_amount=100.00, paid_amount=85.00)
        ]
    ))

    # Claim 5: Mohs Surgery 17311 + Intermediate Repair 12032 (Distinct site -> Auto Remediate -59)
    c5 = Claim837(
        claim_id="CLM-2026-905",
        patient_id="PAT-99381",
        patient_name="Victor Frankenstein",
        dob="1960-07-15",
        payer_id="CIGNA-CORP",
        payer_name="Cigna Health and Life",
        date_of_service="2026-08-20",
        rendering_npi="1382910482",
        billing_npi="1023948512",
        diagnosis_codes=["C44.41", "C44.321"],
        line_items=[
            ClaimLineItem(
                line_number=1,
                cpt_code="17311",
                description="Mohs micrographic technique first stage head neck",
                modifiers=[],
                billed_amount=1800.00
            ),
            ClaimLineItem(
                line_number=2,
                cpt_code="12032",
                description="Repair intermediate wounds scalp axillae trunk 2.6 cm to 7.5 cm",
                modifiers=[],
                billed_amount=650.00
            )
        ],
        total_billed=2450.00,
        clinical_notes="""OPERATIVE REPORT - MOHS AND SEPARATE SITE CLOSURE:
Patient had Mohs excision of squamous cell carcinoma of the right temple (stage 1, clear margins). Defect closed primarily (17311).
ADDITIONAL SEPARATE SURGICAL PROCEDURE:
Patient had a previously biopsied 3.5cm surgical wound on the posterior scalp that had opened and required intermediate layered wound debridement and dual-layer closure with 3-0 Vicryl and 4-0 Ethilon (CPT 12032). This repair was at an entirely separate anatomical location (posterior scalp vs right temple) and performed in the same surgical session.""",
        status="PENDING"
    )
    db.save_claim(c5)
    db.save_remittance(Remittance835(
        claim_id="CLM-2026-905",
        remittance_id="REM-89214",
        check_number="CHK-5591023",
        adjudication_date="2026-09-01",
        total_billed=2450.00,
        total_paid=1400.00,
        patient_responsibility=150.00,
        primary_carc="97",
        primary_reason="CARC 97: Surgical repair bundled into primary surgical excision.",
        line_adjudications=[
            LineAdjudication(line_number=1, cpt_code="17311", billed_amount=1800.00, allowed_amount=1550.00, paid_amount=1400.00),
            LineAdjudication(line_number=2, cpt_code="12032", billed_amount=650.00, allowed_amount=0.00, paid_amount=0.00,
                             carc_codes=["97"], rarc_codes=["CO-97"], denial_reason="NCCI PTP edit: 12032 bundled into 17311")
        ]
    ))

    print("✅ Seed data populated successfully!")

if __name__ == "__main__":
    seed_database()
