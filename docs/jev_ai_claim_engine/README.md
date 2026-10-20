# JEV AI Claim Engine Documentation

Welcome to the **JEV AI Claim Engine** documentation directory.

## Documents

- [Adjudication & Remediation Architecture](file:///Users/nicholasfrenette/.gemini/antigravity-ide/scratch/JEV_AI_CLAIM_ENGINE/docs/jev_ai_claim_engine/ADJUDICATION_REMEDIATION_ARCHITECTURE.md): Comprehensive specification detailing:
  1. **Where Remediation is Derived From**: Mathematical decision calculus, `JevNoul` & `JevScore` primitives, 0.85 safety gate, and modifier logic.
  2. **Where Evidence is Sourced**: EDI 837/835, Neon DB NCCI PTP tables, `icd10-codes` MCP, `cms-coverage` MCP, and `local-fhir` MCP stdio server.
  3. **Where and How It is Mapped**: LangGraph 6-step state machine execution, line item mutations, and appeal letter generation.
  4. **Database Persistence**: Full relational schemas for `claims_837`, `adjudications`, `remittances_835`, and `ncci_ptp_edits`.
  5. **Verified Case Studies**: Real-world claim adjudication results and recovered balances.

## Key Code References
- Decision Engine: [app/adapters/jev_ai.py](file:///Users/nicholasfrenette/.gemini/antigravity-ide/scratch/JEV_AI_CLAIM_ENGINE/app/adapters/jev_ai.py)
- LangGraph Workflow: [app/graph/workflow.py](file:///Users/nicholasfrenette/.gemini/antigravity-ide/scratch/JEV_AI_CLAIM_ENGINE/app/graph/workflow.py)
- Database Adapter: [app/adapters/neon_db.py](file:///Users/nicholasfrenette/.gemini/antigravity-ide/scratch/JEV_AI_CLAIM_ENGINE/app/adapters/neon_db.py)
- FHIR MCP Server: [servers/fhir/dist/index.js](file:///Users/nicholasfrenette/.gemini/antigravity-ide/scratch/JEV_AI_CLAIM_ENGINE/servers/fhir/dist/index.js)
