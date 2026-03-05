from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/evolution", tags=["evolution"])


class EvolutionProposal(BaseModel):
    agent_id: str
    task_description: str
    strategy: str = "perturbation"  # "perturbation" | "adjacent"
    n_variants: int = 3


@router.post("/proposals", status_code=201)
def create_proposal(req: EvolutionProposal, request: Request):
    from agency.utils.ids import new_uuid
    from agency.engine.evolver import random_perturbation
    from agency.engine.agent_creator import create_adjacent_agent

    proposal_id = new_uuid()
    instance_id = str(request.app.state.state_dir)

    if req.strategy == "perturbation":
        variants = random_perturbation(
            request.app.state.db, req.agent_id, instance_id, req.n_variants
        )
    elif req.strategy == "adjacent":
        adj = create_adjacent_agent(request.app.state.db, req.agent_id, instance_id)
        variants = [adj] if adj else []
    else:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {req.strategy}")

    if not hasattr(request.app.state, "proposals"):
        request.app.state.proposals = {}
    request.app.state.proposals[proposal_id] = {
        "source_agent_id": req.agent_id,
        "strategy": req.strategy,
        "variant_agent_ids": variants,
        "status": "pending",
        "approved_agent_id": None,
    }
    return {"proposal_id": proposal_id, "variant_agent_ids": variants}


@router.get("/proposals")
def list_proposals(request: Request):
    proposals = getattr(request.app.state, "proposals", {})
    return [{"proposal_id": pid, **data} for pid, data in proposals.items()]


@router.post("/proposals/{proposal_id}/approve", status_code=200)
def approve_proposal(proposal_id: str, approved_agent_id: str, request: Request):
    proposals = getattr(request.app.state, "proposals", {})
    if proposal_id not in proposals:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p = proposals[proposal_id]
    if approved_agent_id not in p["variant_agent_ids"]:
        raise HTTPException(status_code=400, detail="Agent not in proposal variants")
    p["status"] = "approved"
    p["approved_agent_id"] = approved_agent_id
    return {"proposal_id": proposal_id, "approved_agent_id": approved_agent_id}
