---
name: claims-billing-rules
description: Autonomous RCM Claims Remediation and NCCI PTP validation protocol using Jev AI decision engine, clinical evidence extraction, and modifier determination.
---

# Skill: Claims Billing Rules & NCCI Validation

## Context
Use this skill when analyzing claim rejections, NCCI procedure unbundling, or CARC 97 / 16 / 50 reason codes.

## Step-by-Step Adjudication Protocol
1. **NCCI Table Inspection:**
   - Query `ncci_ptp_edits` in Neon Postgres for CPT code pairings.
   - Indicator `0`: Barred under all circumstances. Flag for contractual write-off.
   - Indicator `1`: Permissible ONLY if documentation proves an independent anatomical site, separate encounter, or distinct surgical session.
   - Indicator `9`: Edit not applicable.

2. **Modifier Selection:**
   - E/M with Minor Surgery: Evaluate Modifier `-25` (Significant, separately identifiable E/M service by same physician on same day).
   - Distinct Anatomical Site: Evaluate Modifier `-59` or `-XS` (Separate structure/organ).
   - Distinct Encounter / Session: Evaluate Modifier `-XE` (Separate encounter on same date of service).
   - Distinct Practitioner: Evaluate Modifier `-XP`.
   - Unusual Non-Overlapping Service: Evaluate Modifier `-XU`.

3. **Clinical Ground Truth Verification:**
   - Use the `local-fhir` MCP server to extract operative notes and progress reports.
   - Extract the verbatim clinical sentence proving distinct service.

4. **Jev AI Gate:**
   - Query Jev `Noul` and `Score` primitives. If overturn confidence >= 0.85, auto-append modifier. Otherwise, trigger LangGraph `interrupt()` for human-in-the-loop review.
