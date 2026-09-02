from __future__ import annotations

import re

DEFAULT_KEYWORDS = [
    "중요",
    "시험",
    "기억",
    "출제",
    "나올 수",
    "핵심",
    "주의",
    "반드시",
    "외워",
    "헷갈",
]


def find_highlights(text: str, keywords: list[str] | None = None) -> list[str]:
    kw_list = keywords or DEFAULT_KEYWORDS
    found: list[str] = []
    for kw in kw_list:
        if kw in text and kw not in found:
            found.append(kw)
    return found
