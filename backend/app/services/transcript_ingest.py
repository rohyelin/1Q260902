from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from app.services.transcribe import seconds_to_hhmmss

# 텍스트로 바로 읽는 확장자 (그 외 .pdf/.docx는 추출 함수로 처리)
_PLAIN_TEXT_EXTS = {".txt", ".md", ".text", ".vtt", ".srt"}
# docx 워드프로세싱 XML 네임스페이스
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _extract_pdf_text(path: str) -> str:
    """PDF 전사본에서 텍스트를 추출한다 (PyMuPDF)."""
    import fitz  # PyMuPDF (강의록 추출과 동일 라이브러리)

    parts: list[str] = []
    doc = fitz.open(path)
    try:
        for page in doc:
            parts.append(page.get_text("text"))
    finally:
        doc.close()
    return "\n".join(parts)


def _extract_docx_text(path: str) -> str:
    """워드(.docx) 전사본에서 문단 텍스트를 추출한다 (표준 라이브러리만 사용).

    docx는 zip 안 word/document.xml 이므로 별도 패키지 설치 없이 읽는다.
    """
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    lines: list[str] = []
    for para in root.iter(f"{_W_NS}p"):
        texts = [node.text for node in para.iter(f"{_W_NS}t") if node.text]
        line = "".join(texts).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_transcript_text(path: str) -> str:
    """업로드된 전사본 파일에서 순수 텍스트를 뽑는다.

    확장자에 따라 txt/md/자막은 그대로, PDF/DOCX는 추출한다.
    알 수 없는 확장자는 일단 텍스트로 읽어본다.
    """
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return _extract_pdf_text(path)
    if ext == ".docx":
        return _extract_docx_text(path)
    if ext in _PLAIN_TEXT_EXTS:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    return Path(path).read_text(encoding="utf-8", errors="ignore")

# 업로드된 "전사본(텍스트)" → chunk 변환.
#
# 녹음 파이프라인의 chunk_segments()는 발화 사이 "침묵(pause)"을 경계로 자르지만,
# 업로드된 전사본에는 침묵 정보가 없다. 그래서 여기서는 문장/문단/길이 기준으로 자른다.
#
# 목표: "형식이 뭐가 오든" 최대한 알아서 처리한다.
#   - 순수 텍스트            : 그대로 문장 단위로
#   - 타임스탬프 포함        : [00:12:34] / (1:02) / 00:12 등 → 시간 살려서 표시용으로
#   - SRT/VTT 자막           : "00:00:01,000 --> 00:00:04,000" 큐 + 인덱스 줄 처리
#   - 화자 라벨 포함         : "교수:", "학생:", "A:", "Speaker 1:" 등 → 제거
# 타임스탬프는 결과 화면 표시용일 뿐, 슬라이드 매칭 계산에는 쓰이지 않는다.

# 조각을 작게 유지해 한 조각이 두 슬라이드 내용을 걸치지 않게 한다.
# (450→250으로 줄이니 슬라이드 경계 매칭이 크게 개선됨을 실제 강의로 확인)
MAX_CHARS = 380      # chunk 하드 상한
TARGET_CHARS = 250   # 목표 길이 (이 이상 쌓이면 문장 경계에서 끊음)
MIN_CHARS = 120      # 마지막 조각이 이보다 짧으면 직전 chunk에 합침

# ── A-1: 문장 단위 분할 ────────────────────────────────────────────
# 라벨 검수(임신부생리 27장)에서, 슬라이드 설명이 실제로 시작되는 지점의 60%가
# chunk "안쪽"에 있었다. chunk를 통째로 배정하는 구조에서는 이 60%를 원리적으로
# 맞출 수 없어, 조각을 문장 단위까지 잘게 내린다.
#
# 자르는 단위와 경계 판단을 분리한다:
#   - 배정(assignment)은 문장 단위로 한다  → 경계를 문장까지 좁힐 수 있다
#   - 판단(embedding)은 뒤따르는 문맥을 함께 본다 → 한 문장만으로는 신호가 약하므로
#
# 문맥을 "뒤쪽"만 붙이는 이유: 우리가 찾는 것은 "여기서 무엇이 시작되는가"다.
# 앞 문장을 붙이면 직전 슬라이드 내용이 섞여 들어와, 관측된 '늦음' 편향을 키운다.
SENTENCE_LEVEL = True     # False로 두면 예전(250자 누적) 방식
MERGE_SHORT_CHARS = 40    # 이보다 짧은 조각은 다음 문장과 합친다.
                          # ("네." "그렇죠." 같은 토막은 그 자체로는 신호가 없다)
                          #
                          # 25로 낮춰 실측한 결과(2026-09-01):
                          #   천장(정답이 조각 맨앞)  12 → 13   거의 안 오름
                          #   실제 맞음+경계          67% → 56%  오히려 떨어짐
                          # 조각이 짧아질수록 문장 하나의 뜻 신호가 약해져 손해가 컸다.
                          # 남은 '조각 안쪽' 정답은 짧은 문장이 뭉쳐서가 아니라
                          # 긴 문장 하나 안에서 슬라이드가 넘어가기 때문이다.
                          # → 더 잘게 자르는 방향은 막다른 길. 절 단위 분할이 필요.
EMBED_FORWARD_CHARS = 220  # 임베딩할 때 뒤에서 끌어올 문맥 길이

# 줄 맨 앞 인라인 타임스탬프: [00:12:34], (1:02:03), 00:12:34, 00:12 등
_INLINE_TS_PATTERNS = [
    re.compile(r"^\s*[\[(]\s*(\d{1,2}):(\d{2}):(\d{2})(?:[.,]\d+)?\s*[\])]\s*"),
    re.compile(r"^\s*[\[(]\s*(\d{1,2}):(\d{2})(?:[.,]\d+)?\s*[\])]\s*"),
    re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})(?:[.,]\d+)?\s+"),
    re.compile(r"^\s*(\d{1,2}):(\d{2})(?:[.,]\d+)?\s+"),
]

# "교수:", "학생 :", "A:", "Speaker 1:", "화자2:" 등 (줄 앞 짧은 라벨 + 콜론)
_SPEAKER_RE = re.compile(r"^\s*(?:speaker\s*\d+|화자\s*\d*|[A-Za-z가-힣]{1,8}\s?\d{0,2})\s*[:：]\s*", re.IGNORECASE)

# 문장 경계: 종결부호 뒤 공백
_SENT_END_RE = re.compile(r"(?<=[.?!。？！])\s+")

# ── PDF에서 생긴 군더더기 공백 정리 ────────────────────────────────
# PDF는 화면 폭에 맞춰 글자를 배치하므로, 텍스트를 뽑으면 단어 한가운데에
# 공백이나 줄바꿈이 끼어든다. ("강의자료 를", "생 각을", "다운받으\n시면")
# 화면과 인쇄물에 그대로 나오면 읽기 나쁘므로 여기서 한 번 정리한다.
_HANGUL_ONE_RE = re.compile(r"^[가-힣]$")
# 홀로 떨어져 나온 조사 — 앞 낱말에 도로 붙인다.
# '이/가/에/로'는 "이 사람", "로 가면"처럼 진짜 낱말일 수 있어 제외한다.
_ORPHAN_PARTICLES = {"를", "을", "은", "는", "의", "도", "와", "과", "께", "만", "부터", "까지"}


def _fix_pdf_spacing(text: str) -> str:
    """줄바꿈을 없애고, 떨어져 나온 글자 조각을 원래 낱말에 도로 붙인다."""
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return text

    tokens = text.split(" ")
    out: list[str] = []
    carry = ""  # 다음 낱말 앞에 붙일 한 글자 조각
    for tok in tokens:
        if not tok:
            continue
        if carry:
            tok = carry + tok
            carry = ""
        if _HANGUL_ONE_RE.match(tok):
            carry = tok          # 한 글자만 떨어진 것 → 뒤 낱말에 붙인다
            continue
        if out and tok in _ORPHAN_PARTICLES:
            out[-1] += tok       # 조사만 떨어진 것 → 앞 낱말에 붙인다
            continue
        out.append(tok)
    if carry:
        if out:
            out[-1] += carry
        else:
            out.append(carry)
    return " ".join(out)

# 시간 문자열 → 초
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})(?::(\d{2}))?(?:[.,](\d{1,3}))?")


def _parse_time(text: str) -> float | None:
    m = _TIME_RE.search(text)
    if not m:
        return None
    a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
    if c is not None:  # H:M:S
        return float(a * 3600 + b * 60 + int(c))
    return float(a * 60 + b)  # M:S


def _strip_inline_timestamp(line: str) -> tuple[str, float | None]:
    for pat in _INLINE_TS_PATTERNS:
        m = pat.match(line)
        if m:
            g = m.groups()
            if len(g) == 3:
                secs = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2])
            else:
                secs = int(g[0]) * 60 + int(g[1])
            return line[m.end():], float(secs)
    return line, None


def _strip_speaker(line: str) -> str:
    return _SPEAKER_RE.sub("", line, count=1)


def _hardwrap(text: str) -> list[str]:
    """문장 단위로 쪼개되, 종결부호 없는 초장문은 단어 경계로 강제 분할한다."""
    out: list[str] = []
    for sent in _SENT_END_RE.split(text):
        s = sent.strip()
        if not s:
            continue
        if len(s) <= MAX_CHARS:
            out.append(s)
            continue
        cur = ""
        for word in s.split():
            if cur and len(cur) + 1 + len(word) > TARGET_CHARS:
                out.append(cur)
                cur = word
            else:
                cur = f"{cur} {word}".strip()
        if cur:
            out.append(cur)
    return out


def _parse_units(text: str) -> list[tuple[str, float | None]]:
    """전사본 텍스트를 (문장, 시작초 or None) 조각 리스트로 변환한다.

    PDF 전사본은 화면 폭에 맞춰 줄이 끊겨 있고, 그 끊김이 단어 한가운데인 경우가 많다.
    ("...다운받으" / "시면 될 것 같고요.")
    그래서 줄을 그대로 조각으로 삼으면 안 되고, 먼저 문단으로 이어 붙인 뒤
    문장 경계에서 자른다. 문단을 끊는 신호는 빈 줄과 새 타임스탬프뿐이다.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    units: list[tuple[str, float | None]] = []
    pending_ts: float | None = None  # SRT/VTT 큐에서 다음 텍스트 줄에 붙일 시간
    buf: list[str] = []
    buf_ts: float | None = None

    def flush_paragraph() -> None:
        """모아둔 줄을 이어 붙여 문장 단위로 쪼갠다."""
        nonlocal buf, buf_ts
        joined = _fix_pdf_spacing(" ".join(buf))
        buf = []
        ts = buf_ts
        buf_ts = None
        if not joined:
            return
        for piece in _hardwrap(joined):
            units.append((piece, ts))
            ts = None  # 시간은 문단의 첫 문장에만 붙인다

    for line in lines:
        raw = line.strip()
        if not raw:
            flush_paragraph()  # 빈 줄 = 문단 경계
            continue
        if raw.upper().startswith("WEBVTT"):
            continue
        if "-->" in raw:  # SRT/VTT 큐 타이밍 줄
            flush_paragraph()
            pending_ts = _parse_time(raw.split("-->")[0])
            continue
        if raw.isdigit():  # SRT 큐 인덱스 줄
            continue

        stripped, inline_ts = _strip_inline_timestamp(line)
        stripped = _strip_speaker(stripped).strip()
        if not stripped:
            continue

        ts_here = inline_ts if inline_ts is not None else pending_ts
        pending_ts = None  # 한 번 쓰면 소비
        if ts_here is not None:
            flush_paragraph()  # 새 타임스탬프 = 새 구간 시작
            buf_ts = ts_here
        buf.append(stripped)

    flush_paragraph()
    return units


def chunk_transcript(text: str) -> list[dict[str, Any]]:
    """전사본 텍스트를 매칭 파이프라인이 쓰는 chunk 리스트로 변환한다.

    반환 chunk는 chunk_segments()와 동일한 필드를 갖는다.
    타임스탬프가 없으면 start_time/end_time은 빈 문자열("")로 둔다.
    """
    units = _parse_units(text)
    if not units:
        return []

    chunks: list[dict[str, Any]] = []
    buf: list[str] = []
    buf_start_ts: float | None = None
    buf_end_ts: float | None = None
    cur_len = 0

    def flush() -> None:
        nonlocal buf, buf_start_ts, buf_end_ts, cur_len
        joined = " ".join(buf).strip()
        buf = []
        cur_len = 0
        s_ts, e_ts = buf_start_ts, buf_end_ts
        buf_start_ts = None
        buf_end_ts = None
        if not joined:
            return
        start = s_ts if s_ts is not None else 0.0
        end = e_ts if e_ts is not None else start
        chunks.append(
            {
                "chunk_id": len(chunks),
                "start": float(start),
                "end": float(end),
                "start_time": seconds_to_hhmmss(start) if s_ts is not None else "",
                "end_time": seconds_to_hhmmss(end) if e_ts is not None else "",
                "text": joined,
                "raw_text": joined,
                "segment_ids": [],
            }
        )

    for sent, ts in units:
        if ts is not None:
            if buf_start_ts is None:
                buf_start_ts = ts
            buf_end_ts = ts
        buf.append(sent)
        cur_len += len(sent) + 1
        if cur_len >= (MERGE_SHORT_CHARS if SENTENCE_LEVEL else TARGET_CHARS):
            flush()
    flush()

    # 마지막 조각이 너무 짧으면 직전 chunk에 합친다.
    tail_min = MERGE_SHORT_CHARS if SENTENCE_LEVEL else MIN_CHARS
    if len(chunks) >= 2 and len(chunks[-1]["text"]) < tail_min:
        last = chunks.pop()
        prev = chunks[-1]
        prev["text"] = f"{prev['text']} {last['text']}".strip()
        prev["raw_text"] = prev["text"]
        if last["end"]:
            prev["end"] = last["end"]
        if last["end_time"]:
            prev["end_time"] = last["end_time"]

    for i, ch in enumerate(chunks):
        ch["chunk_id"] = i

    attach_embed_context(chunks)
    return chunks


def attach_embed_context(
    chunks: list[dict[str, Any]], forward_chars: int = EMBED_FORWARD_CHARS
) -> None:
    """각 조각에 '뒤따르는 문맥'을 붙여 embed_text를 만든다.

    임베딩은 embed_text로, 화면 표시와 BM25·anchor 점수는 원래 text로 쓴다.
    (앞 문맥을 넣지 않는 이유는 파일 상단 주석 참고)
    """
    n = len(chunks)
    for i, ch in enumerate(chunks):
        own = ch.get("text", "")
        if forward_chars <= 0:
            ch["embed_text"] = own
            continue
        tail: list[str] = []
        budget = forward_chars
        for j in range(i + 1, n):
            nxt = chunks[j].get("text", "")
            if not nxt:
                continue
            tail.append(nxt[:budget])
            budget -= len(nxt)
            if budget <= 0:
                break
        ch["embed_text"] = " ".join([own, *tail]).strip()
