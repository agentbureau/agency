import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agency.db.primitives import find_similar
from agency.db.compositions import upsert_agent
from agency.db.templates import list_templates
from agency.engine.renderer import render_agent, load_default_template
from agency.engine.constants import (
    METAPRIMITIVE_SIMILARITY_THRESHOLD,
    POOL_COVERAGE_WARNING_THRESHOLD,
    SKILL_TAG_BOOST_FACTOR,
    ASSIGNER_STRATEGY_KEY,
    ASSIGNER_STRATEGY_EMBEDDING,
    ASSIGNER_STRATEGY_LLM,
    ASSIGNER_LLM_MODEL,
    ASSIGNER_LLM_TIMEOUT,
    ASSIGNER_LLM_MAX_RETRIES,
    ASSIGNER_FALLBACK_LOG,
    COMPOSITION_FITNESS_FLOOR,
    COMPOSITION_FITNESS_GOOD_THRESHOLD,
    TASK_TYPE_KEYWORDS,
)
from agency.engine.classifier import classify_task_type
from agency.utils.hashing import content_hash
from agency.utils.ids import new_uuid
from agency.utils.errors import PrimitiveStoreEmpty

logger = logging.getLogger(__name__)


def _apply_skill_boost(results: list[dict], skills: list[str] | None) -> None:
    """Boost similarity scores for primitives matching skill tags (§4.4.2b)."""
    if not skills:
        return
    for r in results:
        desc_lower = r["description"].lower()
        if any(tag.lower() in desc_lower for tag in skills):
            r["similarity"] = min(r["similarity"] * SKILL_TAG_BOOST_FACTOR, 1.0)
    results.sort(key=lambda r: r["similarity"], reverse=True)


def _apply_relevance_floor(results: list[dict]) -> list[dict]:
    """Filter primitives below the similarity threshold (§4.4.2a)."""
    return [r for r in results if r.get("similarity", 0) >= METAPRIMITIVE_SIMILARITY_THRESHOLD]


def _log_fallback(task_id: str, failure_mode: str, slot_affected: str, detail: str) -> None:
    """Log an LLM-path fallback event to the fallback log file (§4.4.3c)."""
    log_path = Path(os.path.expanduser(ASSIGNER_FALLBACK_LOG))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "failure_mode": failure_mode,
        "slot_affected": slot_affected,
        "detail": detail,
        "strategy_used": "embedding",
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _render_functional_agent_prompt(
    metaprimitives: list[dict],
    task_description: str,
    skills: list[str] | None,
    role_candidates: list[dict],
    outcome_candidates: list[dict],
    tradeoff_candidates: list[dict],
    max_role_components: int = 3,
    max_desired_outcomes: int = 1,
    max_trade_off_configs: int = 1,
) -> str:
    """Render the functional agent Jinja2 template for the LLM assigner call."""
    from jinja2 import Environment, FileSystemLoader

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("functional_agent.jinja2")
    return template.render(
        metaprimitives=metaprimitives,
        task_description=task_description,
        skills=skills,
        role_candidates=role_candidates,
        outcome_candidates=outcome_candidates,
        tradeoff_candidates=tradeoff_candidates,
        max_role_components=max_role_components,
        max_desired_outcomes=max_desired_outcomes,
        max_trade_off_configs=max_trade_off_configs,
    )


def _validate_llm_selections(
    selections: dict,
    role_candidate_ids: set[str],
    outcome_candidate_ids: set[str],
    tradeoff_candidate_ids: set[str],
    task_id: str,
) -> dict:
    """Validate LLM selections against candidate lists.

    Returns validated selections dict. Hallucinated IDs are removed and
    logged; affected slots fall back to embedding path (returned as empty
    lists so the caller can detect and substitute).
    """
    validated = {}
    slot_map = {
        "role_components": role_candidate_ids,
        "desired_outcomes": outcome_candidate_ids,
        "trade_off_configs": tradeoff_candidate_ids,
    }
    for slot_name, valid_ids in slot_map.items():
        raw = selections.get(slot_name, [])
        valid = []
        for item in raw:
            item_id = item.get("id", "") if isinstance(item, dict) else str(item)
            if item_id in valid_ids:
                valid.append(item)
            else:
                _log_fallback(
                    task_id, "hallucinated_id", slot_name,
                    f"ID {item_id} not in candidate list",
                )
        validated[slot_name] = valid
    return validated


def _assign_via_llm(
    db: sqlite3.Connection,
    task_id: str,
    task_description: str,
    skills: list[str] | None,
) -> dict | None:
    """Attempt LLM-based primitive selection (§4.4.3).

    Returns a dict with 'selections', 'fitness_verdict',
    'pool_coverage_warning', and 'task_classification' on success.
    Returns None on unrecoverable failure (caller should use embedding path).
    """
    # 1. Load metaprimitives
    try:
        metaprimitives = find_similar(
            db, "role_components", task_description,
            limit=10, scope="meta:assigner",
        )
    except Exception:
        metaprimitives = []

    # Also load meta desired_outcomes and trade_off_configs
    for table in ("desired_outcomes", "trade_off_configs"):
        try:
            meta = find_similar(db, table, task_description, limit=10, scope="meta:assigner")
            metaprimitives.extend(meta)
        except Exception:
            pass

    # Format metaprimitives for the template
    mp_formatted = []
    for mp in metaprimitives:
        mp_formatted.append({
            "type": mp.get("type", "unknown"),
            "name": mp.get("name", mp.get("id", "unnamed")),
            "description": mp.get("description", ""),
        })

    # 2. Get top-20 candidates per slot
    role_candidates = find_similar(db, "role_components", task_description, limit=20, scope="task")
    outcome_candidates = find_similar(db, "desired_outcomes", task_description, limit=20, scope="task")
    tradeoff_candidates = find_similar(db, "trade_off_configs", task_description, limit=20, scope="task")

    role_candidate_ids = {r["id"] for r in role_candidates}
    outcome_candidate_ids = {r["id"] for r in outcome_candidates}
    tradeoff_candidate_ids = {r["id"] for r in tradeoff_candidates}

    # 3. Render the functional agent prompt
    prompt = _render_functional_agent_prompt(
        metaprimitives=mp_formatted,
        task_description=task_description,
        skills=skills,
        role_candidates=role_candidates,
        outcome_candidates=outcome_candidates,
        tradeoff_candidates=tradeoff_candidates,
    )

    # 4. LLM call with retry
    retries = ASSIGNER_LLM_MAX_RETRIES + 1  # 1 initial + retries
    last_error = None

    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["claude", "--print", "--model", ASSIGNER_LLM_MODEL, "--output-format", "json"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=ASSIGNER_LLM_TIMEOUT,
            )
            if result.returncode != 0:
                _log_fallback(task_id, "api_error", "all", f"claude exit code {result.returncode}: {result.stderr[:200]}")
                return None

            parsed = json.loads(result.stdout)

            # 5. Validate selections
            selections = parsed.get("selections", {})
            validated = _validate_llm_selections(
                selections,
                role_candidate_ids,
                outcome_candidate_ids,
                tradeoff_candidate_ids,
                task_id,
            )

            return {
                "selections": validated,
                "fitness_verdict": parsed.get("fitness_verdict", "marginal"),
                "pool_coverage_warning": parsed.get("pool_coverage_warning", False),
                "task_classification": parsed.get("task_classification", ""),
                "notes": parsed.get("notes", ""),
                # Pass candidates through for embedding fallback on empty slots
                "_role_candidates": role_candidates,
                "_outcome_candidates": outcome_candidates,
                "_tradeoff_candidates": tradeoff_candidates,
            }

        except subprocess.TimeoutExpired:
            _log_fallback(task_id, "timeout", "all", f"LLM call timed out after {ASSIGNER_LLM_TIMEOUT}s")
            return None
        except json.JSONDecodeError as e:
            last_error = str(e)
            if attempt < retries - 1:
                logger.debug("LLM JSON parse failure (attempt %d), retrying", attempt + 1)
                continue
            _log_fallback(task_id, "parse", "all", f"JSON parse failure after {retries} attempts: {last_error}")
            return None
        except (OSError, subprocess.SubprocessError) as e:
            _log_fallback(task_id, "api_error", "all", str(e))
            return None

    return None



def _assign_via_embedding(
    db: sqlite3.Connection, task_id: str, task: dict,
    skills: list[str] | None = None,
) -> dict:
    """Run the embedding-based assignment path.

    Returns dict with:
      "results": (role_results, outcome_results, tradeoff_results) — post-floor
      "raw_candidates": (raw_role, raw_outcome, raw_tradeoff) — pre-floor
      "task_type": str
    """
    task_description = task.get("task_description", "")
    task_type = classify_task_type(task_description)

    role_results = find_similar(
        db, "role_components", task_description, limit=3, scope="task",
    )
    if not role_results:
        raise PrimitiveStoreEmpty("No role components in primitive store")
    _apply_skill_boost(role_results, skills)
    raw_role_candidates = list(role_results)
    role_results = _apply_relevance_floor(role_results)

    outcome_results = find_similar(
        db, "desired_outcomes", task_description, limit=1, scope="task",
    )
    _apply_skill_boost(outcome_results, skills)
    raw_outcome_candidates = list(outcome_results)
    outcome_results = _apply_relevance_floor(outcome_results)

    tradeoff_results = find_similar(
        db, "trade_off_configs", task_description, limit=1, scope="task",
    )
    _apply_skill_boost(tradeoff_results, skills)
    raw_tradeoff_candidates = list(tradeoff_results)
    tradeoff_results = _apply_relevance_floor(tradeoff_results)

    return {
        "results": (role_results, outcome_results, tradeoff_results),
        "raw_candidates": (raw_role_candidates, raw_outcome_candidates, raw_tradeoff_candidates),
        "task_type": task_type,
    }


def _persist_candidates(
    conn: sqlite3.Connection,
    task_id: str,
    role_candidates: list[dict],
    outcome_candidates: list[dict],
    tradeoff_candidates: list[dict],
    selected_ids: set[str],
) -> None:
    """Persist assignment candidates for experiment tracking (Issue 22)."""
    rows = []
    for ptype, candidates in [
        ("role_component", role_candidates),
        ("desired_outcome", outcome_candidates),
        ("trade_off_config", tradeoff_candidates),
    ]:
        for c in candidates:
            rows.append((
                new_uuid(), task_id, c["id"], ptype,
                c.get("similarity", 0.0),
                1 if c["id"] in selected_ids else 0,
                c.get("retrieval_pass", "full_pool"),
            ))
    if rows:
        conn.executemany(
            """INSERT INTO assignment_candidates
               (id, task_id, primitive_id, primitive_type, similarity_score,
                was_selected, retrieval_pass)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()


def assign_agent(db: sqlite3.Connection, task_id: str, task: dict,
                 cfg: dict | None = None, skills: list[str] | None = None) -> dict:
    """
    Find or compose the best agent for a task.

    Strategy is determined by cfg['assigner']['strategy']:
    - 'embedding' (default): deterministic embedding-similarity path (§4.4.2)
    - 'llm': LLM-based selection with embedding fallback (§4.4.3)
    """
    task_description = task.get("task_description", "")
    instance_id = task.get("instance_id", "default")
    client_id = task.get("client_id")
    project_id = task.get("project_id")

    # Read strategy from feature flag (§4.4.1)
    strategy = ASSIGNER_STRATEGY_EMBEDDING
    if cfg:
        strategy = cfg.get("assigner", {}).get(ASSIGNER_STRATEGY_KEY, ASSIGNER_STRATEGY_EMBEDDING)

    # Pre-classify task type (Issue 8) — once, before strategy branch
    task_type = classify_task_type(task_description)

    llm_result = None
    emb_result = None
    if strategy == ASSIGNER_STRATEGY_LLM:
        llm_result = _assign_via_llm(db, task_id, task_description, skills)

    if llm_result is not None:
        # Use LLM selections, with per-slot embedding fallback for empty slots
        selections = llm_result["selections"]

        # Extract selected IDs and descriptions from LLM output
        role_ids = [s["id"] if isinstance(s, dict) else s for s in selections.get("role_components", [])]
        outcome_ids = [s["id"] if isinstance(s, dict) else s for s in selections.get("desired_outcomes", [])]
        tradeoff_ids = [s["id"] if isinstance(s, dict) else s for s in selections.get("trade_off_configs", [])]

        # Build lookup maps from candidates
        role_map = {r["id"]: r for r in llm_result["_role_candidates"]}
        outcome_map = {r["id"]: r for r in llm_result["_outcome_candidates"]}
        tradeoff_map = {r["id"]: r for r in llm_result["_tradeoff_candidates"]}

        # Build result lists from LLM selections
        role_results = [role_map[rid] for rid in role_ids if rid in role_map]
        outcome_results = [outcome_map[oid] for oid in outcome_ids if oid in outcome_map]
        tradeoff_results = [tradeoff_map[tid] for tid in tradeoff_ids if tid in tradeoff_map]

        # LLM fallback — call embedding path once, reuse for all empty slots
        if not role_results or not outcome_results or not tradeoff_results:
            emb_result = _assign_via_embedding(db, task_id, task, skills)
            if not role_results:
                role_results = emb_result["results"][0]
            if not outcome_results:
                outcome_results = emb_result["results"][1]
            if not tradeoff_results:
                tradeoff_results = emb_result["results"][2]
    else:
        # Full embedding path
        emb_result = _assign_via_embedding(db, task_id, task, skills)
        role_results, outcome_results, tradeoff_results = emb_result["results"]

    role_component_ids = [r["id"] for r in role_results]
    role_component_texts = [r["description"] for r in role_results]

    desired_outcome = outcome_results[0]["description"] if outcome_results else "Complete the task effectively"
    desired_outcome_id = outcome_results[0]["id"] if outcome_results else None

    trade_off_config = tradeoff_results[0]["description"] if tradeoff_results else "Balance quality and speed"
    trade_off_config_id = tradeoff_results[0]["id"] if tradeoff_results else None

    # Persist assignment candidates for experiment tracking (Issue 22)
    selected_ids = set(role_component_ids)
    if desired_outcome_id:
        selected_ids.add(desired_outcome_id)
    if trade_off_config_id:
        selected_ids.add(trade_off_config_id)
    try:
        if llm_result is not None:
            raw_role = llm_result["_role_candidates"]
            raw_outcome = llm_result["_outcome_candidates"]
            raw_tradeoff = llm_result["_tradeoff_candidates"]
        elif emb_result is not None:
            raw_role = emb_result["raw_candidates"][0]
            raw_outcome = emb_result["raw_candidates"][1]
            raw_tradeoff = emb_result["raw_candidates"][2]
        else:
            raw_role = raw_outcome = raw_tradeoff = []
        _persist_candidates(db, task_id, raw_role, raw_outcome, raw_tradeoff, selected_ids)
    except Exception as e:
        logger.warning("Candidate persistence failed: %s", e)

    # Select template
    templates = list_templates(db, template_type="task_agent", instance_id=instance_id)
    if templates:
        template_content = templates[0]["content"]
        template_id = templates[0]["id"]
    else:
        template_content = load_default_template("task_agent")
        template_id = "default"

    # Upsert composition
    agent_id = upsert_agent(
        db,
        role_component_ids=role_component_ids,
        desired_outcome_id=desired_outcome_id,
        trade_off_config_id=trade_off_config_id,
        instance_id=instance_id,
        client_id=client_id,
        project_id=project_id,
        template_id=template_id,
    )

    # Track assignment counts for explore/exploit (Issue 25)
    try:
        from agency.db.performance import increment_assignment_counts
        increment_assignment_counts(db, role_component_ids, desired_outcome_id, trade_off_config_id)
    except Exception as e:
        logger.warning("Assignment count increment failed: %s", e)

    composition_hash = content_hash(json.dumps(sorted(role_component_ids)))

    rendered = render_agent(
        template=template_content,
        agent_id=agent_id,
        content_hash=composition_hash,
        template_id=template_id,
        role_components=role_component_texts if role_component_texts else ["general task completion"],
        desired_outcome=desired_outcome,
        trade_off_config=trade_off_config,
        task_description=task_description,
        output_structure=task.get("output_structure", "structured"),
        output_format=task.get("output_format", "json"),
        clarification_behaviour=task.get("clarification_behaviour", "ask"),
    )

    # Compute mean embedding vector across all selected primitives
    all_embeddings = []
    for r in role_results + outcome_results + tradeoff_results:
        emb = r.get("embedding")
        if emb:
            vec = json.loads(emb) if isinstance(emb, str) else emb
            all_embeddings.append(vec)

    if all_embeddings:
        n = len(all_embeddings[0])
        mean_embedding = [sum(e[i] for e in all_embeddings) / len(all_embeddings) for i in range(n)]
    else:
        mean_embedding = []

    # Composition fitness metadata (§4.4.2c / §4.4.3)
    all_selected = role_results + outcome_results + tradeoff_results

    # Mean fitness and advisory band (Issue 4)
    fitness_floor = (
        (cfg or {}).get("assigner", {}).get("composition_fitness_floor")
        or COMPOSITION_FITNESS_FLOOR
    )
    similarities = [r.get("similarity", 0) for r in all_selected if r.get("id")]
    mean_fitness = sum(similarities) / len(similarities) if similarities else 0.0
    if mean_fitness < fitness_floor:
        pool_match = "low"
    elif mean_fitness < COMPOSITION_FITNESS_GOOD_THRESHOLD:
        pool_match = "moderate"
    else:
        pool_match = "good"

    if llm_result is not None:
        # LLM path: use the LLM's fitness verdict and pool coverage warning
        composition_fitness = {
            "per_primitive_similarity": {
                r["id"]: round(r.get("similarity", 0), 4)
                for r in all_selected if r.get("id")
            },
            "pool_coverage_warning": llm_result.get("pool_coverage_warning", False),
            "fitness_verdict": llm_result.get("fitness_verdict", "marginal"),
            "task_classification": task_type,
            "task_type": task_type,
            "mean_fitness": round(mean_fitness, 4),
            "pool_match": pool_match,
            "slots_filled": {
                "role_components": len(role_component_ids),
                "desired_outcomes": 1 if desired_outcome_id else 0,
                "trade_off_configs": 1 if trade_off_config_id else 0,
            },
            "slots_empty": {
                "role_components": max(0, 3 - len(role_component_ids)),
                "desired_outcomes": 0 if desired_outcome_id else 1,
                "trade_off_configs": 0 if trade_off_config_id else 1,
            },
        }
    else:
        composition_fitness = {
            "per_primitive_similarity": {
                r["id"]: round(r.get("similarity", 0), 4)
                for r in all_selected if r.get("id")
            },
            "pool_coverage_warning": not any(
                r.get("similarity", 0) >= POOL_COVERAGE_WARNING_THRESHOLD
                for r in all_selected
            ),
            "task_type": task_type,
            "mean_fitness": round(mean_fitness, 4),
            "pool_match": pool_match,
            "slots_filled": {
                "role_components": len(role_component_ids),
                "desired_outcomes": 1 if desired_outcome_id else 0,
                "trade_off_configs": 1 if trade_off_config_id else 0,
            },
            "slots_empty": {
                "role_components": max(0, 3 - len(role_component_ids)),
                "desired_outcomes": 0 if desired_outcome_id else 1,
                "trade_off_configs": 0 if trade_off_config_id else 1,
            },
        }

    # Capability caveat for research tasks (Issues 5-6)
    if task_type == "research":
        composition_fitness["capability_caveat"] = (
            "Agency's advantage is weakest on research tasks requiring "
            "domain-specific knowledge. Composition primitives frame how "
            "to think — they cannot supply what to know."
        )

    return {
        "agent_id": agent_id,
        "content_hash": composition_hash,
        "template_id": template_id,
        "rendered_prompt": rendered,
        "embedding_vector": mean_embedding,
        "primitive_ids": {
            "role_components": role_component_ids,
            "desired_outcomes": [desired_outcome_id] if desired_outcome_id else [],
            "trade_off_configs": [trade_off_config_id] if trade_off_config_id else [],
        },
        "composition_fitness": composition_fitness,
    }


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x ** 2 for x in a) ** 0.5
    mag_b = sum(x ** 2 for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def deduplicate_compositions(compositions: list, threshold: float = 0.90) -> list[list[int]]:
    assigned = [False] * len(compositions)
    clusters = []
    for i, comp in enumerate(compositions):
        if assigned[i]:
            continue
        cluster = [i]
        for j in range(i + 1, len(compositions)):
            if not assigned[j]:
                sim = cosine_similarity(comp.embedding, compositions[j].embedding)
                if sim >= threshold:
                    cluster.append(j)
                    assigned[j] = True
        clusters.append(cluster)
        assigned[i] = True
    return clusters


def assign_agents_batch(tasks: list, db, cfg: dict) -> dict:
    """Assign agents to a batch of tasks with cosine-similarity deduplication."""
    results = []
    for task in tasks:
        enriched = task.description
        if task.skills:
            enriched += " " + " ".join(task.skills)
        if task.deliverables:
            enriched += " " + " ".join(task.deliverables)
        result = assign_agent(
            db, task.external_id or enriched[:16], {"task_description": enriched},
            cfg=cfg, skills=task.skills if hasattr(task, 'skills') else None,
        )
        results.append(result)

    class Comp:
        def __init__(self, embedding):
            self.embedding = embedding

    comps = [Comp(r["embedding_vector"]) for r in results]
    clusters = deduplicate_compositions(comps)

    assignments = {}
    agents = {}

    for cluster in clusters:
        canonical_idx = cluster[0]
        canonical = results[canonical_idx]
        agent_hash = canonical["content_hash"]

        agents[agent_hash] = {
            "rendered_prompt": canonical["rendered_prompt"],
            "content_hash": canonical["content_hash"],
            "template_id": canonical["template_id"],
            "primitive_ids": canonical["primitive_ids"],
            "agent_id": canonical["agent_id"],
            "composition_fitness": canonical.get("composition_fitness"),
        }

        for idx in cluster:
            task = tasks[idx]
            ext_id = task.external_id or str(idx)
            assignments[ext_id] = {
                "agency_task_id": results[idx].get("task_id", ext_id),
                "agent_hash": agent_hash,
                "agent_id": results[idx]["agent_id"],
            }

    return {"assignments": assignments, "agents": agents}
