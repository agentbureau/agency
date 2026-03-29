from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from agency.db.primitives import find_similar
from agency.engine.classifier import classify_task_type, estimate_method_absence
from agency.engine.constants import (
    TRIAGE_TOP_N,
    METAPRIMITIVE_SIMILARITY_THRESHOLD,
    COMPOSITION_FITNESS_FLOOR,
    COMPOSITION_FITNESS_GOOD_THRESHOLD,
    AGENCY_PROBABILITY_BY_TYPE,
    METHOD_ABSENCE_HIGH,
    METHOD_ABSENCE_MODERATE,
)

router = APIRouter(tags=["triage"])


class TriageRequest(BaseModel):
    description: str
    project_id: str | None = None


def compute_recommendation(
    task_type_probability: str,
    fitness_band: str,
    method_absence: float,
) -> tuple[str, str | None]:
    """Compute compose recommendation from three signals.

    Returns: (recommendation, reason | None)
    """
    # Unlikely to help: fitness below floor
    if fitness_band == "low":
        return ("compose_unlikely_to_help",
                "Composition fitness below 0.39 floor — primitive pool has "
                "insufficient semantic overlap with this task.")

    # Unlikely to help: CC-favoured task type + low method absence
    if task_type_probability == "low" and method_absence < METHOD_ABSENCE_MODERATE:
        return ("compose_unlikely_to_help",
                "Task type is CC-favoured and the prompt already prescribes "
                "the analytical method — Agency unlikely to add value.")

    # Compose with advisory: mixed signals
    if task_type_probability == "low":
        return ("compose_with_advisory", None)
    if method_absence < METHOD_ABSENCE_MODERATE:
        return ("compose_with_advisory", None)

    # Compose: all signals favourable
    return ("compose", None)


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

    # Signal 1: task type
    task_type = classify_task_type(req.description)
    task_type_probability = AGENCY_PROBABILITY_BY_TYPE.get(task_type, "neutral")

    try:
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

    matched_primitives = [
        {"name": r.get("name", ""), "type": r["type"], "similarity": round(r.get("similarity", 0), 4)}
        for r in matched
    ]

    # Warning for empty store
    warning = None
    if not all_results:
        warning = "No primitives installed. Run agency primitives update to download starter primitives."

    # Signal 2: fitness estimate
    similarities = [r.get("similarity", 0) for r in matched]
    fitness_estimate = sum(similarities) / len(similarities) if similarities else 0.0
    if fitness_estimate < COMPOSITION_FITNESS_FLOOR:
        fitness_band = "low"
    elif fitness_estimate < COMPOSITION_FITNESS_GOOD_THRESHOLD:
        fitness_band = "moderate"
    else:
        fitness_band = "good"

    # Signal 3: method absence
    method_absence = estimate_method_absence(req.description)
    if method_absence >= METHOD_ABSENCE_HIGH:
        method_absence_band = "high"
    elif method_absence >= METHOD_ABSENCE_MODERATE:
        method_absence_band = "moderate"
    else:
        method_absence_band = "low"

    # Combined recommendation
    recommendation, reason = compute_recommendation(
        task_type_probability, fitness_band, method_absence,
    )

    # Reasoning text
    method_note = (
        "analytical method not specified — Agency can fill the gap"
        if method_absence >= METHOD_ABSENCE_HIGH
        else "analytical method partially or fully specified in prompt"
    )
    reasoning = (
        f"Task type: {task_type} ({task_type_probability} Agency probability). "
        f"Fitness estimate: {fitness_estimate:.3f} ({fitness_band}). "
        f"Method absence: {method_absence:.1f} ({method_note}). "
        f"Recommendation: {recommendation}."
    )

    response = {
        "matched_primitives": matched_primitives,
        "task_type": task_type,
        "fitness_estimate": round(fitness_estimate, 4),
        "method_absence_estimate": round(method_absence, 2),
        "recommendation": recommendation,
        "reasoning": reasoning,
        "signals": {
            "task_type": task_type,
            "task_type_agency_probability": task_type_probability,
            "fitness_estimate": round(fitness_estimate, 4),
            "fitness_band": fitness_band,
            "method_absence_estimate": round(method_absence, 2),
            "method_absence_band": method_absence_band,
        },
        "warning": warning,
    }
    if reason is not None:
        response["reason"] = reason

    # Capability caveat for research tasks (Issues 5-6)
    if task_type == "research":
        response["capability_caveat"] = (
            "Agency's advantage is weakest on research tasks requiring "
            "domain-specific knowledge. Composition primitives frame how "
            "to think — they cannot supply what to know."
        )

    return response
