from __future__ import annotations

import re
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from app.services.embedding import cosine_similarity_matrix

TOKEN_RE = re.compile(r"[a-zA-Z0-9가-힣]+")
UPPER_ABBR_RE = re.compile(r"\b[A-Z]{2,}\b")
NUMBER_EXPR_RE = re.compile(r"\d+[\w\-./]*")
FORMULA_RE = re.compile(r"\b[A-Z][a-z]?\d*|[\w]+-[\w]+")
KOREAN_KEYWORDS = ["중요", "시험", "기억", "출제", "핵심", "주의"]

# ── A-2: "여기서 시작된다" 신호 ────────────────────────────────────
# 교수님은 슬라이드를 넘길 때 그 슬라이드의 주제어를 꺼내며 시작한다.
# 그 지점은 "앞쪽은 이 슬라이드와 안 맞고, 뒤쪽부터 맞기 시작하는" 변곡점이다.
# 지금 알고리즘은 조각별 점수의 높낮이만 보므로 이 변곡을 못 본다.
#
# 특정 말버릇(다음은, 그다음에...)을 넣지 않는 이유는 교수님마다 다르기 때문이다.
# 대신 점수가 '오르기 시작하는 지점'을 찾는다 — 누가 강의하든 성립한다.
# 2026-09-01 sweep.py 로 조합 120개를 시험해 고른 값 (임신부생리 강의 1개 기준).
# 제목 신호가 제대로 살아나자 START_EDGE 는 0이 가장 좋았다.
# = 주제어가 '처음 등장하는 자리'를 보는 것이, 점수의 변곡점을 보는 것보다 정확했다.
# 다른 강의에서도 그런지는 아직 확인 전이므로 신호 자체는 지우지 않고 남겨 둔다.
# sweep 결과, 상위 15개 조합이 전부 동점이었다. 제목 가중치는 0.15~0.35 어디든
# 결과가 같았으므로, 한 강의에 과하게 맞추지 않도록 가운데 값을 쓴다.
START_EDGE_WEIGHT = 0.0    # 0이면 변곡점 신호를 끈다 (0.25로 되돌리면 다시 켜짐)
START_EDGE_WINDOW = 4      # 앞뒤 몇 조각을 평균 내어 비교할지 (위가 0이면 무의미)
TITLE_START_WEIGHT = 0.25  # 제목 주제어가 '처음' 등장하는 조각에 주는 가점
TITLE_BOOST_WEIGHT = 0.08  # 제목 주제어가 들어 있기만 해도 주는 가점

# ── 주제어 품질 기준 ──────────────────────────────────────────────
# 실측(소아혈액질환 71장)에서 확인된 문제:
#   - 제목 'Text in here' 에서 뽑힌 'in' 이 216조각 중 39개에 등장.
#     이런 흔한 말에도 시작 가점이 붙어 앵커를 앞으로 끌고 갔다.
#   - '유전구상적혈구증' 은 발화에 0회. 교수님은 spherocytosis 라고 말한다.
# 그래서 가점을 주기 전에 그 낱말이 단서로 쓸 만한지 먼저 거른다.
TERM_MAX_CHUNK_RATIO = 0.25  # 조각의 이 비율보다 많이 나오면 흔한 말 → 버림
TERM_MAX_PAGE_RATIO = 0.20   # 여러 슬라이드에 두루 나오면 그 슬라이드 것이 아님 → 버림
TERM_MIN_LEN = 2
BODY_TERM_LIMIT = 8          # 제목에서 못 건졌을 때 본문에서 가져올 낱말 수

# 파워포인트 템플릿에 남아 있는 자리표시자. 내용이 아니므로 제목으로 쓰지 않는다.
# (실측: 이 강의 71장 중 3장이 'Text in here' 를 제목으로 쓰고 있었다)
_PLACEHOLDER_TITLE_RE = re.compile(
    r"^\s*(text in here|click to edit|제목을?\s*입력|여기에?\s*(제목|텍스트)"
    r"|lorem ipsum|title|subtitle|제목|부제)\b",
    re.IGNORECASE,
)
# 같은 낱말이 이만큼 떨어져 다시 나오면 '다시 꺼낸 것'으로 본다.
# 제목이 같은 슬라이드가 연달아 나올 때, 전사본 맨 앞의 첫 등장만 인정하면
# 뒤 슬라이드의 앵커가 앞으로 끌려간다(실측: 7칸·10칸 빠름).
REINTRO_GAP = 6

# 슬라이드 한 장 분량을 건너뛸 때 물릴 벌점.
# 조각 수가 아니라 '슬라이드 몇 장어치를 건너뛰는가'를 기준으로 삼아,
# 조각을 잘게 쪼개도 기준이 흔들리지 않게 한다.
# (예전 고정값 0.015 는 조각 61개 기준이었고, 254개가 되자 4배로 가혹해졌다)
JUMP_PENALTY_PER_PAGE = 0.035

MIN_MATCH_SCORE = 0.35
# 이 값보다 페이지 최고 유사도가 낮으면 "미설명 슬라이드"로 보고 매칭하지 않는다.
UNMATCHED_SCORE = 0.14
# 한 슬라이드에 담을 수 있는 chunk 상한. 실제 개수는 slide별로 다음 anchor까지의
# 창 크기(가변)로 결정되므로, 이 값은 "교수님이 한 슬라이드를 아주 길게 설명한 경우"에도
# 조각이 다음 슬라이드로 새지 않도록 넉넉하게 둔다. (기존 6은 긴 설명을 잘라 흩뜨렸음)
# A-1로 조각이 문장 단위까지 잘아졌으므로 상한을 올린다.
# 실제 분량 제한은 select_monotonic_matches 의 max_chars_per_page=2500 이 맡는다.
MAX_CHUNKS_PER_PAGE = 200

# 페이지 타입
PAGE_CONTENT = "content"      # 실제 내용이 많은 슬라이드
PAGE_SECTION = "section"      # 제목/구분 슬라이드 (예: "I. 후두 검사")
PAGE_IMAGE_ONLY = "image_only"  # 텍스트가 거의 없는 그림/도표 슬라이드

# 섹션 슬라이드로 판단할 때 쓰는 힌트 패턴 (로마숫자/장번호 제목)
SECTION_HEAD_RE = re.compile(r"^\s*(?:[IVXⅠ-Ⅹ]+|\d+)\s*[.)]?\s*\S")


def classify_page_type(text: str) -> str:
    """슬라이드 텍스트로 페이지 타입을 추정한다.

    - 텍스트가 거의 없으면 IMAGE_ONLY (그림/도표 위주)
    - 짧고 줄 수가 적으면 SECTION (제목/구분 슬라이드)
    - 그 외는 CONTENT
    이렇게 나눠야 제목·구분 슬라이드에 엉뚱한 chunk가 랜덤 매칭되는 것을 막을 수 있다.
    """
    t = (text or "").strip()
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    n_chars = len(t)

    if n_chars < 25:
        return PAGE_IMAGE_ONLY

    # 짧은 텍스트 + 적은 줄 수 → 구분/제목 슬라이드
    if n_chars < 90 and len(lines) <= 3:
        return PAGE_SECTION
    if len(lines) <= 2 and n_chars < 120 and SECTION_HEAD_RE.match(lines[0] if lines else ""):
        return PAGE_SECTION

    return PAGE_CONTENT


def slide_title(text: str) -> str:
    """슬라이드 제목(첫 의미 있는 줄)을 뽑는다."""
    for ln in (text or "").splitlines():
        s = ln.strip()
        if len(s) >= 2:
            return s
    return ""


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(text.lower())
    return [t for t in tokens if len(t) > 1]


def extract_anchor_terms(page_text: str) -> list[str]:
    anchors: set[str] = set()
    for pattern in (UPPER_ABBR_RE, NUMBER_EXPR_RE, FORMULA_RE):
        for match in pattern.findall(page_text):
            anchors.add(match)
    for kw in KOREAN_KEYWORDS:
        if kw in page_text:
            anchors.add(kw)
    words = re.findall(r"[A-Za-z]{3,}", page_text)
    for i in range(len(words) - 1):
        phrase = f"{words[i]} {words[i + 1]}"
        anchors.add(phrase.lower())
    return list(anchors)


def anchor_score(page_text: str, chunk_text: str) -> float:
    anchors = extract_anchor_terms(page_text)
    if not anchors:
        return 0.0
    chunk_lower = chunk_text.lower()
    hits = sum(1 for a in anchors if a.lower() in chunk_lower)
    return min(1.0, hits / max(1, len(anchors) * 0.3))


def min_max_normalize(scores: np.ndarray) -> np.ndarray:
    if scores.size == 0:
        return scores
    lo, hi = scores.min(), scores.max()
    if hi - lo < 1e-9:
        return np.zeros_like(scores)
    return (scores - lo) / (hi - lo)


def compute_bm25_scores(page_texts: list[str], chunk_texts: list[str]) -> np.ndarray:
    corpus_tokens = [tokenize(t) for t in chunk_texts]
    bm25 = BM25Okapi(corpus_tokens)
    scores = np.zeros((len(page_texts), len(chunk_texts)), dtype=np.float32)
    for i, page_text in enumerate(page_texts):
        query_tokens = tokenize(page_text)
        if not query_tokens:
            continue
        raw = np.array(bm25.get_scores(query_tokens), dtype=np.float32)
        scores[i] = min_max_normalize(raw)
    return scores


def compute_final_scores(
    page_texts: list[str],
    chunk_texts: list[str],
    page_embeddings: np.ndarray,
    chunk_embeddings: np.ndarray,
) -> np.ndarray:
    dense = cosine_similarity_matrix(page_embeddings, chunk_embeddings)
    bm25 = compute_bm25_scores(page_texts, chunk_texts)
    n_pages, n_chunks = dense.shape
    anchor = np.zeros((n_pages, n_chunks), dtype=np.float32)

    # A-1 이후 chunk 수가 수백 개로 늘어난다. 페이지마다 anchor 용어를 한 번만 뽑고
    # 소문자 변환도 미리 해둔다 (이전에는 (페이지 x chunk)번 정규식을 다시 돌렸다).
    lowered_chunks = [ct.lower() for ct in chunk_texts]
    for i, page_text in enumerate(page_texts):
        anchors = extract_anchor_terms(page_text)
        if not anchors:
            continue
        lowered_anchors = [a.lower() for a in anchors]
        denom = max(1.0, len(anchors) * 0.3)
        for j, chunk_lower in enumerate(lowered_chunks):
            hits = sum(1 for a in lowered_anchors if a in chunk_lower)
            if hits:
                anchor[i, j] = min(1.0, hits / denom)

    return 0.70 * dense + 0.20 * bm25 + 0.10 * anchor


def _align_anchors_dp(
    scores: np.ndarray,
    stay_penalty: float = 0.03,
    jump_penalty: float | None = None,
) -> list[int]:
    """전역 최적 monotonic 정렬 (DTW 방식 DP).

    페이지 순서와 chunk(시간) 순서가 모두 단조 증가한다는 제약 하에
    전체 점수 합을 최대화하는 anchor 경로를 찾는다.
    한 chunk는 최대 2개의 연속 페이지에서만 anchor가 될 수 있다
    (state 0 = 새로 진입, state 1 = 두 번째 연속 사용).

    ── jump_penalty 를 조각 밀도에 맞춰 자동으로 정하는 이유 ──────────────
    건너뛴 조각 수에 비례해 벌점을 매겨, 신호가 약한 구간에서 한 번에
    수십 분을 뛰어넘는 것을 막는다. 그런데 이 값이 고정이면 조각 크기가
    바뀔 때 의미가 달라진다.

    실측(종양관리 24장 / 254조각):
      조각을 문장 단위로 잘게 쪼개면서 조각 수가 61 → 254 로 4배가 되었다.
      같은 시간을 건너뛰는 데 4배 벌점을 물게 되어, 교수님이 한 슬라이드를
      오래 설명하면 다음 슬라이드가 따라가지 못했다.
      그 밀림이 누적되어 오차가 +1 → +40 조각까지 벌어졌다.

    그래서 "슬라이드 하나를 건너뛰는 비용"이 일정하도록 정규화한다.
    """
    n_pages, n_chunks = scores.shape
    if jump_penalty is None:
        # 슬라이드 한 장당 평균 조각 수. 이 값으로 나눠 밀도와 무관하게 만든다.
        per_page = max(1.0, n_chunks / max(1, n_pages))
        jump_penalty = JUMP_PENALTY_PER_PAGE / per_page
    NEG = -1e18
    # 페이지 수가 chunk 수의 2배를 넘으면 2연속 제한으로는 경로가 없으므로 완화
    allow_long_stay = n_pages > 2 * n_chunks

    dp0 = np.full((n_pages, n_chunks), NEG)
    dp1 = np.full((n_pages, n_chunks), NEG)
    dp0[0] = scores[0].astype(np.float64)

    # 전진 시 조상 chunk 인덱스 (backtrack용)
    back0 = np.full((n_pages, n_chunks), -1, dtype=np.int64)

    for p in range(1, n_pages):
        prev_best = np.maximum(dp0[p - 1], dp1[p - 1])

        # prefix max over c' < c, jump_penalty * (c - c') 반영
        # value(c') = prev_best[c'] + jump_penalty * c'  를 최대화하는 c'를 고르고
        # 최종적으로 - jump_penalty * c 를 더한다.
        adjusted = prev_best + jump_penalty * np.arange(n_chunks)
        best_val = NEG
        best_idx = -1
        pref_val = np.full(n_chunks, NEG)
        pref_idx = np.full(n_chunks, -1, dtype=np.int64)
        for c in range(n_chunks):
            pref_val[c] = best_val
            pref_idx[c] = best_idx
            if adjusted[c] > best_val:
                best_val = adjusted[c]
                best_idx = c

        dp0[p] = scores[p] + pref_val - jump_penalty * np.arange(n_chunks)
        back0[p] = pref_idx
        dp1[p] = scores[p] + dp0[p - 1] - stay_penalty
        if allow_long_stay:
            dp1[p] = np.maximum(dp1[p], scores[p] + dp1[p - 1] - stay_penalty)

    # backtrack
    anchors = [0] * n_pages
    c = int(np.argmax(np.maximum(dp0[-1], dp1[-1])))
    state = 0 if dp0[-1][c] >= dp1[-1][c] else 1
    anchors[-1] = c

    for p in range(n_pages - 1, 0, -1):
        if state == 1:
            # 페이지 p 가 페이지 p-1 과 같은 chunk 를 쓴 경우.
            # dp1[p] 는 dp0[p-1] 에서만 온다(allow_long_stay 가 아닌 한).
            # 여기서 상태를 다시 계산하면 2연속 제한이 깨져 3개 이상이 사슬처럼 이어진다.
            # 실제로 슬라이드 13·14·15 가 같은 조각을 물었던 원인.
            anchors[p - 1] = c
            if allow_long_stay and dp1[p - 1][c] > dp0[p - 1][c]:
                state = 1
            else:
                state = 0
        else:
            prev_c = int(back0[p][c])
            if prev_c < 0:
                prev_c = c
            c = prev_c
            anchors[p - 1] = c
            state = 0 if dp0[p - 1][c] >= dp1[p - 1][c] else 1

    return anchors


def select_monotonic_matches(
    scores: np.ndarray,
    chunks: list[dict[str, Any]],
    *,
    gate_scores: np.ndarray | None = None,
    page_types: list[str] | None = None,
    min_score: float = MIN_MATCH_SCORE,
    unmatched_score: float = UNMATCHED_SCORE,
    max_chunks_per_page: int = MAX_CHUNKS_PER_PAGE,
    max_chars_per_page: int = 2500,
    pace_weight: float = 0.12,
) -> tuple[list[list[dict[str, Any]]], list[str]]:
    warnings: list[str] = []
    n_pages, n_chunks = scores.shape
    if n_pages == 0 or n_chunks == 0:
        return [[] for _ in range(n_pages)], warnings

    if page_types is None:
        page_types = [PAGE_CONTENT] * n_pages

    # 약한 pacing prior: 신호가 약한(점수가 평평한) 구간에서는 페이지 진행률과
    # chunk 진행률이 비슷해지도록 유도한다. 강한 매칭 점수는 prior를 이기므로
    # 슬라이드별 설명 길이가 크게 달라도 실제 신호를 따라간다.
    pos_p = np.arange(n_pages) / max(n_pages - 1, 1)
    pos_c = np.arange(n_chunks) / max(n_chunks - 1, 1)
    prior = -pace_weight * np.abs(pos_p[:, None] - pos_c[None, :])

    anchors = _align_anchors_dp(scores + prior)

    # 순위를 매기는 점수와 신뢰도를 판정하는 점수를 분리한다.
    # scores 에는 제목 가점 등이 더해져 1을 넘을 수 있어(실측 1.06),
    # 0~1 을 전제로 만든 아래 판정선이 사실상 작동하지 않았다.
    # gate_scores(가점 전 원점수)로 판정하면 "설명 없는 슬라이드"를 제대로 비운다.
    conf = gate_scores if gate_scores is not None else scores
    anchor_scores = [float(conf[p, anchors[p]]) for p in range(n_pages)]

    # 적응형 신뢰도 threshold: 점수 분포가 전반적으로 낮으면 절대값 대신 분포 기준
    median_sc = float(np.median(anchor_scores))
    eff_min_score = min(min_score, max(0.15, 0.7 * median_sc))
    # unmatched 판정선도 분포에 맞춰 완화 (너무 공격적으로 비우지 않도록)
    eff_unmatched = min(unmatched_score, 0.5 * eff_min_score)

    page_matches: list[list[dict[str, Any]]] = []

    for p in range(n_pages):
        a = anchors[p]
        anchor_sc = anchor_scores[p]
        ptype = page_types[p]
        page_best = float(conf[p].max())

        # 제목/구분·그림 슬라이드는 신호가 뚜렷할 때만 매칭한다.
        # 내용이 거의 없는 슬라이드에 top-chunk를 억지로 붙이면 랜덤 매칭이 되므로,
        # 판정선을 CONTENT보다 높여 애매하면 비운다.
        if ptype in (PAGE_SECTION, PAGE_IMAGE_ONLY):
            type_gate = eff_min_score * (0.9 if ptype == PAGE_SECTION else 1.0)
            if page_best < type_gate:
                page_matches.append([])
                label = "구분/제목" if ptype == PAGE_SECTION else "그림/도표"
                warnings.append(
                    f"페이지 {p + 1}: {label} 슬라이드로 보여 매칭하지 않았습니다 "
                    f"(최고 유사도 {page_best:.2f})."
                )
                continue
        elif page_best < eff_unmatched:
            page_matches.append([])
            warnings.append(
                f"페이지 {p + 1}: 관련 발화를 찾지 못해 매칭하지 않았습니다 "
                f"(최고 유사도 {page_best:.2f}). 설명 없이 넘어간 슬라이드일 수 있습니다."
            )
            continue

        # 이 페이지의 chunk "구간": anchor부터 다음 페이지 anchor 직전까지 연속으로 담는다.
        # top-k를 흩뿌리는 대신 연속 구간이라, 교수님이 한 슬라이드를 길게 설명하면
        # 그 구간이 통째로, 빨리 넘긴 슬라이드는 짧게 들어간다.
        if p + 1 < n_pages:
            window_end = max(anchors[p + 1], a + 1)
        else:
            window_end = a + max_chunks_per_page
        window_end = min(window_end, a + max_chunks_per_page, n_chunks)
        chosen = list(range(a, window_end))  # 연속 구간, 시간순

        # 예전에는 max_chars_per_page 를 넘으면 남은 chunk를 그냥 버렸다.
        # 전사본이 통째로 사라지는 원인이었으므로, 구간 안의 chunk는 전부 담는다.
        # (분량이 많으면 PDF 쪽에서 '이어서' 장으로 나눠 싣는다.)
        trimmed: list[dict[str, Any]] = [
            {**chunks[cid], "score": round(float(scores[p, cid]), 4)} for cid in chosen
        ]

        if not trimmed:
            trimmed = [{**chunks[a], "score": round(anchor_sc, 4)}]

        low_conf = anchor_sc < eff_min_score
        for m in trimmed:
            m["low_confidence"] = low_conf
        if low_conf:
            warnings.append(
                f"페이지 {p + 1}: 매칭 신뢰도 낮음 ({anchor_sc:.2f}), "
                "시간 순서 기준으로 배치했습니다."
            )

        page_matches.append(trimmed)

    # ── 어느 페이지에도 안 담긴 chunk를 회수한다 ──────────────────────
    # 빠지는 경로가 세 가지 있었다.
    #   1) 첫 anchor 이전 구간 (강의 도입부. 첫 장이 4분부터 시작하던 원인)
    #   2) 매칭을 비운 페이지(제목·그림 슬라이드)의 구간
    #   3) 마지막 anchor 이후 구간 (강의 마무리)
    # 전사본은 한 글자도 잃으면 안 되므로, 시간상 가장 가까운 앞 페이지에 붙인다.
    assigned: set[int] = {
        m["chunk_id"] for page in page_matches for m in page
    }
    id_to_pos = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    orphans = [c for c in chunks if c["chunk_id"] not in assigned]

    if orphans:
        # 각 페이지가 담고 있는 chunk 위치의 최댓값 (앞 페이지 찾기용)
        page_last_pos = [
            max((id_to_pos[m["chunk_id"]] for m in page), default=-1)
            for page in page_matches
        ]
        recovered = 0
        for ch in orphans:
            pos = id_to_pos[ch["chunk_id"]]
            # 이 chunk보다 앞서 끝나는 페이지 중 가장 늦은 것
            target = -1
            for p in range(n_pages):
                if page_last_pos[p] != -1 and page_last_pos[p] < pos:
                    target = p
            if target == -1:  # 앞에 아무것도 없으면 (도입부) 내용이 있는 첫 페이지로
                target = next(
                    (p for p in range(n_pages) if page_matches[p]), 0
                )
            page_matches[target].append(
                {
                    **ch,
                    "score": round(float(scores[target, ch["chunk_id"]]), 4)
                    if ch["chunk_id"] < n_chunks
                    else 0.0,
                    "carried_over": True,
                    "low_confidence": True,
                }
            )
            recovered += 1

        # 페이지 안에서 시간순 정렬 유지
        for page in page_matches:
            page.sort(key=lambda m: id_to_pos.get(m["chunk_id"], 0))

        warnings.append(
            f"어느 슬라이드에도 매칭되지 않은 발화 {recovered}개를 "
            "시간상 가장 가까운 슬라이드에 붙였습니다 (누락 방지)."
        )

    return page_matches, warnings


_PARTICLES = (
    "에서도", "에서", "으로", "이라고", "라고", "부터", "까지", "에게", "한테",
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "로", "와", "과", "만",
)
_KO_WORD_RE = re.compile(r"[가-힣]{2,}")


def _strip_particle(word: str) -> str:
    """뒤에 붙은 조사를 떼어낸다. 떼고 나서 2글자 미만이면 원형 유지."""
    for p in _PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def build_lexicon(pages: list[dict[str, Any]], chunk_texts: list[str]) -> set[str]:
    """이 강의에 실제로 쓰인 한국어 낱말 사전을 만든다.

    슬라이드 제목은 `자궁경부질난소의변화`처럼 붙어 있는 경우가 많은데,
    같은 낱말이 본문이나 교수님 발화에는 띄어쓰기된 채로 나온다.
    그 형태를 모아 두면 붙은 제목을 다시 쪼갤 수 있다.
    형태소 분석기 없이, 이 강의 안의 데이터만으로 처리한다.
    """
    lex: set[str] = set()
    sources = [p.get("text", "") for p in pages] + list(chunk_texts)
    for text in sources:
        for word in _KO_WORD_RE.findall(text or ""):
            lex.add(word)
            stem = _strip_particle(word)
            if len(stem) >= 2:
                lex.add(stem)
    return lex


def segment_korean(token: str, lexicon: set[str], max_len: int = 8) -> list[str]:
    """붙어 있는 한국어 덩어리를 사전에 있는 낱말로 쪼갠다 (긴 것 우선)."""
    out: list[str] = []
    i = 0
    n = len(token)
    while i < n:
        for length in range(min(max_len, n - i), 1, -1):
            cand = token[i : i + length]
            if cand in lexicon:
                out.append(cand)
                i += length
                break
        else:
            i += 1  # 사전에 없는 글자는 건너뛴다
    return out


def slide_topic_terms(
    title: str, lexicon: set[str] | None = None
) -> list[str]:
    """슬라이드 제목에서 '주제어' 후보를 뽑는다.

    교수님은 슬라이드를 넘길 때 이 낱말들을 꺼내며 시작하는 경향이 있다.
    """
    terms: set[str] = set()
    for tok in tokenize(title):
        if len(tok) < 2:
            continue
        terms.add(tok)
        stem = _strip_particle(tok)
        if len(stem) >= 2:
            terms.add(stem)
        # 붙어 있는 긴 한국어 덩어리는 사전으로 쪼갠다
        if lexicon and len(tok) >= 5 and _KO_WORD_RE.fullmatch(tok):
            for piece in segment_korean(tok, lexicon):
                if len(piece) >= 2:
                    terms.add(piece)
    return [t for t in terms if len(t) >= 2]


def _page_terms(page: dict[str, Any]) -> list[str]:
    """슬라이드 본문에서 낱말 후보를 뽑는다 (제목에서 못 건졌을 때 쓴다)."""
    text = page.get("text", "") or ""
    out: set[str] = set()
    for tok in tokenize(text):
        if len(tok) >= TERM_MIN_LEN:
            out.add(tok)
            stem = _strip_particle(tok)
            if len(stem) >= TERM_MIN_LEN:
                out.add(stem)
    return list(out)


def build_signal_terms(
    pages: list[dict[str, Any]],
    chunk_texts: list[str],
    lexicon: set[str] | None = None,
) -> list[list[tuple[str, float]]]:
    """슬라이드마다 '단서로 쓸 만한 낱말'과 그 가중치를 정한다.

    거르는 기준 두 가지.
      흔한 말   조각 여럿에 두루 나오면 위치를 못 알려준다 ('in', '환자')
      없는 말   발화에 한 번도 안 나오면 아무 일도 못 한다 ('유전구상적혈구증')

    제목에서 쓸 만한 게 안 나오면 **본문 낱말** 중 드문 것을 대신 쓴다.
    그것마저 없으면 빈 목록을 준다 — 나쁜 단서를 쓰느니 안 쓰는 편이 낫다.
    """
    lowered = [ct.lower() for ct in chunk_texts]
    n_chunks = max(1, len(lowered))
    n_pages = max(1, len(pages))
    page_lowered = [(p.get("text", "") or "").lower() for p in pages]

    chunk_df: dict[str, int] = {}
    page_df: dict[str, int] = {}

    def measure(term: str) -> tuple[int, int]:
        t = term.lower()
        if t not in chunk_df:
            chunk_df[t] = sum(1 for c in lowered if t in c)
            page_df[t] = sum(1 for p in page_lowered if t in p)
        return chunk_df[t], page_df[t]

    def keep(term: str) -> tuple[bool, float]:
        """쓸 만한가, 그리고 얼마나 드문가(가중치)."""
        cdf, pdf = measure(term)
        if cdf == 0:
            return False, 0.0                       # 발화에 없음
        if cdf > n_chunks * TERM_MAX_CHUNK_RATIO:
            return False, 0.0                       # 너무 흔함
        if pdf > max(1, n_pages * TERM_MAX_PAGE_RATIO):
            return False, 0.0                       # 여러 슬라이드에 두루 나옴
        # 드물수록 무겁게 (조각 1개에만 나오면 1.0에 가깝다)
        return True, float(1.0 / (1.0 + np.log1p(cdf - 1)))

    result: list[list[tuple[str, float]]] = []
    for page in pages:
        title = slide_title(page.get("text", ""))
        if _PLACEHOLDER_TITLE_RE.match(title):
            picked = []          # 자리표시자는 제목이 아니다. 바로 본문으로 간다.
        else:
            cands = slide_topic_terms(title, lexicon)
            picked = [(t, w) for t in cands for ok, w in [keep(t)] if ok]

        if not picked:
            # 제목이 출처 표기이거나 'Text in here' 같은 자리표시자인 경우.
            # 그 슬라이드 본문에서 드문 낱말을 대신 쓴다.
            body = [(t, w) for t in _page_terms(page) for ok, w in [keep(t)] if ok]
            body.sort(key=lambda x: -x[1])
            picked = body[:BODY_TERM_LIMIT]

        result.append(picked)
    return result


def _title_boost_matrix(
    pages: list[dict[str, Any]],
    chunk_texts: list[str],
    lexicon: set[str] | None = None,
    signal_terms: list[list[tuple[str, float]]] | None = None,
) -> np.ndarray:
    """슬라이드 제목 단어가 chunk에 등장하면 가점을 주는 행렬.

    제목은 슬라이드에서 가장 강한 anchor이므로, 제목 용어가 담긴 chunk에
    작은 additive boost를 준다(embedding 신호를 덮어쓰지 않는 수준).
    """
    n_pages, n_chunks = len(pages), len(chunk_texts)
    boost = np.zeros((n_pages, n_chunks), dtype=np.float32)
    lowered = [ct.lower() for ct in chunk_texts]
    terms_per_page = signal_terms or build_signal_terms(pages, chunk_texts, lexicon)

    for i, terms in enumerate(terms_per_page):
        if not terms:
            continue  # 쓸 만한 단서가 없으면 이 슬라이드는 제목 신호를 쓰지 않는다
        total_w = sum(w for _, w in terms)
        if total_w <= 0:
            continue
        for j, ct in enumerate(lowered):
            hit_w = sum(w for t, w in terms if t.lower() in ct)
            if hit_w:
                boost[i, j] = min(1.0, hit_w / total_w)
    return boost


def _start_edge(scores: np.ndarray, window: int = START_EDGE_WINDOW) -> np.ndarray:
    """점수가 '오르기 시작하는' 지점을 찾는다 (변화점 탐지).

    각 조각 j에 대해 [j, j+window) 평균에서 [j-window, j) 평균을 뺀다.
    앞에서는 안 맞다가 여기서부터 맞기 시작하면 값이 커진다.
    한 칸 차이만 보면 잡음에 흔들리므로 몇 조각을 평균 낸다.
    """
    n_pages, n_chunks = scores.shape
    edge = np.zeros_like(scores)
    if n_chunks < 3:
        return edge

    pad = np.concatenate([np.zeros((n_pages, 1), dtype=scores.dtype), scores], axis=1)
    cum = np.cumsum(pad, axis=1)

    for j in range(1, n_chunks):
        f_end = min(j + window, n_chunks)
        b_start = max(0, j - window)
        fwd = (cum[:, f_end] - cum[:, j]) / max(1, f_end - j)
        bwd = (cum[:, j] - cum[:, b_start]) / max(1, j - b_start)
        edge[:, j] = np.maximum(0.0, fwd - bwd)
    return edge


def _first_hit(hit: np.ndarray, gap: int = REINTRO_GAP) -> np.ndarray:
    """주제어를 '다시 꺼낸' 자리를 1로 남긴다.

    전사본 전체에서 딱 한 번, 맨 처음 등장만 인정하면 문제가 생긴다.
    슬라이드 16·17·18 처럼 제목이 같으면 그 '맨 처음'은 슬라이드 16 자리이고,
    17·18 의 앵커가 거기로 끌려간다 (실측: 정답보다 7칸·10칸 빠름).

    그래서 '앞 gap개 조각에 그 낱말이 없었다면 여기서 다시 꺼낸 것'으로 본다.
    교수님이 주제를 다시 언급하며 새 슬라이드로 넘어가는 지점을 잡아낸다.
    """
    n_pages, n_chunks = hit.shape
    out = np.zeros_like(hit)
    if n_chunks == 0:
        return out
    for j in range(n_chunks):
        lo = max(0, j - gap)
        if j == 0:
            recent = np.zeros(n_pages, dtype=hit.dtype)
        else:
            recent = hit[:, lo:j].max(axis=1)
        out[:, j] = np.maximum(0.0, hit[:, j] - recent)
    return out


def match_pages_to_chunks(
    pages: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    page_embeddings: np.ndarray,
    chunk_embeddings: np.ndarray,
) -> tuple[list[list[dict[str, Any]]], list[str]]:
    page_texts = [
        p.get("embedding_text") or p.get("text", "") for p in pages
    ]
    chunk_texts = [c["text"] for c in chunks]
    scores = compute_final_scores(page_texts, chunk_texts, page_embeddings, chunk_embeddings)

    # 가점을 얹기 전 원점수. 0~1 범위이므로 신뢰도 판정은 이쪽으로 한다.
    base_scores = scores.copy()

    # 이 강의에 실제로 쓰인 낱말 사전 (붙어 있는 제목을 쪼갤 때 쓴다)
    lexicon = build_lexicon(pages, chunk_texts)

    # 슬라이드마다 쓸 만한 단서 낱말을 고른다 (흔한 말·발화에 없는 말은 버린다).
    signal_terms = build_signal_terms(pages, chunk_texts, lexicon)

    # 제목 부스트를 additive로 얹는다 (dense 우위를 유지하되 제목 일치를 반영).
    title_boost = _title_boost_matrix(
        pages, chunk_texts, lexicon, signal_terms=signal_terms
    )
    scores = scores + TITLE_BOOST_WEIGHT * title_boost

    # A-2. 슬라이드는 "여기서부터 시작"하는 자리가 있다. 그 변곡점을 가점한다.
    if START_EDGE_WEIGHT > 0:
        scores = scores + START_EDGE_WEIGHT * _start_edge(scores)
    # 제목 용어가 처음 등장하는 조각도 시작점일 가능성이 높다.
    if TITLE_START_WEIGHT > 0:
        scores = scores + TITLE_START_WEIGHT * _first_hit(
            (title_boost > 0).astype(np.float32)
        )

    page_types = [classify_page_type(p.get("text", "")) for p in pages]
    for p, ptype in zip(pages, page_types):
        p["page_type"] = ptype

    return select_monotonic_matches(
        scores, chunks, gate_scores=base_scores, page_types=page_types
    )
