#!/usr/bin/env python3
"""
Databricks Model Context Protocol (MCP) Server
Allows external clients, LLMs, and RCM agents to connect to Databricks Lakehouse
to query claims, inspect Delta tables/Volumes, trigger JEV AI adjudication,
and sync remediated outcomes back to Unity Catalog Gold tables.
"""

import sys
import os
import json
import logging
from typing import Dict, Any, List

# Ensure parent directory is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.adapters.databricks_adapter import DatabricksAdapter
from app.adapters.neon_db import DatabaseAdapter
from app.services.ingestion_service import IngestionService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", stream=sys.stderr)
logger = logging.getLogger("databricks-mcp-server")

db_adapter = DatabaseAdapter()
databricks_adapter = DatabricksAdapter()
ingestion_service = IngestionService()

TOOLS_DEFINITION = [
    {
        "name": "databricks_sql_query",
        "description": "Execute a SQL query against Databricks SQL Warehouse or Unity Catalog claims tables.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL statement (e.g. 'SELECT * FROM main.claims_rcm.claims_837_bronze LIMIT 10')"
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Maximum number of rows to return (default: 100)",
                    "default": 100
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "databricks_list_claims",
        "description": "List 837 claims stored in Databricks Unity Catalog Bronze table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of claims to retrieve (default: 50)",
                    "default": 50
                },
                "status": {
                    "type": "string",
                    "description": "Filter by claim status (e.g. 'DENIED', 'REMEDIATED_AUTO_APPEND', 'HITL_REVIEW')"
                }
            }
        }
    },
    {
        "name": "databricks_get_claim_details",
        "description": "Retrieve comprehensive details for a specific claim including 837 claim, 835 remittance, and JEV AI adjudication.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "The unique claim identifier (e.g. 'CLM-10842-01')"
                }
            },
            "required": ["claim_id"]
        }
    },
    {
        "name": "databricks_trigger_remediation",
        "description": "Execute the autonomous JEV AI multi-MCP adjudication and modifier recommendation pipeline for a claim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "The claim identifier to remediate"
                }
            },
            "required": ["claim_id"]
        }
    },
    {
        "name": "databricks_sync_remediated_claims",
        "description": "Synchronize remediated claims, appeal packages, and modifier determinations into Databricks Gold tables.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": "Optional claim ID to sync. If omitted, syncs all available remediated claims."
                }
            }
        }
    },
    {
        "name": "databricks_volume_list_edi",
        "description": "List raw 837 / 835 EDI files currently available in Databricks Unity Catalog Volumes or ingest dropzones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "volume_path": {
                    "type": "string",
                    "description": "Volume directory path (default: '/Volumes/main/claims_rcm/raw_edi/')"
                }
            }
        }
    },
    {
        "name": "databricks_ingest_edi_file",
        "description": "Ingest an EDI / X12 file from a Databricks Volume or local dropzone into the JEV AI Claim Engine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Full path to the EDI / X12 file to ingest"
                },
                "auto_remediate": {
                    "type": "boolean",
                    "description": "Whether to automatically trigger JEV AI remediation after ingestion (default: false)",
                    "default": False
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "databricks_health_check",
        "description": "Check connectivity status and latency to the Databricks Lakehouse workspace and SQL warehouse.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

def handle_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the requested tool and return a JSON-serializable dictionary."""
    if name == "databricks_health_check":
        return databricks_adapter.test_connection()

    elif name == "databricks_sql_query":
        query = args.get("query", "")
        max_rows = args.get("max_rows", 100)
        return databricks_adapter.execute_sql(query, max_rows=max_rows)

    elif name == "databricks_list_claims":
        limit = args.get("limit", 50)
        status = args.get("status")
        claims = databricks_adapter.list_claims(limit=limit, status=status)
        return {
            "count": len(claims),
            "claims": claims
        }

    elif name == "databricks_get_claim_details":
        claim_id = args.get("claim_id")
        details = databricks_adapter.get_claim_details(claim_id)
        if not details:
            return {"error": f"Claim {claim_id} not found."}
        return details

    elif name == "databricks_trigger_remediation":
        claim_id = args.get("claim_id")
        try:
            from app.graph.workflow import remediation_graph
            initial_state = {
                "claim_id": claim_id,
                "audit_trail": []
            }
            final_state = remediation_graph.invoke(initial_state)
            outcome = db_adapter.get_adjudication(claim_id)
            return {
                "success": True,
                "claim_id": claim_id,
                "outcome": outcome.model_dump() if outcome else final_state.get("adjudication")
            }
        except Exception as e:
            logger.exception("Error executing remediation graph")
            return {"success": False, "error": str(e), "claim_id": claim_id}

    elif name == "databricks_sync_remediated_claims":
        claim_id = args.get("claim_id")
        if claim_id:
            outcome = db_adapter.get_adjudication(claim_id)
            if not outcome:
                return {"error": f"No adjudication found for claim {claim_id}."}
            return databricks_adapter.sync_remediated_claim(outcome)
        else:
            return databricks_adapter.sync_all_remediated()

    elif name == "databricks_volume_list_edi":
        volume_path = args.get("volume_path")
        files = databricks_adapter.list_volume_edi_files(volume_path)
        return {
            "volume": volume_path or f"/Volumes/{databricks_adapter.catalog}/{databricks_adapter.schema}/raw_edi/",
            "total_files": len(files),
            "files": files
        }

    elif name == "databricks_ingest_edi_file":
        file_path = args.get("file_path")
        auto_remediate = args.get("auto_remediate", False)
        
        # Resolve path
        p = os.path.expanduser(file_path)
        if not os.path.isabs(p):
            p = os.path.abspath(p)
            
        if not os.path.exists(p):
            return {"error": f"File {p} does not exist."}

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        filename = os.path.basename(p)
        result = ingestion_service.ingest_content(content, filename=filename, auto_remediate=auto_remediate)
        return result

    else:
        return {"error": f"Unknown tool: {name}"}


def main():
    """Stdio JSON-RPC loop for Model Context Protocol."""
    logger.info("Databricks MCP Server starting on stdio...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as err:
            logger.error(f"Invalid JSON received: {err}")
            continue

        req_id = req.get("id")
        method = req.get("method")

        # Handshake / initialize
        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "databricks-mcp",
                        "version": "1.0.0"
                    },
                    "capabilities": {
                        "tools": {}
                    }
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            # Client acknowledge, no response needed
            pass

        elif method == "ping":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {}
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOLS_DEFINITION
                }
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            
            try:
                data = handle_tool_call(name, args)
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(data, indent=2)
                            }
                        ]
                    }
                }
            except Exception as e:
                logger.exception(f"Error handling tool call {name}")
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"error": str(e)})
                            }
                        ]
                    }
                }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        else:
            if req_id is not None:
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method {method} not found"
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()

if __name__ == "__main__":
    main()
