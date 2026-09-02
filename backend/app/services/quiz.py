from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI

from app.config import get_settings

QUIZ_SYSTEM_PROMPT = (
    "당신은 의대생을 위한 강의 복습 퀴즈 출제자입니다. "
    "특정 강의 슬라이드와, 그 슬라이드를 설명하는 동안 교수님이 실제로 말한 전사문이 주어집니다. "
    "전사문과 슬라이드 내용을 근거로, 학생이 스스로 복습할 수 있는 퀴즈를 만드세요.\n\n"
    "규칙:\n"
    "- 문제는 반드시 슬라이드/전사문에 실제로 나온 내용만 근거로 한다(외부 지식으로 지어내지 않는다).\n"
    "- 슬라이드에 적힌 정확한 의학 용어 표기를 사용한다.\n"
    "- 단답형, 빈칸 채우기, O/X, 짧은 서술형을 섞어서 출제한다.\n"
    "- 교수님이 '시험에 나온다', '중요하다'고 강조한 내용은 우선적으로 출제하고 문제 끝에 (⭐중요) 표시.\n"
    "- 각 문제에는 반드시 명확한 정답을 함께 제공한다. 정답은 1~2문장으로 간결하게.\n"
    "- 요청된 문제 수를 정확히 지킨다.\n"
    "- 관련 발화가 거의 없으면 빈 목록을 반환한다.\n"
    "출력은 반드시 JSON 형식: "
    "{\"questions\": [{\"question\": \"...\", \"answer\": \"...\"}, ...]}"
)


def _num_questions(scripts: list[dict[str, Any]]) -> int:
    """매칭된 스크립트 분량에 비례해 문제 수를 정한다 (1~6개)."""
    total_chars = sum(
        len(s.get("corrected_text") or s.get("text") or s.get("raw_text", ""))
        for s in scripts
    )
    if total_chars < 80:
        return 0
    return max(1, min(6, 1 + total_chars // 400))


def _extract_questions(content: str) -> list[dict[str, str]]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        data = json.loads(content)
        items = data.get("questions", [])
        result = []
        for it in items:
            q = str(it.get("question", "")).strip()
            a = str(it.get("answer", "")).strip()
            if q:
                result.append({"question": q, "answer": a})
        return result
    except (json.JSONDecodeError, AttributeError):
        return []


def generate_quiz(
    page_text: str,
    caption: str,
    scripts: list[dict[str, Any]],
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_text_model:
        return []
    if not scripts:
        return []

    n_questions = _num_questions(scripts)
    if n_questions == 0:
        return []

    script_text = "\n".join(
        f"[{s.get('start_time', '')}] {s.get('corrected_text') or s.get('text') or s.get('raw_text', '')}"
        for s in scripts
    ).strip()
    if not script_text:
        return []

    slide_info = f"슬라이드 텍스트:\n{page_text.strip()}"
    if caption:
        slide_info += f"\n\n슬라이드 시각 설명:\n{caption.strip()}"

    user_prompt = (
        f"{slide_info}\n\n"
        f"이 슬라이드를 설명할 때 교수님의 전사문:\n{script_text}\n\n"
        f"위 내용을 바탕으로 복습 퀴즈를 정확히 {n_questions}개 만드세요. "
        "각 문제에 정답을 반드시 포함하세요."
    )

    client = OpenAI(api_key=settings.openai_api_key)
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.openai_text_model,
                max_completion_tokens=16000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt or QUIZ_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            return _extract_questions(content) if content else []
        except Exception:
            if attempt == 1:
                return []
            time.sleep(2**attempt)
    return []
