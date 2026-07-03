"""
Local sentence-transformer embeddings.

File-drop install (no deployment):
  1. Run ``scripts\download-models.ps1`` — it pulls all-MiniLM-L6-v2 into
     ``models/embeddings/all-MiniLM-L6-v2/``.
  2. ``pip install sentence-transformers`` (one-time).
  3. Restart backend — this module auto-detects the folder.

If either step is missing, ``encode()`` returns ``None`` and every caller is
expected to fall back gracefully (e.g. just skip de-dup).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Where the user drops the sentence-transformer model folder.
MODELS_DIR = Path(os.environ.get(
    "RI_EMBEDDINGS_DIR",
    str(Path(__file__).resolve().parent.parent.parent / "models" / "embeddings"),
))


# ---------------------------------------------------------------------------
# Lazy singleton — load the model on first use, never again.
# ---------------------------------------------------------------------------

_MODEL = None
_TRIED_LOAD = False
_MODEL_NAME: Optional[str] = None


def _find_model_dir() -> Optional[Path]:
    if not MODELS_DIR.exists():
        return None
    # Any sub-directory containing config.json is a valid HF/ST model dir.
    for child in sorted(MODELS_DIR.iterdir()):
        if child.is_dir() and (child / "config.json").exists():
            return child
    return None


def get_model():
    """Return the loaded SentenceTransformer or None if unavailable."""
    global _MODEL, _TRIED_LOAD, _MODEL_NAME
    if _TRIED_LOAD:
        return _MODEL
    _TRIED_LOAD = True

    model_dir = _find_model_dir()
    if model_dir is None:
        logger.info("embeddings: no model folder under %s — features disabled. "
                    "Run scripts/download-models.ps1 to enable.", MODELS_DIR)
        return None

    try:
        from sentence_transformers import SentenceTransformer  # local import
    except ImportError:
        logger.info("embeddings: sentence-transformers not installed — features disabled. "
                    "Run: pip install sentence-transformers")
        return None

    try:
        _MODEL = SentenceTransformer(str(model_dir))
        _MODEL_NAME = model_dir.name
        logger.info("embeddings: loaded %s from %s", _MODEL_NAME, model_dir)
        return _MODEL
    except Exception as exc:  # noqa: BLE001
        logger.warning("embeddings: failed to load %s (%s) — features disabled", model_dir, exc)
        return None


def is_available() -> bool:
    return get_model() is not None


def model_name() -> Optional[str]:
    get_model()
    return _MODEL_NAME


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode(texts: Iterable[str]) -> Optional[np.ndarray]:
    """Embed a list of strings. Returns an (N, D) ``float32`` array, or
    ``None`` if the model isn't available — callers must handle that."""
    model = get_model()
    if model is None:
        return None
    arr = list(texts)
    if not arr:
        return np.zeros((0, 384), dtype=np.float32)
    out = model.encode(arr, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(out, dtype=np.float32)


# ---------------------------------------------------------------------------
# Convenience: cluster near-duplicates by cosine similarity
# ---------------------------------------------------------------------------

def cluster_by_similarity(texts: List[str], threshold: float = 0.92) -> List[int]:
    """Greedy single-pass clustering: returns a cluster id per input row, in
    input order. Near-duplicate paragraphs (cosine >= threshold) collapse to
    the same id. If embeddings aren't available, every row gets its own id
    (so nothing collapses)."""
    if not texts:
        return []
    emb = encode(texts)
    if emb is None:
        return list(range(len(texts)))

    # Embeddings are L2-normalised, so dot product == cosine similarity.
    cluster_ids: List[int] = [-1] * len(texts)
    centroids: List[np.ndarray] = []
    for i, v in enumerate(emb):
        if centroids:
            sims = np.dot(np.stack(centroids), v)
            best = int(np.argmax(sims))
            if sims[best] >= threshold:
                cluster_ids[i] = best
                continue
        cluster_ids[i] = len(centroids)
        centroids.append(v)
    return cluster_ids
