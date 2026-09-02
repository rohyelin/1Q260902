from __future__ import annotations

import base64
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import get_settings

CAPTION_PROMPT = (
    "이 이미지는 의학 대학 강의 슬라이드입니다. "
    "슬라이드에 보이는 핵심 주제, 해부 구조, 도식, 영어 약어, 질병명, 수치를 "
    "한국어로 3~6문장으로 설명하세요. "
    "슬라이드에 없는 내용은 추측하지 마세요. "
    "텍스트가 거의 없는 제목/구분 슬라이드면 그 사실도 포함하세요."
)

SPARSE_TEXT_THRESHOLD = 200


def _encode_image(image_path: str) -> str:
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


def caption_page_image(image_path: str, page_text: str = "") -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        return ""

    model = settings.openai_vision_model or settings.openai_text_model
    if not model:
        return ""

    client = OpenAI(api_key=settings.openai_api_key)
    b64 = _encode_image(image_path)
    hint = f"\n슬라이드에서 추출된 텍스트: {page_text[:300]}" if page_text else ""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": CAPTION_PROMPT + hint},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}",
                                    "detail": "low",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=350,
                temperature=0.2,
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception:
            if attempt == 1:
                return ""
            time.sleep(2**attempt)
    return ""


def caption_pages(
    pages: list[dict[str, Any]],
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    settings = get_settings()
    if not settings.openai_api_key:
        warnings.append("OPENAI_API_KEY가 없어 슬라이드 vision caption을 건너뜁니다.")
        return pages, warnings

    model = settings.openai_vision_model or settings.openai_text_model
    if not model:
        warnings.append("OPENAI_VISION_MODEL 또는 OPENAI_TEXT_MODEL이 없어 caption을 건너뜁니다.")
        return pages, warnings

    from app.services.parallel import parallel_map

    total = len(pages)

    def work(_i: int, page: dict[str, Any]) -> str:
        # 텍스트가 충분하거나 이미지가 없으면 caption 불필요
        text_len = len(page.get("text", ""))
        image_path = page.get("image_path", "")
        if not image_path or not Path(image_path).exists():
            return ""
        if text_len >= SPARSE_TEXT_THRESHOLD:
            return ""
        return caption_page_image(image_path, page.get("text", ""))

    def progress(done: int, _n: int) -> None:
        if on_progress:
            on_progress(done, total, f"슬라이드 vision caption ({done}/{total})")

    captions = parallel_map(work, pages, on_progress=progress)

    for page, caption in zip(pages, captions):
        text_len = len(page.get("text", ""))
        page["caption"] = caption
        if caption:
            page["embedding_text"] = (
                f"{page['text']}\n\n[슬라이드 시각 설명]\n{caption}".strip()
            )
        else:
            page["embedding_text"] = page["text"]
            if text_len < 30 and page.get("image_path"):
                warnings.append(
                    f"페이지 {page['page']}: 텍스트가 적고 vision caption도 생성되지 않았습니다."
                )

    return pages, warnings


def get_page_embedding_texts(pages: list[dict[str, Any]]) -> list[str]:
    return [p.get("embedding_text") or p.get("text", "") for p in pages]
