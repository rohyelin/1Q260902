from __future__ import annotations

import re
import time
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any

from openai import OpenAI

from app.config import get_settings

TOKEN_RE = re.compile(r"[A-Za-z가-힣][A-Za-z가-힣0-9\-]*")
UPPER_ABBR_RE = re.compile(r"\b[A-Z]{2,}\b")
HYPHEN_TERM_RE = re.compile(r"[\w가-힣]+-[\w가-힣]+")
EN_WORD_RE = re.compile(r"[A-Za-z]{3,}")
KO_WORD_RE = re.compile(r"[가-힣]{2,}")

STOPWORDS = {
    "그리고",
    "하는",
    "있는",
    "대한",
    "위해",
    "에서",
    "으로",
    "이다",
    "합니다",
    "있습니다",
    "같은",
    "이런",
    "오늘",
    "다음",
    "먼저",
    "정도",
    "때문",
    "그래서",
    "하지만",
    "the",
    "and",
    "for",
    "with",
}

CORRECTION_SYSTEM_PROMPT = (
    "당신은 의학 강의 음성 전사 교정 전문가입니다. "
    "발음 오인식으로 잘못 적힌 단어만 문맥과 용어집을 참고해 교정하세요. "
    "특히 강의록에 나오는 의학 용어(예: 연합증→연화증)는 용어집을 우선해 바로잡으세요. "
    "의미를 추가하거나 삭제하지 마세요. 문장 구조는 최대한 유지하세요. "
    "교정된 문장만 출력하세요."
)

CORRECTION_BATCH_SYSTEM_PROMPT = (
    "당신은 의학 강의 음성 전사 교정 전문가입니다. "
    "여러 구간으로 나뉜 한 강의의 전사 전체가 주어집니다. "
    "강의 전체 맥락과 용어집을 참고해 발음 오인식으로 잘못 적힌 단어를 교정하세요. "
    "말투(구어체)는 그대로 두고 단어만 바로잡으며, 문맥상 명백한 의학 용어는 "
    "적극적으로 교정하되 없는 내용을 새로 지어내지는 마세요. "
    "각 구간의 번호를 그대로 유지하고, 교정된 문장만 담아 JSON 객체로 반환하세요."
)

# 이비인후과/후두 도메인 시드 용어. PDF에서 못 뽑히거나 분해가 안 되는 핵심어를
# 미리 넣어 fuzzy·LLM 교정과 요약이 항상 올바른 표기를 쓰도록 한다.
SEED_TERMS = [
    "후두", "후두경", "후두경검사", "후두연화증", "후두개염", "후두개",
    "성대", "성대마비", "성대결절", "성문", "성문하", "성문하협착",
    "연화증", "협착", "협착증", "기관절개술", "윤상연골", "갑상연골",
    "피열연골", "아리테노이드", "크리코이드", "인두", "하인두", "구인두",
    "비인두", "역류", "인후두역류질환", "연골", "점막", "종양", "낭종",
    "육아종", "유두종", "쉰목소리", "애성", "연하", "연하곤란", "흡기",
    "천명", "청진",
    # 영어 약어/용어
    "HPV", "LPRD", "LMS", "TSH", "MRI", "CT",
    "Laryngomalacia", "Laryngoscopy", "Laryngoscope", "Epiglottitis",
    "Subglottic", "stenosis", "Vocal", "fold", "paralysis", "Larynx",
    "Stroboscopy", "Dysphagia", "Dyspnea", "Hoarseness", "Stridor",
]

# 의학 복합어를 분해할 때 남길 접미사(머리명사)
MED_SUFFIXES = ("연화증", "협착증", "협착", "결절", "마비", "종양", "낭종", "염", "증", "술", "암", "종")


def _decompose_medical_term(term: str) -> list[str]:
    """복합 의학용어에서 의미 있는 하위어를 추출한다.

    예: '후두연화증' -> ['연화증'], '성문하협착' -> ['협착'].
    전사에서는 앞 수식어 없이 머리명사만 말하는 경우가 많아 매칭에 도움된다.
    """
    subs: list[str] = []
    for suf in MED_SUFFIXES:
        if len(term) > len(suf) + 1 and term.endswith(suf):
            # 접미사를 포함한 뒤쪽 3~4글자 조각
            for size in (len(suf), len(suf) + 1, len(suf) + 2):
                if 3 <= size < len(term):
                    subs.append(term[-size:])
            break
    return subs


def build_glossary(pages: list[dict[str, Any]], max_terms: int = 800) -> list[str]:
    # 항상 유지할 우선 용어(시드 + 복합어 분해). 컷오프에 잘리지 않게 별도 관리.
    priority: set[str] = set(SEED_TERMS)
    terms: set[str] = set()
    for page in pages:
        text = page.get("text", "")
        caption = page.get("caption", "")
        combined = f"{text}\n{caption}"
        terms.update(UPPER_ABBR_RE.findall(combined))
        terms.update(HYPHEN_TERM_RE.findall(combined))
        terms.update(EN_WORD_RE.findall(combined))
        ko_terms = KO_WORD_RE.findall(combined)
        terms.update(ko_terms)
        for kt in ko_terms:
            priority.update(_decompose_medical_term(kt))

    def keep(t: str) -> bool:
        return t.lower() not in STOPWORDS and len(t) >= 2 and not t.isdigit()

    priority_list = sorted((t for t in priority if keep(t)), key=lambda x: (-len(x), x.lower()))
    rest = sorted((t for t in terms - priority if keep(t)), key=lambda x: (-len(x), x.lower()))
    combined_terms = priority_list + rest
    return combined_terms[:max_terms]


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _same_med_suffix(a: str, b: str) -> str | None:
    for suf in MED_SUFFIXES:
        if a.endswith(suf) and b.endswith(suf):
            return suf
    return None


def fuzzy_correct_text(text: str, glossary: list[str], threshold: float = 0.78) -> str:
    if not text or not glossary:
        return text

    tokens = TOKEN_RE.findall(text)
    glossary_set = set(glossary)
    replacements: dict[str, str] = {}

    for token in tokens:
        if len(token) < 2 or token in replacements:
            continue
        # 이미 사전에 있는 올바른 용어는 절대 바꾸지 않는다
        # (예: '후두개염'을 '후두염'으로 오교정하는 것 방지).
        if token in glossary_set:
            continue
        best_term: str | None = None
        best_ratio = threshold
        for term in glossary:
            if term == token:
                continue
            if abs(len(term) - len(token)) > 3:
                continue
            ratio = _similarity(token, term)
            # 같은 의학 접미사(증/염/술 등)를 공유하면 임계값을 낮춘다.
            # 예: '연합증' vs '연화증' (앞 글자만 다른 오인식)
            suf = _same_med_suffix(token, term)
            eff_threshold = best_ratio
            floor = 0.6
            if suf and len(token) >= 3:
                # 접미사가 짧을수록(증/염) 오검 위험이 크므로 하한을 높인다.
                floor = 0.62 if len(suf) == 1 else 0.58
                eff_threshold = min(best_ratio, floor)
            if ratio > eff_threshold and ratio >= floor:
                best_ratio = ratio
                best_term = term
        if best_term:
            replacements[token] = best_term

    result = text
    for old in sorted(replacements, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(old)}\b", replacements[old], result)
        if old not in result and old in text:
            result = result.replace(old, replacements[old])
    return result


def fuzzy_correct_chunks(
    chunks: list[dict[str, Any]], glossary: list[str]
) -> list[dict[str, Any]]:
    for chunk in chunks:
        chunk.setdefault("raw_text", chunk["text"])
        chunk["text"] = fuzzy_correct_text(chunk["text"], glossary)
        chunk["fuzzy_corrected_text"] = chunk["text"]
    return chunks


def _format_glossary_snippet(glossary: list[str], limit: int = 80) -> str:
    return ", ".join(glossary[:limit])


def llm_correct_chunk(
    text: str,
    *,
    prev_text: str = "",
    next_text: str = "",
    glossary: list[str],
) -> str:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_text_model:
        return text

    client = OpenAI(api_key=settings.openai_api_key)
    user_prompt = (
        f"참고 용어집: {_format_glossary_snippet(glossary)}\n\n"
        f"이전 문맥: {prev_text[:400] if prev_text else '(없음)'}\n"
        f"다음 문맥: {next_text[:400] if next_text else '(없음)'}\n\n"
        f"교정할 문장:\n{text}"
    )

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.openai_text_model,
                messages=[
                    {"role": "system", "content": CORRECTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            return content.strip() if content else text
        except Exception:
            if attempt == 1:
                return text
            time.sleep(2**attempt)
    return text


def llm_correct_chunks(
    chunks: list[dict[str, Any]],
    glossary: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_text_model:
        return chunks

    from app.services.parallel import parallel_map

    # 문맥은 fuzzy 교정본(현재 text) 기준으로 스냅샷 → 병렬 처리해도 안정적.
    snapshot = [c["text"] for c in chunks]
    total = len(chunks)

    def work(i: int, _c: dict[str, Any]) -> str:
        prev_text = snapshot[i - 1] if i > 0 else ""
        next_text = snapshot[i + 1] if i + 1 < total else ""
        return llm_correct_chunk(
            snapshot[i],
            prev_text=prev_text,
            next_text=next_text,
            glossary=glossary,
        )

    corrected = parallel_map(work, chunks, on_progress=on_progress)
    for chunk, text in zip(chunks, corrected):
        chunk["text"] = text
    return chunks


def _parse_corrected_json(content: str, count: int, fallback: list[str]) -> list[str]:
    """모델이 돌려준 JSON({"1": "...", ...})을 인덱스 순서 리스트로 변환. 실패 시 원문 유지."""
    import json

    content = (content or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lstrip().lower().startswith("json"):
            content = content.lstrip()[4:]
    try:
        data = json.loads(content)
    except Exception:
        return fallback
    result: list[str] = []
    for i in range(count):
        val = data.get(str(i + 1)) if isinstance(data, dict) else None
        result.append(val.strip() if isinstance(val, str) and val.strip() else fallback[i])
    return result


def llm_correct_all_chunks(
    chunks: list[dict[str, Any]],
    glossary: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """전사 전체를 한 번의 호출로, 강의 전체 맥락을 보며 교정한다.
    조각 경계(타임스탬프)는 유지한 채 각 조각의 교정문만 받아온다."""
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_text_model or not chunks:
        return chunks

    client = OpenAI(api_key=settings.openai_api_key)
    glossary_snippet = _format_glossary_snippet(glossary, limit=300)
    originals = [c["text"] for c in chunks]
    numbered = "\n".join(f"[{i + 1}] {t}" for i, t in enumerate(originals))
    user_prompt = (
        f"참고 용어집: {glossary_snippet}\n\n"
        "아래는 한 강의 전사의 연속된 구간 전체다. 전체 흐름과 용어집을 참고해 "
        "발음 오인식으로 잘못 적힌 부분을 교정하라. 각 구간의 번호는 그대로 유지하고, "
        '교정된 문장만 담아 JSON으로 반환하라. 형식: {"1": "...", "2": "..."}\n\n'
        f"{numbered}"
    )

    corrected = originals
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=settings.openai_text_model,
                messages=[
                    {"role": "system", "content": CORRECTION_BATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=128000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            corrected = _parse_corrected_json(content or "", len(chunks), originals)
            break
        except Exception:
            if attempt == 1:
                corrected = originals
            else:
                time.sleep(2**attempt)

    for c, text in zip(chunks, corrected):
        c["text"] = text
    if on_progress:
        on_progress(len(chunks), len(chunks))
    return chunks


def correct_transcript(
    chunks: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    on_progress: Callable[[int, str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    glossary = build_glossary(pages)
    if not glossary:
        warnings.append("PDF에서 교정용 용어집을 추출하지 못했습니다.")

    chunks = fuzzy_correct_chunks(chunks, glossary)

    settings = get_settings()
    if settings.openai_api_key and settings.openai_text_model:
        def llm_progress(done: int, total: int) -> None:
            if on_progress:
                pct = int(done / max(total, 1) * 100)
                on_progress(pct, f"전사문 LLM 교정 중 ({done}/{total})")

        chunks = llm_correct_all_chunks(chunks, glossary, on_progress=llm_progress)
    else:
        warnings.append("OPENAI_TEXT_MODEL이 없어 LLM 교정 단계를 건너뜁니다.")

    return chunks, warnings
