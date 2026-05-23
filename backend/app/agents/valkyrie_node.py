"""
valkyrie_node.py
----------------
LangGraph node: validate SAGE SQL results via VALKYRIE, run correction loop (max 2 attempts).

Flow per attempt:
  1. POST validated sql_results → VALKYRIE :8004/sql/validate
  2. Collect failed intents
  3. For each failed intent → POST → SAGE :8003/sql/correct
  4. Repeat validation with corrected SQLs (up to MAX_CORRECTIONS rounds)
  5. Package synthesizer_context from final VALKYRIE response
"""

import logging
import httpx

logger = logging.getLogger("valkyrie_node")

VALKYRIE_URL   = "http://localhost:8004"
SAGE_URL       = "http://localhost:8003"
MAX_CORRECTIONS = 2
TIMEOUT         = 120.0


async def valkyrie_node(state: dict) -> dict:
    sql_result      = state.get("sql_result")
    intent_result   = state.get("intent_result")
    security_profile = state.get("security_profile", {})
    prompt          = state.get("prompt", "")
    request_id      = state.get("metadata", {}).get("request_id", "")

    # Skip if no SQL was generated
    if not sql_result or not intent_result:
        return _skip()

    sql_results = sql_result.get("sql_results", [])
    intents     = intent_result.get("intents", [])

    if not any(r.get("status") == "success" for r in sql_results):
        return _skip()

    intent_map   = {i["intent_id"]: i for i in intents}
    current_sqls = sql_results  # mutable across correction loop
    val_response = None

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for attempt in range(MAX_CORRECTIONS + 1):
                logger.info(
                    "VALKYRIE attempt %d/%d request_id=%s",
                    attempt + 1, MAX_CORRECTIONS + 1, request_id,
                )

                # ── Validate ──────────────────────────────────────────────────
                val_payload = {
                    "request_id":       request_id,
                    "prompt":           prompt,
                    "security_profile": security_profile,
                    "intents":          intents,
                    "sql_results":      current_sqls,
                }
                resp = await client.post(f"{VALKYRIE_URL}/sql/validate", json=val_payload)
                resp.raise_for_status()
                val_response = resp.json()

                failed = [
                    r for r in val_response.get("validated_results", [])
                    if r.get("status") == "fail"
                ]

                if not failed or attempt == MAX_CORRECTIONS:
                    break  # all pass, or no more correction attempts

                # ── Correct failed SQLs via SAGE ───────────────────────────────
                sql_map = {r["intent_id"]: r for r in current_sqls}

                for failed_result in failed:
                    intent_id = failed_result["intent_id"]
                    intent    = intent_map.get(intent_id, {})
                    original  = sql_map.get(intent_id, {})

                    correct_payload = {
                        "request_id":            f"{request_id}_corr{attempt + 1}_i{intent_id}",
                        "intent_id":             intent_id,
                        "generated_sql":         failed_result.get("sql", ""),
                        "validation_errors":     failed_result.get("violations", []),
                        "corrections_suggested": failed_result.get("corrections_suggested", []),
                        "original_prompt":       intent.get("description", ""),
                        "domain":                intent.get("domain", ""),
                        "sub_domain":            intent.get("sub_domain"),
                        "tables":                [intent["structured_table"]] if intent.get("structured_table") else [],
                        "rls_applied":           original.get("rls_applied"),
                        "cls_applied":           original.get("cls_applied"),
                        "model_used":            original.get("model_used"),
                    }

                    logger.info(
                        "SAGE correction attempt=%d intent_id=%d errors=%d",
                        attempt + 1, intent_id, len(failed_result.get("violations", [])),
                    )

                    try:
                        corr_resp = await client.post(f"{SAGE_URL}/sql/correct", json=correct_payload)
                        corr_resp.raise_for_status()
                        corr_data     = corr_resp.json()
                        corrected_sql = corr_data.get("corrected_sql")
                        if corrected_sql:
                            current_sqls = [
                                {**r, "generated_sql": corrected_sql}
                                if r.get("intent_id") == intent_id else r
                                for r in current_sqls
                            ]
                            logger.info(
                                "SAGE corrected intent_id=%d → %d chars",
                                intent_id, len(corrected_sql),
                            )
                    except Exception as e:
                        logger.error("SAGE correction failed intent_id=%d: %s", intent_id, e)

        overall = val_response.get("status", "error") if val_response else "error"
        return {
            "valkyrie_status":    overall,
            "valkyrie_result":    val_response,
            "synthesizer_context": val_response.get("synthesizer_context") if val_response else None,
            "valkyrie_error":     None,
        }

    except httpx.ConnectError:
        logger.error("VALKYRIE not reachable at %s", VALKYRIE_URL)
        return {
            "valkyrie_status":    "error",
            "valkyrie_result":    None,
            "synthesizer_context": None,
            "valkyrie_error":     "VALKYRIE service unavailable",
        }
    except Exception as e:
        logger.error("valkyrie_node error: %s", e)
        return {
            "valkyrie_status":    "error",
            "valkyrie_result":    None,
            "synthesizer_context": None,
            "valkyrie_error":     str(e),
        }


def _skip() -> dict:
    return {
        "valkyrie_status":    "skipped",
        "valkyrie_result":    None,
        "synthesizer_context": None,
        "valkyrie_error":     None,
    }
