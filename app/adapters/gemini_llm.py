import os
from typing import Optional, Dict, Any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

class GeminiLlmAdapter:
    """
    Google Gemini LLM Adapter for Healthcare Claims Prediction and Remediation.
    Performs clinical chart reasoning, medical necessity corroboration,
    and automated EDI 837 appeal packet generation.
    """
    def __init__(self):
        self.api_key = GEMINI_API_KEY
        self.client = None
        if self.api_key and self.api_key != "your_gemini_api_key":
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"Warning: Failed to initialize Google GenAI Client: {e}")

    def generate_appeal_letter(
        self,
        claim_id: str,
        patient_name: str,
        dos: str,
        payer_name: str,
        cpt_pairs: str,
        modifier: str,
        clinical_evidence: str,
        verbatim_quote: str,
        carc_code: str = "97"
    ) -> str:
        prompt = f"""You are a certified healthcare revenue cycle management (RCM) billing appeal specialist.
Draft a concise, authoritative formal appeal letter to overturn the denial for claim {claim_id}.

Patient: {patient_name}
Date of Service: {dos}
Payer: {payer_name}
Denial Code: CARC {carc_code} (Service included in payment of another service / NCCI PTP edit)
Procedures in Question: {cpt_pairs}
Remediation Action: Appended Modifier -{modifier}
Clinical Proof: {clinical_evidence}
Verbatim Clinical Documentation Quote: "{verbatim_quote}"

Structure the letter with:
1. Re-adjudication Request Header
2. Clinical Necessity & Independent Service Justification under CMS NCCI Policy Manual Chapter 1
3. Direct Citation of the Medical Record
4. Request for Immediate Payment of Remediated Line Item"""

        if self.client:
            try:
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"Gemini API call failed, using high-fidelity clinical template: {e}")

        # Authoritative clinical template fallback
        return f"""REVENUE CYCLE RE-ADJUDICATION & FORMAL APPEAL REQUEST
Date: {dos}
To: Claims Adjudication Department, {payer_name}
Re: Formal Overturn Request for Claim ID {claim_id} | Patient: {patient_name}

To Medical Review & Claims Adjudication:

We are formally requesting re-adjudication of Claim {claim_id} for services rendered on {dos}. Line item denial under CARC {carc_code} ("benefit included in allowance of another service") was issued due to an initial omission of Modifier -{modifier}.

CLINICAL SUBSTANTIATION & CMS NCCI GUIDELINES:
In accordance with Chapter 1, Section E of the CMS National Correct Coding Initiative (NCCI) Policy Manual:
"{verbatim_quote}"

The operative and progress records unequivocally demonstrate that the service in question constitutes a significant, distinct service (Modifier -{modifier}) performed at a separate anatomical location or representing a separately identifiable medical service from the primary procedure ({cpt_pairs}).

DOCUMENTATION CITATION:
Review of the attached electronic medical record confirms:
• Document Type: Operative / Progress Note extracted via FHIR EHR Integration
• Direct Evidence: {clinical_evidence}

Based on these clinical ground truths, Modifier -{modifier} has been formally appended to the corrected 837 claim submission. We request prompt reprocessing and remittance of the allowable amount.

Sincerely,
Revenue Cycle Remediation & Appeals Division"""

gemini_adapter = GeminiLlmAdapter()
