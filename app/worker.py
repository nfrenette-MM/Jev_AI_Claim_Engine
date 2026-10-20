import os
import asyncio
from typing import Dict, Any
from app.adapters.neon_db import db
from app.graph.workflow import remediation_graph

async def remediate_claim_task(ctx: Dict[Any, Any], claim_id: str) -> Dict[str, Any]:
    """
    ARQ Background Worker Task:
    Processes autonomous remediation for a specific 837 claim using LangGraph and Jev AI.
    """
    print(f"[Worker] Processing claim remediation for {claim_id}...")
    initial_state = {
        "claim_id": claim_id,
        "claim": None,
        "remittance": None,
        "ncci_edit": None,
        "clinical_evidence": None,
        "jev_noul": None,
        "jev_score": None,
        "modifier_applied": None,
        "decision": None,
        "human_approved": None,
        "appeal_letter": None,
        "audit_trail": [],
        "resubmission_ready": False
    }
    result = remediation_graph.invoke(initial_state)
    print(f"[Worker] Claim {claim_id} finished with decision: {result.get('decision')}")
    return result

class WorkerSettings:
    """ARQ Worker configuration for Redis queue."""
    functions = [remediate_claim_task]
    redis_settings = os.getenv("REDIS_URL", "redis://localhost:6379")

if __name__ == "__main__":
    print("ARQ Worker initialized with functions:", [f.__name__ for f in WorkerSettings.functions])
