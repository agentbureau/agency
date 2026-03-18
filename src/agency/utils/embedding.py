from functools import lru_cache
import logging
import math
import os


EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def suppress_hf_warnings():
    """Suppress HuggingFace Hub and transformers warnings before model load.

    Shared utility — call before any sentence-transformers import.
    """
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
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
    return _model().encode(text).tolist()


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    mag1 = math.sqrt(sum(a * a for a in v1))
    mag2 = math.sqrt(sum(b * b for b in v2))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)
