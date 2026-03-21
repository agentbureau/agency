from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from agency.db.primitives import find_similar
from agency.engine.constants import TRIAGE_TOP_N, METAPRIMITIVE_SIMILARITY_THRESHOLD

router = APIRouter(tags=["triage"])


class TriageRequest(BaseModel):
    description: str
    project_id: str | None = None


@router.post("/triage", status_code=200)
def triage(req: TriageRequest, request: Request):
    if not req.description or not req.description.strip():
        raise HTTPException(status_code=422, detail={
            "error_type": "validation",
            "code": "triage_missing_description",
            "message": "The description field is required and must be non-empty.",
            "cause": "Request body missing description or description is empty string.",
            "fix": "Provide a non-empty task description.",
        })

    conn = request.app.state.db

    try:
        # Search all three slot types with scope='task'
        role_results = find_similar(conn, "role_components", req.description,
                                     limit=TRIAGE_TOP_N, scope="task")
        outcome_results = find_similar(conn, "desired_outcomes", req.description,
                                        limit=TRIAGE_TOP_N, scope="task")
        tradeoff_results = find_similar(conn, "trade_off_configs", req.description,
                                         limit=TRIAGE_TOP_N, scope="task")
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "error_type": "transient",
            "code": "triage_search_failed",
            "message": "Primitive search failed.",
            "cause": str(e),
            "fix": "Check embedding model is downloaded (agency primitives update) and database is accessible.",
        })

    # Tag results with their type
    for r in role_results:
        r["type"] = "role_component"
    for r in outcome_results:
        r["type"] = "desired_outcome"
    for r in tradeoff_results:
        r["type"] = "trade_off_config"

    # Merge, dedup by ID, sort by similarity, truncate
    all_results = role_results + outcome_results + tradeoff_results
    seen_ids = set()
    deduped = []
    for r in sorted(all_results, key=lambda x: x.get("similarity", 0), reverse=True):
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            deduped.append(r)
    matched = deduped[:TRIAGE_TOP_N]

    # Build response
    matched_primitives = [
        {"name": r.get("name", ""), "type": r["type"], "similarity": round(r.get("similarity", 0), 4)}
        for r in matched
    ]

    # Warning for empty store
    warning = None
    if not all_results:
        warning = "No primitives installed. Run agency primitives update to download starter primitives."

    # Recommendation logic
    has_strong_match = any(r.get("similarity", 0) >= METAPRIMITIVE_SIMILARITY_THRESHOLD for r in matched)

    if matched:
        strongest = matched[0]
        strongest_name = strongest.get("name", "unknown")
        strongest_sim = round(strongest.get("similarity", 0), 3)

        if has_strong_match:
            n_above = sum(1 for r in matched if r.get("similarity", 0) >= METAPRIMITIVE_SIMILARITY_THRESHOLD)
            recommendation = "compose"
            reasoning = f"Matched {n_above} primitive(s) above 0.5 similarity; strongest match: '{strongest_name}' at {strongest_sim}."
        else:
            recommendation = "skip-safe"
            reasoning = f"No primitive exceeded 0.5 similarity; strongest match: '{strongest_name}' at {strongest_sim}. Composition would fill slots with low-relevance primitives."
    else:
        recommendation = "skip-safe"
        reasoning = "No primitives in store."

    return {
        "matched_primitives": matched_primitives,
        "task_type": "unclassified",
        "recommendation": recommendation,
        "reasoning": reasoning,
        "warning": warning,
    }
