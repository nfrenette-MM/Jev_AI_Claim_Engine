import re
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from app.models import Claim837, Remittance835, ClaimLineItem, LineAdjudication

class EdiParseResult:
    def __init__(self):
        self.claims: List[Claim837] = []
        self.remittances: List[Remittance835] = []
        self.raw_type: str = "UNKNOWN"
        self.errors: List[str] = []

class EdiX12Parser:
    """
    ANSI ASC X12 5010 Parser for Healthcare EDI Transactions:
    - 837 Health Care Claim (Professional / Institutional)
    - 835 Health Care Claim Payment and Remittance Advice
    Supports automatic segment delimiter detection (~, \\n) and element separators (*).
    Also supports structured JSON representations of 837/835.
    """

    def parse(self, raw_content: str, filename: str = "") -> EdiParseResult:
        result = EdiParseResult()
        content = raw_content.strip()

        if not content:
            result.errors.append("Empty EDI content provided.")
            return result

        # Check if structured JSON
        if content.startswith("{") or content.startswith("["):
            try:
                data = json.loads(content)
                self._parse_json_payload(data, result)
                result.raw_type = "JSON"
                return result
            except Exception as e:
                result.errors.append(f"JSON parsing error: {str(e)}")

        # Check if CSV format (Enhanced PM Report / Claims Export)
        first_line = content.split("\n")[0].strip()
        if filename.lower().endswith(".csv") or ("," in first_line and not content.startswith("ISA")):
            try:
                self._parse_csv_payload(content, result)
                if result.claims:
                    result.raw_type = "CSV_PM_REPORT"
                    return result
            except Exception as e:
                result.errors.append(f"CSV parsing error: {str(e)}")

        # Detect X12 Delimiters
        segment_delim = self._detect_segment_delimiter(content)
        segments = [s.strip() for s in content.split(segment_delim) if s.strip()]

        if not segments:
            result.errors.append("No valid X12 segments detected.")
            return result

        # Detect transaction type from ST segment or ISA/GS
        is_837 = any(s.startswith("ST*837") or "837" in s for s in segments[:10])
        is_835 = any(s.startswith("ST*835") or "835" in s for s in segments[:10])

        if is_837:
            result.raw_type = "X12_837"
            self._parse_837_segments(segments, result)
        elif is_835:
            result.raw_type = "X12_835"
            self._parse_835_segments(segments, result)
        else:
            # Fallback: check if content has CLP (835) or CLM (837)
            if any(s.startswith("CLM*") for s in segments):
                result.raw_type = "X12_837"
                self._parse_837_segments(segments, result)
            elif any(s.startswith("CLP*") for s in segments):
                result.raw_type = "X12_835"
                self._parse_835_segments(segments, result)
            else:
                result.errors.append("Could not determine EDI transaction type (neither 837 nor 835).")

        return result

    def _detect_segment_delimiter(self, content: str) -> str:
        if "~" in content:
            return "~"
        elif "\n" in content:
            return "\n"
        return "~"

    def _parse_json_payload(self, data: Union[Dict[str, Any], List[Any]], result: EdiParseResult):
        items = data if isinstance(data, list) else [data]
        for item in items:
            if "claim_id" in item and ("line_items" in item or "patient_id" in item):
                try:
                    c = Claim837(
                        claim_id=str(item.get("claim_id")),
                        patient_id=str(item.get("patient_id", "PAT-UNKNOWN")),
                        patient_name=str(item.get("patient_name", "Anonymous Patient")),
                        dob=str(item.get("dob", "1980-01-01")),
                        payer_id=str(item.get("payer_id", "PAYER-01")),
                        payer_name=str(item.get("payer_name", "Commercial Insurance")),
                        date_of_service=str(item.get("date_of_service", datetime.utcnow().strftime("%Y-%m-%d"))),
                        rendering_npi=str(item.get("rendering_npi", "1999999999")),
                        billing_npi=str(item.get("billing_npi", "1000000000")),
                        diagnosis_codes=item.get("diagnosis_codes", []),
                        line_items=[ClaimLineItem(**li) for li in item.get("line_items", [])],
                        total_billed=float(item.get("total_billed", 0.0)),
                        clinical_notes=str(item.get("clinical_notes", "")),
                        status=item.get("status", "PENDING")
                    )
                    result.claims.append(c)
                except Exception as e:
                    result.errors.append(f"Failed to parse claim JSON: {e}")

            if "remittance_id" in item or ("check_number" in item and "line_adjudications" in item):
                try:
                    r = Remittance835(
                        claim_id=str(item.get("claim_id")),
                        remittance_id=str(item.get("remittance_id", f"REM-{item.get('claim_id')}")),
                        check_number=str(item.get("check_number", "CHK-ELECTRONIC")),
                        adjudication_date=str(item.get("adjudication_date", datetime.utcnow().strftime("%Y-%m-%d"))),
                        total_billed=float(item.get("total_billed", 0.0)),
                        total_paid=float(item.get("total_paid", 0.0)),
                        patient_responsibility=float(item.get("patient_responsibility", 0.0)),
                        line_adjudications=[LineAdjudication(**la) for la in item.get("line_adjudications", [])],
                        primary_carc=str(item.get("primary_carc", "97")),
                        primary_reason=str(item.get("primary_reason", "Service bundled under NCCI PTP edits"))
                    )
                    result.remittances.append(r)
                except Exception as e:
                    result.errors.append(f"Failed to parse remittance JSON: {e}")

    def _parse_837_segments(self, segments: List[str], result: EdiParseResult):
        current_claim_id = None
        patient_name = "Patient"
        dob = "1975-01-01"
        patient_id = "PAT-UNKNOWN"
        payer_name = "Medicare / Commercial Payer"
        payer_id = "PAYER-01"
        billing_npi = "1023948512"
        rendering_npi = "1942083411"
        dos = datetime.utcnow().strftime("%Y-%m-%d")
        diagnoses: List[str] = []
        line_items: List[ClaimLineItem] = []
        total_billed = 0.0
        pos = "11"
        clinical_notes = []

        line_counter = 1

        for seg_str in segments:
            parts = seg_str.split("*")
            tag = parts[0].upper()

            # Billing Provider
            if tag == "NM1" and len(parts) > 1 and parts[1] == "85":
                if len(parts) > 3:
                    pass
                if len(parts) > 9 and parts[9]:
                    billing_npi = parts[9]

            # Subscriber / Patient Name
            elif tag == "NM1" and len(parts) > 1 and parts[1] in ("IL", "QC"):
                lname = parts[3] if len(parts) > 3 else ""
                fname = parts[4] if len(parts) > 4 else ""
                patient_name = f"{fname} {lname}".strip() or "Patient"
                if len(parts) > 9 and parts[9]:
                    patient_id = parts[9]

            # Date of Birth
            elif tag == "DMG" and len(parts) > 2:
                raw_dob = parts[2]
                if len(raw_dob) == 8:
                    dob = f"{raw_dob[0:4]}-{raw_dob[4:6]}-{raw_dob[6:8]}"

            # Payer Name
            elif tag == "NM1" and len(parts) > 1 and parts[1] == "PR":
                payer_name = parts[3] if len(parts) > 3 else "Payer"
                payer_id = parts[9] if len(parts) > 9 else "PAYER-01"

            # Claim Header (CLM)
            elif tag == "CLM" and len(parts) > 2:
                # If we were already tracking a claim, flush it
                if current_claim_id and line_items:
                    result.claims.append(Claim837(
                        claim_id=current_claim_id,
                        patient_id=patient_id,
                        patient_name=patient_name,
                        dob=dob,
                        payer_id=payer_id,
                        payer_name=payer_name,
                        date_of_service=dos,
                        rendering_npi=rendering_npi,
                        billing_npi=billing_npi,
                        diagnosis_codes=diagnoses,
                        line_items=line_items,
                        total_billed=total_billed or sum(li.billed_amount for li in line_items),
                        clinical_notes="\n".join(clinical_notes),
                        status="PENDING"
                    ))
                    line_items = []
                    diagnoses = []
                    clinical_notes = []
                    line_counter = 1

                current_claim_id = parts[1]
                try:
                    total_billed = float(parts[2])
                except ValueError:
                    total_billed = 0.0

                if len(parts) > 5 and parts[5]:
                    pos_parts = parts[5].split(":")
                    pos = pos_parts[0] if pos_parts else "11"

            # Date of Service (DTP*472*D8*YYYYMMDD)
            elif tag == "DTP" and len(parts) > 3 and parts[1] == "472":
                raw_dos = parts[3]
                if len(raw_dos) >= 8:
                    dos = f"{raw_dos[0:4]}-{raw_dos[4:6]}-{raw_dos[6:8]}"

            # Diagnosis Codes (HI)
            elif tag == "HI" and len(parts) > 1:
                for el in parts[1:]:
                    if not el:
                        continue
                    code_parts = el.split(":")
                    if len(code_parts) >= 2:
                        dx_code = code_parts[1].strip()
                        # Format ICD-10 (e.g., C44319 -> C44.319)
                        if "." not in dx_code and len(dx_code) > 3:
                            formatted_dx = f"{dx_code[:3]}.{dx_code[3:]}"
                        else:
                            formatted_dx = dx_code
                        if formatted_dx not in diagnoses:
                            diagnoses.append(formatted_dx)

            # Clinical Note (NTE)
            elif tag == "NTE" and len(parts) > 2:
                clinical_notes.append(parts[2].strip())

            # Professional Service Line (SV1)
            elif tag == "SV1" and len(parts) > 2:
                comp = parts[1].split(":")
                cpt = comp[1] if len(comp) > 1 else comp[0]
                modifiers = [m for m in comp[2:] if m]
                try:
                    line_billed = float(parts[2])
                except ValueError:
                    line_billed = 0.0

                units = 1
                if len(parts) > 4:
                    try:
                        units = int(float(parts[4]))
                    except (ValueError, TypeError):
                        units = 1

                desc = self._lookup_cpt_desc(cpt)
                line_items.append(ClaimLineItem(
                    line_number=line_counter,
                    cpt_code=cpt,
                    description=desc,
                    modifiers=modifiers,
                    units=units,
                    billed_amount=line_billed,
                    place_of_service=pos,
                    rendering_npi=rendering_npi,
                    diagnosis_pointers=["1"]
                ))
                line_counter += 1

        # Flush final claim
        if current_claim_id and line_items:
            result.claims.append(Claim837(
                claim_id=current_claim_id,
                patient_id=patient_id,
                patient_name=patient_name,
                dob=dob,
                payer_id=payer_id,
                payer_name=payer_name,
                date_of_service=dos,
                rendering_npi=rendering_npi,
                billing_npi=billing_npi,
                diagnosis_codes=diagnoses or ["I10"],
                line_items=line_items,
                total_billed=total_billed or sum(li.billed_amount for li in line_items),
                clinical_notes="\n".join(clinical_notes),
                status="PENDING"
            ))

    def _parse_835_segments(self, segments: List[str], result: EdiParseResult):
        check_number = "CHK-EFT"
        adjudication_date = datetime.utcnow().strftime("%Y-%m-%d")
        payer_id = "PAYER-01"

        current_claim_id = None
        total_billed = 0.0
        total_paid = 0.0
        patient_resp = 0.0
        line_adjudications: List[LineAdjudication] = []
        carc_codes: List[str] = []
        rarc_codes: List[str] = []
        primary_reason = "Service bundled under NCCI PTP edits"
        line_counter = 1

        for seg_str in segments:
            parts = seg_str.split("*")
            tag = parts[0].upper()

            # Financial Information (BPR)
            if tag == "BPR" and len(parts) > 16:
                raw_date = parts[16]
                if len(raw_date) == 8:
                    adjudication_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

            # Trace Number (TRN)
            elif tag == "TRN" and len(parts) > 2:
                check_number = parts[2]

            # Claim Payment Information (CLP)
            elif tag == "CLP" and len(parts) > 5:
                # Flush previous remittance
                if current_claim_id:
                    result.remittances.append(Remittance835(
                        claim_id=current_claim_id,
                        remittance_id=f"REM-{current_claim_id}",
                        check_number=check_number,
                        adjudication_date=adjudication_date,
                        total_billed=total_billed,
                        total_paid=total_paid,
                        patient_responsibility=patient_resp,
                        line_adjudications=line_adjudications,
                        primary_carc=carc_codes[0] if carc_codes else "97",
                        primary_reason=primary_reason
                    ))
                    line_adjudications = []
                    carc_codes = []
                    rarc_codes = []
                    line_counter = 1

                current_claim_id = parts[1]
                try:
                    total_billed = float(parts[3])
                except ValueError:
                    total_billed = 0.0
                try:
                    total_paid = float(parts[4])
                except ValueError:
                    total_paid = 0.0
                try:
                    patient_resp = float(parts[5])
                except (ValueError, IndexError):
                    patient_resp = 0.0

            # Claim Adjustment Segment (CAS)
            elif tag == "CAS" and len(parts) > 2:
                # CAS*CO*97*165.00*1
                reason = parts[2]
                if reason not in carc_codes:
                    carc_codes.append(reason)
                if reason == "97":
                    primary_reason = "CARC 97: The benefit for this service is included in the payment/allowance for another service."
                elif reason == "16":
                    primary_reason = "CARC 16: Claim/service lacks information or has a submission/billing error."

            # Service Line Adjudication (SVC)
            elif tag == "SVC" and len(parts) > 3:
                comp = parts[1].split(":")
                cpt = comp[1] if len(comp) > 1 else comp[0]
                try:
                    line_billed = float(parts[2])
                except ValueError:
                    line_billed = 0.0
                try:
                    line_paid = float(parts[3])
                except ValueError:
                    line_paid = 0.0

                line_adjudications.append(LineAdjudication(
                    line_number=line_counter,
                    cpt_code=cpt,
                    billed_amount=line_billed,
                    allowed_amount=line_paid,
                    paid_amount=line_paid,
                    carc_codes=list(carc_codes),
                    rarc_codes=list(rarc_codes),
                    denial_reason=primary_reason if line_paid == 0.0 else ""
                ))
                line_counter += 1

            # Remittance Advice Remark Code (LQ)
            elif tag == "LQ" and len(parts) > 2:
                rarc = parts[2].strip()
                if rarc not in rarc_codes:
                    rarc_codes.append(rarc)

        def _pick_primary_carc(codes: List[str]) -> str:
            for priority in ["97", "16", "50", "18", "197", "22", "24"]:
                if priority in codes:
                    return priority
            return codes[0] if codes else "97"

        # Flush final remittance
        if current_claim_id:
            result.remittances.append(Remittance835(
                claim_id=current_claim_id,
                remittance_id=f"REM-{current_claim_id}",
                check_number=check_number,
                adjudication_date=adjudication_date,
                total_billed=total_billed,
                total_paid=total_paid,
                patient_responsibility=patient_resp,
                line_adjudications=line_adjudications,
                primary_carc=_pick_primary_carc(carc_codes),
                primary_reason=primary_reason
            ))

    def _parse_csv_payload(self, content: str, result: EdiParseResult):
        import csv
        import io

        f = io.StringIO(content.strip())
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return

        norm_map = {re.sub(r'[^a-zA-Z0-9]', '', k).lower(): k for k in reader.fieldnames if k}

        def get_val(row: Dict[str, Any], *candidates: str, default: str = "") -> str:
            for cand in candidates:
                clean_cand = re.sub(r'[^a-zA-Z0-9]', '', cand).lower()
                if clean_cand in norm_map:
                    v = row.get(norm_map[clean_cand])
                    if v is not None and str(v).strip():
                        return str(v).strip()
            return default

        claims_data: Dict[str, Dict[str, Any]] = {}

        for row in reader:
            claim_id = get_val(row, "claimId", "claim_id", "claimIdentifier", "claimNumber", "claim")
            if not claim_id:
                continue

            if claim_id not in claims_data:
                patient_name = get_val(row, "patientName", "patient_name", "patient", default="Unknown Patient")
                patient_id = get_val(row, "patientId", "patient_id", "policyNumber", "chartNumber", "mrn", default=f"PAT-{claim_id}")
                dob = get_val(row, "dob", "dateOfBirth", "birthDate", default="1975-01-01")
                dos = get_val(row, "dos", "dateOfService", "serviceDate", default=datetime.utcnow().strftime("%Y-%m-%d"))
                payer_name = get_val(row, "payerName", "payer_name", "insurance", "payer", default="Commercial Payer")
                payer_id = get_val(row, "payerId", "payer_id", default="PAYER-01")
                rendering_npi = get_val(row, "renderingNpi", "rendering_npi", "npi", default="1999999999")
                billing_npi = get_val(row, "billingNpi", "billing_npi", default="1000000000")
                notes = get_val(row, "clinicalNotes", "encounterNote", "chartNote", "operativeNote", "clinicalDocumentation", "notes", default="")

                claims_data[claim_id] = {
                    "claim_id": claim_id,
                    "patient_name": patient_name,
                    "patient_id": patient_id,
                    "dob": dob,
                    "dos": dos,
                    "payer_name": payer_name,
                    "payer_id": payer_id,
                    "rendering_npi": rendering_npi,
                    "billing_npi": billing_npi,
                    "notes": notes,
                    "diagnoses": set(),
                    "lines": [],
                    "total_billed": 0.0,
                    "total_paid": 0.0,
                    "carc_codes": set(),
                    "denial_reason": ""
                }

            entry = claims_data[claim_id]

            # Diagnoses
            raw_diag = get_val(row, "diagnosisCodes", "diagnosis_codes", "icd10", "dxCodes", "diag1", "diagnosis", "diagnoses")
            if raw_diag:
                for d in re.split(r'[,;|\s]+', raw_diag):
                    d = d.strip()
                    if d:
                        entry["diagnoses"].add(d)

            # Procedure CPT & Modifiers
            raw_cpt = get_val(row, "cptCode", "cpt_code", "cpt", "procedureCode", "procedure", "hcpcs")
            raw_mods = get_val(row, "modifier", "modifiers", "mod")
            modifiers = [m.strip() for m in re.split(r'[,;|\s]+', raw_mods) if m.strip()] if raw_mods else []

            # Line amounts
            billed_str = get_val(row, "lineBilledAmount", "chargeAmount", "billedAmount", "arClaimBalance", "totalBilled", default="0.0")
            try:
                line_billed = float(re.sub(r'[^0-9.]', '', billed_str)) if billed_str else 0.0
            except ValueError:
                line_billed = 0.0

            paid_str = get_val(row, "linePaidAmount", "paidAmount", "allowedAmount", "totalPaid", default="0.0")
            try:
                line_paid = float(re.sub(r'[^0-9.]', '', paid_str)) if paid_str else 0.0
            except ValueError:
                line_paid = 0.0

            carc_raw = get_val(row, "carcCode", "carc", "denialCode", "adjustmentReasonCode", "reasonCode", default="97")
            if carc_raw:
                for item in re.split(r'[,;|]+', carc_raw):
                    item = item.strip()
                    clean_code = re.sub(r'^(CO|PR|OA|PI)-', '', item, flags=re.IGNORECASE).strip()
                    if clean_code:
                        entry["carc_codes"].add(clean_code)

            denial_desc = get_val(row, "denialDescription", "denialReason", "primaryReason", "adjustmentReasonDescription", "captured277Description")
            if denial_desc and not entry["denial_reason"]:
                entry["denial_reason"] = denial_desc

            if raw_cpt:
                cpt_list = [c.strip() for c in re.split(r'[,;|\s]+', raw_cpt) if c.strip()]
                for cpt in cpt_list:
                    line_idx = len(entry["lines"]) + 1
                    entry["lines"].append(ClaimLineItem(
                        line_number=line_idx,
                        cpt_code=cpt,
                        description=self._lookup_cpt_desc(cpt),
                        modifiers=modifiers,
                        units=1,
                        billed_amount=line_billed if len(cpt_list) == 1 else (line_billed / len(cpt_list)),
                        place_of_service="11",
                        rendering_npi=entry["rendering_npi"],
                        diagnosis_pointers=["1"]
                    ))
            entry["total_billed"] += line_billed
            entry["total_paid"] += line_paid

        for cid, data in claims_data.items():
            if not data["lines"]:
                continue

            diag_list = list(data["diagnoses"]) if data["diagnoses"] else ["M54.5", "I10"]
            primary_carc = "97"
            if data["carc_codes"]:
                # Priority order for primary denial detection
                for p_carc in ["97", "236", "4", "59", "16", "50", "29", "197", "45"]:
                    if p_carc in data["carc_codes"]:
                        primary_carc = p_carc
                        break
                else:
                    primary_carc = list(data["carc_codes"])[0]

            reason = data["denial_reason"] or f"CARC {primary_carc}: The benefit for this service is included in the payment/allowance for another service."

            claim = Claim837(
                claim_id=cid,
                patient_id=data["patient_id"],
                patient_name=data["patient_name"],
                dob=data["dob"],
                payer_id=data["payer_id"],
                payer_name=data["payer_name"],
                date_of_service=data["dos"],
                rendering_npi=data["rendering_npi"],
                billing_npi=data["billing_npi"],
                diagnosis_codes=diag_list,
                line_items=data["lines"],
                total_billed=data["total_billed"] or sum(l.billed_amount for l in data["lines"]),
                clinical_notes=data["notes"],
                status="PENDING"
            )
            result.claims.append(claim)

            is_claim_level_denial = primary_carc in ["29", "16", "50", "197", "22", "18", "45", "96", "4", "236", "NSA"]
            is_single_line = len(data["lines"]) == 1

            line_adjs = []
            for l in data["lines"]:
                is_denied_line = is_single_line or is_claim_level_denial or (l.line_number > 1)
                line_carcs = [primary_carc] if (is_denied_line and primary_carc) else []
                line_rarcs = ["N390"] if (is_denied_line and primary_carc) else []
                line_reason = reason if is_denied_line else ""
                paid_amt = 0.0 if is_denied_line else l.billed_amount
                allowed_amt = 0.0 if is_denied_line else l.billed_amount

                line_adjs.append(
                    LineAdjudication(
                        line_number=l.line_number,
                        cpt_code=l.cpt_code,
                        billed_amount=l.billed_amount,
                        allowed_amount=allowed_amt,
                        paid_amount=paid_amt,
                        carc_codes=line_carcs,
                        rarc_codes=line_rarcs,
                        denial_reason=line_reason
                    )
                )

            remit = Remittance835(
                claim_id=cid,
                remittance_id=f"REM-{cid}",
                check_number="CHK-PM-IMPORT",
                adjudication_date=data["dos"],
                total_billed=claim.total_billed,
                total_paid=data["total_paid"],
                patient_responsibility=0.0,
                line_adjudications=line_adjs,
                primary_carc=primary_carc,
                primary_reason=reason
            )
            result.remittances.append(remit)

    def _lookup_cpt_desc(self, cpt: str) -> str:
        descriptions = {
            "99214": "Office/outpatient visit est patient moderate mdm 30-39 min",
            "99213": "Office visit est patient low-moderate mdm",
            "11102": "Tangential biopsy of skin single lesion",
            "17000": "Destruction premalignant lesion actinic keratosis first",
            "45385": "Colonoscopy flexible with removal of tumor polyp by snare technique",
            "45380": "Colonoscopy flexible with single or multiple biopsy",
            "29881": "Arthroscopy knee surgical with meniscectomy medial or lateral",
            "29877": "Arthroscopy knee surgical debridement/shaving articular cartilage",
            "17311": "Mohs micrographic technique first stage head neck",
            "12032": "Repair intermediate wounds scalp axillae trunk 2.6 cm to 7.5 cm",
            "22614": "Arthrodesis posterior lumbar each additional spine segment",
            "22612": "Arthrodesis posterior or posterolateral lumbar single level",
            "63048": "Laminectomy facetectomy and foraminotomy additional segment",
            "63046": "Laminectomy with facetectomy/foraminotomy single thoracic/lumbar",
            "20240": "Biopsy of bone superficial",
            "14302": "Adjacent tissue transfer or rearrangement defect 30.1 to 60.0 sq cm",
            "64635": "Destruction of neurolytic agent lumbar/sacral facet joint nerve",
            "29999": "Unlisted procedure arthroscopy",
            "27299": "Unlisted procedure pelvis or hip joint",
            "64722": "Decompression of nerve hand/wrist or other site",
            "19364": "Breast reconstruction with free flap",
            "19357": "Breast reconstruction with tissue expander",
            "Q4250": "Amnioamp-mp per square centimeter"
        }
        return descriptions.get(cpt, f"Procedure CPT {cpt}")

edi_parser = EdiX12Parser()
