from functools import lru_cache
import logging
import math
import os

# Suppress HF warnings at import time — before any huggingface_hub import
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def suppress_hf_warnings():
    """Suppress HuggingFace Hub and transformers warnings before model load.

    Shared utility — call before any sentence-transformers import.
    """
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
    logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
    print(f"Loading embedding model ({EMBEDDING_MODEL}) — this may take a moment on first run.")


@lru_cache(maxsize=1)
def _model():
    suppress_hf_warnings()
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def embed(text: str) -> list[float]:
    """Embed a task description (query)."""
    return _model().encode(text).tolist()


def embed_document(text: str) -> list[float]:
    """Embed a primitive description (document)."""
    return _model().encode(text).tolist()


_reembed_checked = False


def verify_and_fix_embeddings(db) -> None:
    """Check stored embedding dimensions. If mismatched, re-embed automatically.

    Called once on first agency_assign after server start. If dimensions match,
    this is a no-op (one SQL query + one embed call). If they don't match,
    re-embeds all primitives inline before returning.
    """
    global _reembed_checked
    if _reembed_checked:
        return
    _reembed_checked = True

    import json
    from agency.db.primitives import PRIMITIVE_TABLES

    row = db.execute("SELECT embedding FROM role_components LIMIT 1").fetchone()
    if not row:
        return
    stored_dims = len(json.loads(row[0]))
    test_vec = embed_document("test")
    model_dims = len(test_vec)
    if stored_dims == model_dims:
        return

    print(
        "\nEmbedding model has changed. Re-embedding your pool of primitives. "
        "This is a one-time operation that will take a few seconds.\n"
    )
    logger = logging.getLogger(__name__)
    logger.warning(
        "Embedding dimension mismatch (stored=%d, model=%d). Re-embedding...",
        stored_dims, model_dims,
    )

    total = 0
    for table in PRIMITIVE_TABLES:
        rows = db.execute(f"SELECT id, description FROM {table}").fetchall()
        for pid, description in rows:
            vec = embed_document(description)
            db.execute(
                f"UPDATE {table} SET embedding = ? WHERE id = ?",
                (json.dumps(vec), pid),
            )
            total += 1
        db.commit()

    print(f"Done — {total} primitives re-embedded.\n")


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)
