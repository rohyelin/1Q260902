from __future__ import annotations

import json
import time

from openai import OpenAI

from app.config import get_settings

POLISH_PROMPT = (
    "다음은 교수님의 강의 음성 전사문입니다. 구어체 표현을 자연스러운 문어체 강의노트 문장으로 바꾸세요. "
    "의미를 추가하거나 삭제하지 마세요. 전문 용어, 영어 약어, 수식, 숫자는 보존하세요. "
    "학생이 복습할 수 있는 문장으로만 다듬으세요. 원문에 없는 내용을 추측하지 마세요."
)

POLISH_BATCH_PROMPT = (
    "당신은 강의 노트 편집자입니다. 여러 구간으로 나뉜 교정된 강의 전사가 주어집니다. "
    "각 구간의 구어체 문장을 자연스러운 문어체 강의노트 문장으로 다듬으세요. "
    "의미를 추가·삭제하지 말고, 전문 용어·영어 약어·수식·숫자는 보존하세요. "
    "각 구간의 번호를 그대로 유지하고, 다듬은 문장만 담아 JSON 객체로 반환하세요."
)

# 한 호출당 구간 수 (출력 토큰 한도·JSON 안정성 위해 제한). 넘으면 나눠 병렬 호출.
_POLISH_BATCH_SIZE = 40


def _resolve_model() -> str:
    settings = get_settings()
    return settings.openai_readability_model or settings.openai_text_model


def _polish_one_batch(client: OpenAI, model: str, texts: list[str]) -> list[str]:
    """구간 묶음 하나를 한 번의 호출로 문어체 변환. 실패 시 원문 유지."""
    numbered = "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(texts))
    user_prompt = (
        "아래 각 구간의 문장을 문어체 강의노트체로 다듬어라. "
        '번호를 유지하고 JSON으로 반환하라. 형식: {"1": "...", "2": "..."}\n\n'
        f"{numbered}"
    )
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                max_completion_tokens=16000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": POLISH_BATCH_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            data = json.loads(response.choices[0].message.content or "{}")
            out: list[str] = []
            for i in range(len(texts)):
                v = data.get(str(i + 1)) if isinstance(data, dict) else None
                out.append(v.strip() if isinstance(v, str) and v.strip() else texts[i])
            return out
        except Exception:
            if attempt == 1:
                return list(texts)
            time.sleep(2**attempt)
    return list(texts)


def polish_texts(texts: list[str]) -> list[str]:
    """매칭된 스크립트를 문어체로 다듬는다. 40개씩 나눠 병렬 호출."""
    settings = get_settings()
    model = _resolve_model()
    if not settings.openai_api_key or not model or not texts:
        return list(texts)

    client = OpenAI(api_key=settings.openai_api_key)
    batches = [
        texts[i : i + _POLISH_BATCH_SIZE] for i in range(0, len(texts), _POLISH_BATCH_SIZE)
    ]
    if len(batches) == 1:
        return _polish_one_batch(client, model, batches[0])

    from app.services.parallel import parallel_map

    def _work(_idx: int, batch: list[str]) -> list[str]:
        return _polish_one_batch(client, model, batch)

    results = parallel_map(_work, batches)
    out: list[str] = []
    for r in results:
        out.extend(r)
    return out


def polish_text(raw_text: str) -> str:
    """단일 텍스트 문어체 변환 (호환용)."""
    settings = get_settings()
    model = _resolve_model()
    if not settings.openai_api_key or not model:
        return raw_text

    client = OpenAI(api_key=settings.openai_api_key)
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": POLISH_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
            )
            content = response.choices[0].message.content
            return content.strip() if content else raw_text
        except Exception:
            if attempt == 1:
                return raw_text
            time.sleep(2**attempt)
    return raw_text
