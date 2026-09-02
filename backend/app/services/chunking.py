from __future__ import annotations

from typing import Any

from app.services.transcribe import seconds_to_hhmmss

# 가변 chunk 경계 기준.
# 고정 길이로 자르지 않고, 교수님의 발화 사이 "침묵(pause)"을 1차 경계로 삼는다.
# 길이 관련 값들은 하드 가드레일일 뿐 목표치가 아니다.
HARD_MIN_DURATION = 8.0     # 이보다 짧은 chunk는 큰 침묵이 있을 때만 허용
SOFT_MIN_DURATION = 12.0    # 이 이상이면 침묵/문장경계에서 자유롭게 끊음
TARGET_DURATION = 35.0      # 침묵이 없어도 이쯤이면 끊는 fallback
MAX_DURATION = 75.0         # 하드 상한
MAX_CHARS = 650             # 하드 상한

GAP_SPLIT = 0.8             # 이 이상 침묵이면 경계 후보
BIG_GAP = 1.6               # 이 이상 침묵이면 강한 경계(짧아도 끊음)
SENTENCE_ENDINGS = ("다.", "요.", "죠.", "다", "요", "죠", ".", "?", "!")

# ── A-1: 문장 단위 분할 (녹음본 경로) ──────────────────────────────
# transcript_ingest.py 와 같은 이유로, 조각을 문장 단위까지 내린다.
# 문장이 끝나고 최소 길이만 넘으면 바로 끊는다. 위의 TARGET/MAX 값들은
# 문장 종결부호가 오래 안 나올 때를 위한 가드레일로만 남는다.
SENTENCE_LEVEL = True
SENTENCE_MIN_DURATION = 2.0   # 이보다 짧은 조각은 다음 문장과 합침
SENTENCE_MIN_CHARS = 20


def _ends_sentence(text: str) -> bool:
    t = text.rstrip()
    return t.endswith(SENTENCE_ENDINGS)


def _make_chunk(chunk_id: int, seg_ids: list[int], texts: list[str], start: float, end: float) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "start": start,
        "end": end,
        "start_time": seconds_to_hhmmss(start),
        "end_time": seconds_to_hhmmss(end),
        "text": " ".join(texts).strip(),
        "segment_ids": list(seg_ids),
    }


def chunk_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """침묵/문장경계 기반 가변 길이 chunking.

    슬라이드별 설명 길이가 제각각이므로 고정 길이 대신 자연 경계에서 자른다.
    - 발화 사이 침묵(GAP_SPLIT)이 있고 충분히 쌓였으면 경계로 삼는다.
    - 큰 침묵(BIG_GAP)은 짧은 chunk라도 경계로 삼는다(주제 전환 가능성).
    - 침묵이 없으면 TARGET/문장경계, 최후엔 MAX로 강제 분할한다.
    """
    if not segments:
        return []

    chunks: list[dict[str, Any]] = []
    seg_ids: list[int] = []
    texts: list[str] = []
    start: float | None = None
    end = 0.0

    n = len(segments)
    for i, seg in enumerate(segments):
        if start is None:
            start = seg["start"]
        seg_ids.append(seg["segment_id"])
        texts.append(seg["text"])
        end = seg["end"]

        duration = end - start
        char_count = sum(len(t) for t in texts) + len(texts)

        # 다음 세그먼트까지의 침묵
        gap = segments[i + 1]["start"] - end if i + 1 < n else 0.0
        is_last = i + 1 >= n

        should_split = False
        if duration >= MAX_DURATION or char_count >= MAX_CHARS:
            should_split = True
        elif SENTENCE_LEVEL and _ends_sentence(seg["text"]) and (
            duration >= SENTENCE_MIN_DURATION or char_count >= SENTENCE_MIN_CHARS
        ):
            # 문장이 끝났고 토막이 아니면 바로 끊는다 (슬라이드 경계를 문장까지 좁히기 위해)
            should_split = True
        elif gap >= BIG_GAP and duration >= HARD_MIN_DURATION:
            should_split = True
        elif gap >= GAP_SPLIT and duration >= SOFT_MIN_DURATION:
            should_split = True
        elif duration >= TARGET_DURATION and _ends_sentence(seg["text"]):
            should_split = True

        if should_split and not is_last:
            chunks.append(_make_chunk(len(chunks), seg_ids, texts, start, end))
            seg_ids = []
            texts = []
            start = None

    if seg_ids and start is not None:
        text = " ".join(texts).strip()
        if text:
            # 마지막 조각이 너무 짧으면 직전 chunk에 합친다.
            if chunks and (end - start) < HARD_MIN_DURATION:
                prev = chunks[-1]
                prev["segment_ids"].extend(seg_ids)
                prev["text"] = (prev["text"] + " " + text).strip()
                prev["end"] = end
                prev["end_time"] = seconds_to_hhmmss(end)
            else:
                chunks.append(_make_chunk(len(chunks), seg_ids, texts, start, end))

    for idx, ch in enumerate(chunks):
        ch["chunk_id"] = idx

    # 임베딩용 문맥(뒤쪽)을 붙인다. 전사본 경로와 동일한 규칙.
    from app.services.transcript_ingest import attach_embed_context

    attach_embed_context(chunks)
    return chunks
