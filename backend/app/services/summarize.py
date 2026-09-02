from __future__ import annotations

import json
import time
from typing import Any

from openai import OpenAI

from app.config import get_settings


class SummaryFailed(RuntimeError):
    """요약 생성이 재시도 후에도 실패했음을 알린다.

    예전에는 실패해도 빈 리스트를 돌려줘서, 속도 제한 한 번에 뒷부분 슬라이드의
    핵심 정리가 통째로 사라져도 아무도 몰랐다.
    """


SUMMARY_SYSTEM_PROMPT = (
    "당신은 의대생을 위한 강의 노트 정리 도우미입니다. "
    "교수님이 강의하며 실제로 말한 전사문이 주어집니다. "
    "전사문에서 교수님이 강조·설명·비교·예시로 든 내용을 "
    "복습용 개조식 노트로 풍부하게 정리하세요.\n\n"
    "규칙:\n"
    "- 각 항목은 명사형 종결체('~함.', '~임.', '~됨.', '~해야 함.')로 끝낸다.\n"
    "- 의학 용어는 정확한 표기를 사용한다.\n"
    "- 전사문에 없는 내용은 절대 지어내지 않는다.\n"
    "- 교수님이 '시험에 나온다', '중요하다'고 언급한 부분은 항목 끝에 (⭐중요) 표시.\n"
    "- 교수님이 든 **구체적 예시**(증례, 임상 상황, 비유, 숫자, '~하면 ~한다' 식 설명)는 "
    "반드시 별도 항목으로 포함하고, 항목 앞에 '예)' 접두어를 붙인다. "
    "예: '예) 신생아에서 inspiratory stridor가 수면·식사 시 악화됨.'\n"
    "- 교수님이 A와 B를 **비교**했으면 'A vs B: ...' 형식으로 정리한다.\n"
    "- 정의, 원인, 증상, 진단, 치료, 강조 포인트, 주의사항 등 강의 주제와 관련된 "
    "내용을 빠짐없이 담아 **5~10개** 항목으로 작성한다(관련 내용이 많으면 10개까지).\n"
    "- 관련 발화가 거의 없으면 빈 목록을 반환한다.\n"
    "출력은 반드시 JSON 형식: {\"points\": [\"...\", \"...\"]}"
)


FULL_NOTE_SYSTEM_PROMPT = (
    "당신은 의대생을 위한 강의 정리본 작성자입니다. "
    "특정 강의 슬라이드와, 그 슬라이드를 설명하는 동안 교수님이 실제로 말한 전사문이 주어집니다. "
    "슬라이드 내용과 교수님 설명을 통합해, 이 슬라이드 부분의 '완결된 정리본'을 작성하세요. "
    "각 슬라이드의 정리본을 이어 붙이면 강의 전체의 완성된 학습 노트가 되어야 합니다.\n\n"
    "규칙:\n"
    "- 슬라이드에 적힌 내용을 뼈대로 삼고, 교수님이 덧붙인 설명·예시·강조를 살로 붙인다.\n"
    "- 슬라이드에만 있고 교수님이 언급하지 않은 항목도 정리본에 포함한다(정리본은 완결성이 중요).\n"
    "- 개념 정의 → 상세 설명 → 예시/임상 포인트 순으로 자연스럽게 배치한다.\n"
    "- 각 항목은 명사형 종결체('~함.', '~임.', '~됨.')로 끝내되, 필요하면 2~3문장으로 충분히 설명한다.\n"
    "- 하위 개념은 항목 앞에 '- ' 를 붙여 들여쓰기 구조를 표현한다.\n"
    "- 교수님이 든 구체적 예시는 '예)' 접두어로 별도 항목 처리한다.\n"
    "- '시험에 나온다', '중요하다' 강조 부분은 항목 끝에 (⭐중요) 표시.\n"
    "- 슬라이드에 적힌 정확한 의학 용어 표기를 사용한다.\n"
    "- 슬라이드/전사문에 없는 내용은 절대 지어내지 않는다.\n"
    "- 분량 제한 없음. 슬라이드 내용을 빠짐없이 커버한다.\n"
    "출력은 반드시 JSON 형식: {\"points\": [\"...\", \"...\"]}"
)


def _extract_points(content: str) -> list[str]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    try:
        data = json.loads(content)
        points = data.get("points", [])
        return [str(p).strip() for p in points if str(p).strip()]
    except (json.JSONDecodeError, AttributeError):
        lines = [ln.strip("-• \t") for ln in content.splitlines() if ln.strip()]
        return [ln for ln in lines if len(ln) > 2][:10]


def summarize_page(
    page_text: str,
    caption: str,
    scripts: list[dict[str, Any]],
    system_prompt: str | None = None,
    require_scripts: bool = True,
) -> list[str]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_text_model:
        return []
    if not scripts and require_scripts:
        return []

    script_text = "\n".join(
        f"[{s.get('start_time', '')}] {s.get('corrected_text') or s.get('text') or s.get('raw_text', '')}"
        for s in scripts
    ).strip()
    if not script_text:
        if require_scripts:
            return []
        if not page_text.strip():
            return []
        script_text = "(이 슬라이드에 대한 교수님 발화 없음 — 슬라이드 내용만으로 정리)"

    user_prompt = (
        f"교수님의 강의 전사문:\n{script_text}\n\n"
        "위 전사문에서 교수님이 강조·설명·비교·예시로 든 핵심 내용을 개조식으로 정리하세요. "
        "교수님이 말한 구체적 예시·비교·임상 포인트가 있으면 '예)' 항목으로 반드시 포함하세요."
    )

    client = OpenAI(api_key=settings.openai_api_key)
    last_error: Exception | None = None
    # 재시도를 넉넉히 준다. 예전엔 2번만 시도하고 조용히 빈 값을 돌려줘서,
    # 속도 제한(429) 한 번에 뒷부분 슬라이드 정리가 통째로 사라졌다.
    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=settings.openai_summary_model or settings.openai_text_model,
                max_completion_tokens=16000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt or SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            return _extract_points(content) if content else []
        except Exception as exc:  # noqa: BLE001 - 마지막에 원인을 알려주기 위해 보관
            last_error = exc
            if attempt < 3:
                time.sleep(2**attempt)

    # 실패를 삼키지 않는다. 호출한 쪽에서 어떤 슬라이드가 비었는지 알려줘야 한다.
    raise SummaryFailed(str(last_error) if last_error else "알 수 없는 오류")
