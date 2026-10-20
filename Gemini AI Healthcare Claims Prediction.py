import os
from pathlib import Path

def init_antigravity_workspace():
    root = Path.cwd()
    print(f"🚀 Initializing Healthcare Claims Agent in Antigravity workspace: {root}")

    # 1. Directory Structure
    dirs = [
        root / ".agents",
        root / ".agents" / "skills",
        root / "app",
        root / "app" / "adapters",
        root / "app" / "graph",
        root / "scripts",
        root / "data",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # 2. Antigravity MCP Server Configuration (.agents/mcp_config.json)
    mcp_config_content = """{
  "mcpServers": {
    "cms-coverage": {
      "serverUrl": "https://hcls.mcp.claude.com/cms_coverage/mcp"
    },
    "icd10-codes": {
      "serverUrl": "https://hcls.mcp.claude.com/icd10_codes/mcp"
    },
    "local-fhir": {
      "command": "node",
      "args": ["./servers/fhir/dist/index.js"],
      "env": {
        "FHIR_BASE_URL": "${FHIR_SERVER_URL}",
        "FHIR_AUTH_TOKEN": "${FHIR_TOKEN}"
      }
    }
  }
}
"""
    (root / ".agents" / "mcp_config.json").write_text(mcp_config_content.strip())

    # 3. Antigravity Agent Policies & Instructions (.agents/agent_config.json)
    agent_config_content = """{
  "name": "Healthcare Claims Remediation Agent",
  "version": "2.0",
  "system_instructions": "You are an autonomous RCM Claims Remediation Agent. Your job is to inspect 837 claims and 835 remittances, verify NCCI PTP edits, evaluate clinical necessity using MCP tools, validate hypotheses via TypeSafe Jev AI, and persist state in Neon Postgres.",
  "policies": [
    "allow(mcp/*)",
    "allow(view_file)",
    "allow(run_command:pytest*)",
    "ask_user(run_command:alembic*)"
  ]
}
"""
    (root / ".agents" / "agent_config.json").write_text(agent_config_content.strip())

    # 4. Mounted HCLS Billing Rules Skill (.agents/skills/claims-billing-rules.md)
    claims_skill_content = """# Skill: Claims Billing Rules & NCCI Validation

## Context
Use this skill when analyzing claim rejections, NCCI procedure unbundling, or CARC 97 / 16 / 50 reason codes.

## Step-by-Step Adjudication Protocol
1. **NCCI Table Inspection:**
   - Query `ncci_ptp_edits` in Neon Postgres for CPT code pairings.
   - Indicator `0`: Barred under all circumstances. Flag for contractual write-off.
   - Indicator `1`: Permissible ONLY if documentation proves an independent anatomical site, separate encounter, or distinct surgical session.
   - Indicator `9`: Edit not applicable.

2. **Modifier Selection:**
   - E/M with Minor Surgery: Evaluate Modifier `-25`.
   - Distinct Anatomical Site: Evaluate Modifier `-59` or `-XS`.
   - Distinct Encounter / Session: Evaluate Modifier `-XE`.

3. **Clinical Ground Truth Verification:**
   - Use the `local-fhir` MCP server to extract operative notes and progress reports.
   - Extract the verbatim clinical sentence proving distinct service.

4. **Jev AI Gate:**
   - Query Jev `Noul` and `Score` primitives. If overturn confidence >= 0.85, auto-append modifier. Otherwise, trigger LangGraph `interrupt()`.
"""
    (root / ".agents" / "skills" / "claims-billing-rules.md").write_text(claims_skill_content.strip())

    # 5. Environment Variables Template (.env)
    env_content = """# Neon Serverless Postgres (Use Pooled endpoint)
DATABASE_URL=postgresql://neondb_owner:YOUR_PW@ep-your-branch-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require

# Google Gemini / Antigravity LLM
GEMINI_API_KEY=your_gemini_api_key

# TypeSafe Jev AI Decision Engine
TYPESAFE_API_KEY=your_jev_api_key

# Redis (Railway private network)
REDIS_URL=redis://localhost:6379

# MCP FHIR Server Target
FHIR_SERVER_URL=https://fhir.example-ehr.com/r4
FHIR_TOKEN=your_fhir_bearer_token
"""
    (root / ".env").write_text(env_content.strip())

    # 6. Python Project Requirements (requirements.txt)
    reqs_content = """fastapi>=0.115.0
uvicorn>=0.30.0
pydantic>=2.8.0
psycopg[binary,pool]>=3.2.0
langgraph>=0.2.20
langgraph-checkpoint-postgres>=2.0.0
google-genai>=0.1.0
mcp>=1.0.0
arq>=0.26.0
requests>=2.32.0
pandas>=2.2.0
"""
    (root / "requirements.txt").write_text(reqs_content.strip())

    # 7. Railway Deployment Procfile (Procfile)
    procfile_content = """web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: python -m arq app.worker.WorkerSettings
"""
    (root / "Procfile").write_text(procfile_content.strip())

    print("✅ Project files generated successfully!")
    print("\nNext steps in Google Antigravity IDE:")
    print("1. Launch Antigravity IDE.")
    print("2. Click 'File' > 'Open Folder...' and select this root directory.")
    print("3. Accept the Workspace Trust prompt to enable MCP and Agent execution.")
    print("4. Press Cmd+, (or Ctrl+,), verify your MCP servers under Customizations.")
    print("5. Run `pip install -r requirements.txt` in the Antigravity integrated terminal.")

if __name__ == "__main__":
    init_antigravity_workspace()