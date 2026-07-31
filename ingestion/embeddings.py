"""Embedding du texte d'une page via Vertex AI (modèle multilingue, le document est en français)."""
from __future__ import annotations

import numpy as np
from google import genai
from google.genai import types


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    return vector / norm if norm > 0 else vector


def embed_text(client: genai.Client, model: str, text: str) -> np.ndarray:
    response = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    vector = np.array(response.embeddings[0].values, dtype=np.float32)
    return _normalize(vector)
