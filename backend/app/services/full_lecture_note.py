from __future__ import annotations

import json
import re
import time
from typing import Any

from openai import OpenAI

from app.config import get_settings

FULL_LECTURE_DOCUMENT_PROMPT = (
    "당신은 의대생을 위한 강의 정리본 편집자입니다. "
    "강의 전체 슬라이드와 교수님 전사문이 페이지별로 주어집니다. "
    "이를 하나의 완결된, **풍부하고 복습에 충분한** '강의 정리본' 문서로 작성하세요.\n\n"
    "문서 구조: 제목 → 핵심 요약 → 개념 구조(계층) → 표(비교·분류·정리) → 교수 강조 → 시험 문제 → 헷갈리는 포인트.\n\n"
    "규칙:\n"
    "- 슬라이드·전사문에 없는 내용은 절대 지어내지 않는다.\n"
    "- 슬라이드에 적힌 정확한 의학 용어 표기를 사용한다.\n"
    "- 그림·도표·영상은 '(슬라이드 N 그림 참고)' 또는 '(슬라이드 N 참고)'로 출처 표기.\n"
    "- **분량**: 각 섹션을 최대한 풍부하게. 강의에 나온 내용을 빠짐없이 담는다.\n"
    "- key_summary: **6~10개** bullet. 정의·핵심 메커니즘·임상 포인트·강조 사항 포함.\n"
    "- concept_structure: **4~8개** 대주제. 각 대주제에 하위 children 2~5개, "
    "items는 2~3문장으로 충분히 설명. callout_question은 교수님이 던진 질문이 있을 때.\n"
    "- comparisons (**표**): **최소 1개, 가능하면 2~4개**. 반드시 아래 유형을 적극 활용:\n"
    "  · **감별/비교 표**: A vs B (예: SIADH vs DI, 전엽 vs 후엽)\n"
    "  · **분류/목록 표**: 한 주제의 항목 나열 (예: 호르몬 | 작용 | 관련 질환)\n"
    "  · **임상 정리 표**: 증상 | 원인 | 진단 | 치료 열을 갖는 표\n"
    "  · 슬라이드에 표·도표가 있으면 그 내용을 표로 재구성하고 slide_ref를 넣는다.\n"
    "  · 비교할 대상이 없어도, 강의 핵심 개념을 정리하는 표 1개 이상은 만든다.\n"
    "- professor_highlights: **5~10개**. 교수님 발화 인용(quote) + 임상/시험 의미(explanation).\n"
    "- exam_questions: **5~8개**. 단답·빈칸·O/X·서술형 혼합.\n"
    "- confusing_points: **4~7개**. 흔한 오개념과 올바른 이해.\n"
    "- comparisons 각 항목: title, columns(헤더), rows(2차원 배열), slide_ref(정수 또는 null).\n"
    "출력은 반드시 JSON 형식:\n"
    "{\n"
    '  "title": "강의 주제 (영문 병기 가능)",\n'
    '  "key_summary": ["..."],\n'
    '  "concept_structure": [\n'
    '    {"heading": "대주제", "items": ["상세 설명..."], '
    '"children": [{"heading": "하위", "items": ["..."]}], "callout_question": "..." 또는 null}\n'
    "  ],\n"
    '  "comparisons": [\n'
    '    {"title": "SIADH vs DI", "columns": ["항목", "SIADH", "DI"], '
    '"rows": [["ADH", "↑", "↓"], ["혈청 Na", "↓", "↑"]], "slide_ref": 12}\n'
    "  ],\n"
    '  "professor_highlights": [\n'
    '    {"quote": "...", "explanation": "→ ...", "slide_ref": 12}\n'
    "  ],\n"
    '  "exam_questions": ["..."],\n'
    '  "confusing_points": ["..."]\n'
    "}"
)

_MAX_PAGE_SCRIPT_CHARS = 1800
_MAX_PAGES_IN_PROMPT = 60


def _build_lecture_context(
    pages: list[dict[str, Any]],
    page_scripts: list[list[dict[str, Any]]],
) -> str:
    blocks: list[str] = []
    for i, page in enumerate(pages[:_MAX_PAGES_IN_PROMPT]):
        page_num = page.get("page", i + 1)
        text = (page.get("text") or "").strip()
        caption = (page.get("caption") or "").strip()
        scripts = page_scripts[i] if i < len(page_scripts) else []

        script_parts: list[str] = []
        char_budget = _MAX_PAGE_SCRIPT_CHARS
        for s in scripts:
            line = s.get("corrected_text") or s.get("text") or s.get("raw_text", "")
            if not line:
                continue
            if len(line) > char_budget:
                line = line[:char_budget] + "…"
                script_parts.append(f"[{s.get('start_time', '')}] {line}")
                break
            script_parts.append(f"[{s.get('start_time', '')}] {line}")
            char_budget -= len(line)

        block = f"=== 슬라이드 {page_num} ===\n"
        if text:
            block += f"[슬라이드 텍스트]\n{text}\n"
        if caption:
            block += f"[슬라이드 시각 설명]\n{caption}\n"
        if script_parts:
            block += "[교수님 전사문]\n" + "\n".join(script_parts)
        else:
            block += "[교수님 전사문] (없음)"
        blocks.append(block)
    return "\n\n".join(blocks)


def _normalize_tables(raw: list) -> list[dict[str, Any]]:
    """표 데이터 정규화 (columns/rows/slide_ref)."""
    tables: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        columns = [str(c).strip() for c in item.get("columns", []) if str(c).strip()]
        rows_raw = item.get("rows") or []
        rows: list[list[str]] = []
        for row in rows_raw:
            if isinstance(row, list):
                rows.append([str(c).strip() for c in row])
        if not title and not columns and not rows:
            continue
        slide_ref = item.get("slide_ref")
        tables.append(
            {
                "title": title or "정리 표",
                "columns": columns,
                "rows": rows,
                "slide_ref": int(slide_ref) if slide_ref is not None else None,
            }
        )
    return tables


def _parse_document(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    data = json.loads(content)
    return {
        "title": str(data.get("title", "강의 정리본")).strip() or "강의 정리본",
        "key_summary": [str(x).strip() for x in data.get("key_summary", []) if str(x).strip()],
        "concept_structure": data.get("concept_structure") or [],
        "comparisons": _normalize_tables(data.get("comparisons") or []),
        "professor_highlights": data.get("professor_highlights") or [],
        "exam_questions": [str(x).strip() for x in data.get("exam_questions", []) if str(x).strip()],
        "confusing_points": [
            str(x).strip() for x in data.get("confusing_points", []) if str(x).strip()
        ],
    }


def generate_full_lecture_document(
    pages: list[dict[str, Any]],
    page_scripts: list[list[dict[str, Any]]],
    system_prompt: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_text_model:
        return {}

    context = _build_lecture_context(pages, page_scripts)
    if not context.strip():
        return {}

    user_prompt = (
        f"아래는 강의 전체 슬라이드와 교수님 전사문입니다.\n\n"
        f"{context}\n\n"
        "위 내용 전체를 바탕으로, 의대생 복습용 **풍부한** 강의 정리본을 작성하세요.\n"
        "- 그림·도표는 '(슬라이드 N 그림 참고)'로 표기.\n"
        "- **표(comparisons)를 2~4개** 적극 활용: 비교표, 분류표, 임상 정리표 등.\n"
        "- 각 섹션 분량 가이드(핵심 요약 6~10개, 개념 구조 4~8개 대주제)를 지키세요."
    )

    client = OpenAI(api_key=settings.openai_api_key)
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.openai_text_model,
                max_completion_tokens=128000,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt or FULL_LECTURE_DOCUMENT_PROMPT,
                    },
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if content:
                doc = _parse_document(content)
                doc["subtitle"] = "강의 정리본 · 자동 생성 · 1Q"
                return doc
            return {}
        except Exception:
            if attempt == 1:
                return {}
            time.sleep(2**attempt)
    return {}
