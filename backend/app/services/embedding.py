from __future__ import annotations

import time
from typing import Optional

import numpy as np
import tiktoken
from openai import OpenAI

from app.config import get_settings

# 모델별 임베딩 차원. large는 3072, small/ada는 1536.
# (모델을 바꾸면 결과 배열 폭도 여기에 맞춰 잡아야 broadcast 에러가 안 난다.)
_MODEL_DIMS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}
DEFAULT_EMBEDDING_DIM = 1536


def _embedding_dim(model: str) -> int:
    return _MODEL_DIMS.get(model, DEFAULT_EMBEDDING_DIM)


# text-embedding-3 계열은 한 번에 최대 8192 토큰까지만 받는다. 여유를 두고 8000으로 자른다.
MAX_EMBEDDING_TOKENS = 8000
_ENCODER = tiktoken.get_encoding("cl100k_base")


def _truncate_to_token_limit(text: str, max_tokens: int = MAX_EMBEDDING_TOKENS) -> str:
    """글이 임베딩 모델의 토큰 한도를 넘으면 앞부분만 잘라서 돌려준다."""
    tokens = _ENCODER.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _ENCODER.decode(tokens[:max_tokens])


def _require_api_key() -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY가 설정되지 않아 페이지-스크립트 매칭을 수행할 수 없습니다."
        )
    return settings.openai_api_key


def _normalize_text(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def _embed_batch(client: OpenAI, texts: list[str], model: str) -> list[list[float]]:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(input=texts, model=model)
            return [item.embedding for item in response.data]
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2**attempt)
    return []


def embed_texts(texts: list[str]) -> np.ndarray:
    api_key = _require_api_key()
    settings = get_settings()
    client = OpenAI(api_key=api_key)
    model = settings.openai_embedding_model

    dim = _embedding_dim(model)
    normalized = [_truncate_to_token_limit(_normalize_text(t)) for t in texts]
    non_empty_indices = [i for i, t in enumerate(normalized) if t.strip()]
    result = np.zeros((len(texts), dim), dtype=np.float32)

    if not non_empty_indices:
        return result

    batch_size = 64
    for start in range(0, len(non_empty_indices), batch_size):
        batch_indices = non_empty_indices[start : start + batch_size]
        batch_texts = [normalized[i] for i in batch_indices]
        embeddings = _embed_batch(client, batch_texts, model)
        for idx, emb in zip(batch_indices, embeddings):
            result[idx] = np.array(emb, dtype=np.float32)

    return result


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return matrix / norms


def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_norm = l2_normalize(a)
    b_norm = l2_normalize(b)
    return a_norm @ b_norm.T
