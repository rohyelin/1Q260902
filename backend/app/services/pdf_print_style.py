"""인쇄물 스타일 PDF를 백엔드에서 직접 만든다 (브라우저 없이).

프론트엔드의 PrintView.tsx 와 같은 레이아웃을 PyMuPDF `insert_htmlbox` 로 그린다.
좌표에 글자를 찍던 pdf_export.py 와 달리 HTML/CSS로 렌더링하므로
볼드·자간·배경 박스·불릿이 그대로 먹는다.

구성
    표지            차시 / 제목 / 교수님
    슬라이드 n장     가로 A4 한 장 = 슬라이드 한 장
                    왼쪽 60% 강의록 + 핵심 정리 / 오른쪽 40% 교수님 설명
    부록            정리본(핵심 정리 모아보기) → 전체 정리본 → 퀴즈 → 정답

pdf_export.py 는 건드리지 않는다 (기존 다운로드 버튼은 그대로 동작).
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

import fitz

# ── 지면 (pt 단위, 1mm = 2.8346pt) ─────────────────────────
MM = 2.834645
PAGE_W, PAGE_H = 841.89, 595.28  # A4 가로
MARGIN = 12 * MM
GAP = 7 * MM

CONTENT_W = PAGE_W - 2 * MARGIN
CONTENT_H = PAGE_H - 2 * MARGIN
LEFT_W = (CONTENT_W - GAP) * 0.60
RIGHT_W = (CONTENT_W - GAP) * 0.40

ACCENT = "#C4A55F"
INK = "#3F3F46"
MUTED = "#8A8A80"

# 분량이 많으면 글자를 한 단계씩 조인다 (한 장을 넘기지 않게)
DENSITY = {
    "loose": (11.0, 1.75),
    "mid": (10.0, 1.65),
    "tight": (9.0, 1.55),
}


# MuPDF의 HTML 렌더러는 유니코드 위첨자·아래첨자 글리프를 못 그린다.
# 그대로 두면 10⁻⁹ 이 '10' + NUL 로 렌더링돼 글자가 실제로 사라진다.
# → <sup>/<sub> 태그로 바꿔서 넣는다 (이건 정상 렌더링됨).
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ", "0123456789+-=()n")
_SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎", "0123456789+-=()")
_SUP_RE = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ]+")
_SUB_RE = re.compile(r"[₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎]+")


def _esc(s: str) -> str:
    """HTML 이스케이프 + 렌더링 안 되는 첨자 문자를 태그로 치환."""
    out = _html.escape(s or "", quote=False)
    out = _SUP_RE.sub(lambda m: f"<sup>{m.group(0).translate(_SUP)}</sup>", out)
    out = _SUB_RE.sub(lambda m: f"<sub>{m.group(0).translate(_SUB)}</sub>", out)
    return out


_HANGUL_RE = re.compile(r"[가-힣]")


def _nowrap_words(html_text: str, max_len: int = 16) -> str:
    """한글 낱말이 줄바꿈에서 쪼개지지 않게 감싼다.

    MuPDF의 HTML 렌더러는 한글을 아무 글자에서나 끊어서 '상피세포가' 가
    '상피세' / '포가' 처럼 잘린다. CSS의 word-break: keep-all 은 무시하지만
    white-space: nowrap 은 먹으므로, 띄어쓰기 단위로 감싸 준다.

    너무 긴 낱말까지 묶으면 칸을 넘칠 수 있어 max_len 이하만 처리하고,
    태그가 섞인 조각(하이라이트 등)은 건드리지 않는다.
    """
    out: list[str] = []
    for tok in html_text.split(" "):
        if (
            tok
            and len(tok) <= max_len
            and "<" not in tok
            and ">" not in tok
            and "&" not in tok
            and _HANGUL_RE.search(tok)
        ):
            out.append(f'<span style="white-space:nowrap">{tok}</span>')
        else:
            out.append(tok)
    return " ".join(out)


def _base_css(box_color: str, text_color: str) -> str:
    return f"""
* {{ font-family: serif; color: {text_color}; }}
.label {{
  font-family: sans-serif; font-size: 8px; letter-spacing: 1.4px;
  color: {MUTED}; margin: 0 0 7px 0;
}}
.meta {{ font-family: sans-serif; font-size: 8px; letter-spacing: 1.2px; color: {MUTED}; margin: 0; }}
.box {{ background: {box_color}; padding: 12px 14px; }}
ul {{ margin: 0; padding-left: 14px; }}
li {{ margin-bottom: 5px; }}
p {{ margin: 0 0 8px 0; }}
p:last-child {{ margin-bottom: 0; }}
.time {{ font-family: sans-serif; font-size: 7.5px; color: {MUTED}; margin: 0 0 2px 0; }}
b {{ font-weight: bold; }}
mark {{ background: #F6E7A8; }}
h1 {{ font-size: 22px; font-weight: bold; margin: 0 0 4px 0; }}
h2 {{ font-size: 13px; font-weight: bold; margin: 10px 0 4px 0; }}
.cover-sess {{ font-family: sans-serif; font-size: 10px; letter-spacing: 4px; color: {MUTED}; text-align: center; margin: 0 0 22px 0; }}
.cover-title {{ font-size: 28px; font-weight: bold; text-align: center; margin: 0 0 26px 0; line-height: 1.4; }}
.cover-prof {{ font-size: 12px; color: {MUTED}; text-align: center; margin: 0; }}
.rule {{ border-top: 1px solid {ACCENT}; width: 60px; margin: 0 auto 26px auto; }}
"""


def _script_body(s: dict[str, Any], readability: bool) -> str:
    base = (s.get("corrected_text") or s.get("raw_text") or "").strip()
    if readability:
        return (s.get("clean_text") or base).strip()
    return base


def _highlight(text: str, keywords: list[str]) -> str:
    """키워드를 <mark>로 감싼다.

    반드시 한 번의 분할로 처리해야 한다. 키워드를 하나씩 순차 치환하면
    'Monochorionic' 을 감싼 뒤 'chorion' 이 그 안쪽까지 다시 치환해
    <mark>Mono<mark>chorion</mark>ic</mark> 처럼 태그가 겹치고,
    HTML이 깨져 그 뒤 문장이 통째로 사라진다.
    """
    kws = sorted({k for k in keywords if k and len(k) > 1}, key=len, reverse=True)
    if not kws:
        return _esc(text)
    pattern = re.compile("|".join(re.escape(k) for k in kws))
    out: list[str] = []
    pos = 0
    for m in pattern.finditer(text):
        out.append(_esc(text[pos : m.start()]))
        out.append(f"<mark>{_esc(m.group(0))}</mark>")
        pos = m.end()
    out.append(_esc(text[pos:]))
    return "".join(out)


# 글자를 이 비율보다 더 줄이지 않는다. 여기까지 줄여도 안 들어가면
# 억지로 욱여넣지 말고 '이어서' 장을 만들어 나눠 싣는다.
MIN_SCALE = 0.80


def _fit(page: fitz.Page, rect: fitz.Rect, html: str, css: str) -> bool:
    """넘치면 MIN_SCALE까지 줄여 담는다. 그래도 안 되면 더 줄여서라도 그린다.

    주의: insert_htmlbox 는 scale_low 로도 안 들어가면 **아무것도 그리지 않고**
    spare 를 -1 로 돌려준다. 반환값을 반드시 확인해야 한다.
    """
    try:
        spare, _ = page.insert_htmlbox(rect, html, css=css, scale_low=MIN_SCALE)
        if spare >= 0:
            return True
    except Exception:
        pass
    # 최후 수단: 제한 없이 축소 (작아지더라도 내용이 사라지진 않게)
    try:
        page.insert_htmlbox(rect, html, css=css)
    except Exception:
        return False
    return False


def _cover(doc: fitz.Document, cover: dict[str, str], css: str) -> None:
    page = doc.new_page(width=PAGE_W, height=PAGE_H)

    # 위쪽 덩어리: 차시 + 제목
    top = []
    if cover.get("session"):
        top.append(f"<p class='cover-sess'>{_esc(cover['session'])}</p>")
    top.append(f"<p class='cover-title'>{_esc(cover.get('title') or '강의 정리본')}</p>")
    _fit(
        page,
        fitz.Rect(MARGIN, PAGE_H * 0.30, PAGE_W - MARGIN, PAGE_H * 0.56),
        "".join(top),
        css,
    )

    # 가운데 금색 선 — HTML의 margin:auto가 안 먹어서 직접 그린다
    mid_y = PAGE_H * 0.60
    half = 30
    page.draw_line(
        fitz.Point(PAGE_W / 2 - half, mid_y),
        fitz.Point(PAGE_W / 2 + half, mid_y),
        color=(0.769, 0.647, 0.373),
        width=0.8,
    )

    if cover.get("professor"):
        _fit(
            page,
            fitz.Rect(MARGIN, PAGE_H * 0.66, PAGE_W - MARGIN, PAGE_H * 0.78),
            f"<p class='cover-prof'>{_esc(cover['professor'])}</p>",
            css,
        )


def _take_that_fits(
    rect: fitz.Rect, blocks: list[str], css: str, wrap: str
) -> int:
    """rect 안에 몇 개까지 들어가는지 이분탐색. 최소 1개는 넣는다(무한루프 방지)."""
    if not blocks:
        return 0
    lo, hi, best = 1, len(blocks), 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if _fits(rect, wrap.format(body="".join(blocks[:mid])), css):
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def _slide_page(
    doc: fitz.Document,
    src: fitz.Document,
    page_idx: int,
    page_num: int,
    total: int,
    summary: list[str],
    scripts: list[dict[str, Any]],
    css: str,
    *,
    readability: bool,
    highlight: bool,
    include_summary: bool,
) -> None:
    """슬라이드 한 장을 그린다.

    내용이 넘치면 '이어서' 장을 만들되, 그 장에도 **강의록을 다시 얹는다**.
    어느 장을 펴도 항상 [강의록 + 스크립트]가 같이 보이게 하기 위함.
    """
    summary = summary if include_summary else []
    scr_chars = sum(len(_script_body(s, readability)) for s in scripts)
    sum_chars = sum(len(s) for s in summary)

    # 강의록 높이 상한.
    # 예전에는 정리 분량에 따라 62mm까지 줄였는데, 4:3 슬라이드(자연 높이 120mm)가
    # 절반 폭으로 쪼그라들었다. 넘치는 내용은 '이어서' 장이 받아주므로
    # 이제는 세로로 긴 원고만 제한하고 보통 슬라이드는 폭을 꽉 채운다.
    #   16:9 → 90mm, 4:3 → 120mm 이라 둘 다 그대로 들어간다.
    img_max = CONTENT_H if not summary else 0.68 * CONTENT_H

    spage = src[page_idx]
    sw, sh = spage.rect.width, spage.rect.height

    def _img_size(part_no: int) -> tuple[float, float]:
        """첫 장은 크게, 이어지는 장은 참고용으로 작게.

        이어지는 장에서까지 강의록을 크게 두면 (특히 4:3처럼 세로로 긴 슬라이드)
        글자 자리가 없어 장수만 계속 불어난다. 이미 한 번 크게 봤으므로
        이어지는 장에서는 '어느 슬라이드인지' 알아볼 정도면 충분하다.
        """
        cap = img_max if part_no == 1 else 0.42 * CONTENT_H
        w = LEFT_W if part_no == 1 else LEFT_W * 0.72
        h = w * sh / sw
        if h > cap:
            h = cap
            w = h * sw / sh
        return w, h

    # ── 각 섹션을 '나눌 수 있는 조각'으로 만들어 둔다 ──
    sum_size, sum_lead = DENSITY[
        "tight" if sum_chars > 800 else "mid" if sum_chars > 450 else "loose"
    ]
    sum_blocks = [
        f"<li>{_nowrap_words(_esc(s.lstrip('-•* ').strip()))}</li>" for s in summary
    ]
    SUM_WRAP = (
        "<div class='box'><p class='label'>{label}</p>"
        f"<ul style='font-size:{sum_size}px; line-height:{sum_lead}'>{{body}}</ul></div>"
    )

    scr_size, scr_lead = DENSITY[
        "tight" if scr_chars > 1500 else "mid" if scr_chars > 850 else "loose"
    ]
    scr_blocks: list[str] = []
    for s in scripts:
        body = _script_body(s, readability)
        if not body:
            continue
        st, et = s.get("start_time") or "", s.get("end_time") or ""
        head = f"<p class='time'>{_esc(st)} – {_esc(et)}</p>" if (st or et) else ""
        text = _highlight(body, s.get("highlights") or []) if highlight else _esc(body)
        text = _nowrap_words(text)
        # 시간표시와 본문은 한 덩어리로 묶어야 따로 떨어지지 않는다
        scr_blocks.append(
            head + f"<p style='font-size:{scr_size}px; line-height:{scr_lead}'>{text}</p>"
        )
    SCR_WRAP = (
        "<div class='box'><p class='label'>{label}</p>{body}</div>"
    )

    # ── 내용을 다 실을 때까지 장을 이어 만든다 (매 장에 강의록을 다시 얹는다) ──
    x0, y0 = MARGIN, MARGIN
    rx = MARGIN + LEFT_W + GAP
    rest_sum, rest_scr = sum_blocks, scr_blocks
    part = 0

    while True:
        part += 1
        page = doc.new_page(width=PAGE_W, height=PAGE_H)

        if part == 1:
            # 첫 장에만 강의록을 얹는다.
            draw_w, draw_h = _img_size(1)
            img_rect = fitz.Rect(x0, y0, x0 + draw_w, y0 + draw_h)
            try:
                page.show_pdf_page(img_rect, src, page_idx)
                page.draw_rect(img_rect, color=(0.85, 0.85, 0.85), width=0.5)
            except Exception:
                pass
            cursor = y0 + draw_h + 4 * MM
            tag = f"슬라이드 {page_num} / {total}"
        else:
            # 이어지는 장은 글자만. 지면을 좌우 절반씩 넉넉히 쓴다.
            cursor = y0
            tag = f"슬라이드 {page_num} / {total} — 이어서 ({part})"

        _fit(
            page,
            fitz.Rect(x0, cursor, x0 + LEFT_W, cursor + 5 * MM),
            f"<p class='meta'>{_esc(tag)}</p>",
            css,
        )
        cursor += 5 * MM

        if part == 1:
            left_rect = fitz.Rect(x0, cursor, x0 + LEFT_W, MARGIN + CONTENT_H)
            right_rect = fitz.Rect(rx, MARGIN, rx + RIGHT_W, MARGIN + CONTENT_H)
        else:
            col_w = (CONTENT_W - GAP) / 2
            left_rect = fitz.Rect(x0, cursor, x0 + col_w, MARGIN + CONTENT_H)
            right_rect = fitz.Rect(
                x0 + col_w + GAP, cursor, PAGE_W - MARGIN, MARGIN + CONTENT_H
            )

        if part == 1:
            # 첫 장은 의도한 배치 그대로: 왼쪽 핵심 정리 / 오른쪽 교수님 설명
            if rest_sum:
                wrap = SUM_WRAP.replace("{label}", "핵심 정리")
                n = _take_that_fits(left_rect, rest_sum, css, wrap)
                _fit(page, left_rect, wrap.format(body="".join(rest_sum[:n])), css)
                rest_sum = rest_sum[n:]

            if rest_scr:
                # 오른쪽은 언제나 '교수님 설명' 자리로만 쓴다.
                # (빈 자리에 핵심 정리를 흘려 넣으면 좌/우 역할이 섞여 형식이 흐트러진다)
                wrap = SCR_WRAP.replace("{label}", "교수님 설명")
                n = _take_that_fits(right_rect, rest_scr, css, wrap)
                _fit(page, right_rect, wrap.format(body="".join(rest_scr[:n])), css)
                rest_scr = rest_scr[n:]
            else:
                _fit(
                    page,
                    right_rect,
                    "<div class='box'><p class='label'>교수님 설명</p>"
                    "<p style='font-size:10px; color:#9a9a92'>이 슬라이드에는 매칭된 설명이 없습니다.</p></div>",
                    css,
                )
        else:
            # 이어지는 장에서도 칸의 역할은 그대로 지킨다.
            #   왼쪽 = 핵심 정리 / 오른쪽 = 교수님 설명
            # (섞어서 채우면 '정리 자리에 스크립트가 있다'고 읽혀 형식이 흐트러진다)
            if rest_sum:
                wrap = SUM_WRAP.replace("{label}", "핵심 정리 (이어서)")
                n = _take_that_fits(left_rect, rest_sum, css, wrap)
                _fit(page, left_rect, wrap.format(body="".join(rest_sum[:n])), css)
                rest_sum = rest_sum[n:]

            if rest_scr:
                wrap = SCR_WRAP.replace("{label}", "교수님 설명 (이어서)")
                n = _take_that_fits(right_rect, rest_scr, css, wrap)
                _fit(page, right_rect, wrap.format(body="".join(rest_scr[:n])), css)
                rest_scr = rest_scr[n:]

        if not rest_sum and not rest_scr:
            break


def _fits(rect: fitz.Rect, html: str, css: str) -> bool:
    """그리기 전에 임시 문서로 재본다. _fit 과 같은 축소 한계를 써야 의미가 있다."""
    probe = fitz.open()
    try:
        p = probe.new_page(width=PAGE_W, height=PAGE_H)
        spare, _ = p.insert_htmlbox(rect, html, css=css, scale_low=MIN_SCALE)
        return spare >= 0
    except Exception:
        return False
    finally:
        probe.close()


def _digest_pages(
    doc: fitz.Document,
    css: str,
    title: str,
    subtitle: str,
    blocks: list[str],
) -> None:
    """부록 한 섹션. 한 장에 안 들어가면 자동으로 다음 장으로 넘긴다.

    blocks: 나눌 수 있는 최소 단위의 HTML 조각들 (예: 슬라이드 하나 분량)
    """
    if not blocks:
        return

    head_h = 18 * MM
    body_rect = fitz.Rect(
        MARGIN, MARGIN + head_h, PAGE_W - MARGIN, MARGIN + CONTENT_H
    )

    idx = 0
    first = True
    while idx < len(blocks):
        # 이 장에 들어갈 만큼만 욕심껏 담는다
        lo, hi, best = 1, len(blocks) - idx, 1
        while lo <= hi:
            mid = (lo + hi) // 2
            html = f"<div class='box'>{''.join(blocks[idx : idx + mid])}</div>"
            if _fits(body_rect, html, css):
                best, lo = mid, mid + 1
            else:
                hi = mid - 1

        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        label = title if first else f"{title} (이어서)"
        _fit(
            page,
            fitz.Rect(MARGIN, MARGIN, PAGE_W - MARGIN, MARGIN + head_h),
            f"<h1>{_esc(label)}</h1>"
            + (f"<p class='meta'>{_esc(subtitle)}</p>" if subtitle and first else ""),
            css,
        )
        html = f"<div class='box'>{''.join(blocks[idx : idx + best])}</div>"
        _fit(page, body_rect, html, css)
        idx += best
        first = False


def build_print_style_pdf(
    pdf_path: str,
    page_summaries: dict[int, list[str]],
    page_scripts: dict[int, list[dict[str, Any]]],
    output_path: str,
    *,
    cover: dict[str, str] | None = None,
    box_color: str | None = None,
    text_color: str | None = None,
    readability: bool = True,
    highlight: bool = True,
    include_summary: bool = True,
    lecture_document: dict[str, Any] | None = None,
    page_quizzes: dict[int, list[dict[str, str]]] | None = None,
) -> tuple[str, list[str]]:
    """인쇄물 스타일 PDF를 만든다. (경로, 경고 목록) 반환."""
    warnings: list[str] = []
    css = _base_css(box_color or "#FAF9F5", text_color or INK)

    src = fitz.open(pdf_path)
    out = fitz.open()
    try:
        if cover and any(cover.values()):
            _cover(out, cover, css)

        total = len(src)
        filled = 0
        for i in range(total):
            n = i + 1
            scripts = page_scripts.get(n) or []
            if scripts:
                filled += 1
            _slide_page(
                out,
                src,
                i,
                n,
                total,
                page_summaries.get(n) or [],
                scripts,
                css,
                readability=readability,
                highlight=highlight,
                include_summary=include_summary,
            )

        if filled == 0:
            warnings.append("매칭된 스크립트가 있는 페이지가 없습니다.")

        # ── 부록 1: 정리본 (추가 AI 호출 없이 기존 요약 재조합) ──
        if include_summary:
            with_sum = [
                (n, page_summaries.get(n) or [])
                for n in range(1, total + 1)
                if page_summaries.get(n)
            ]
            if with_sum:
                blocks = [
                    f"<p class='meta' style='margin-top:8px'>슬라이드 {n}</p>"
                    + "<ul style='font-size:9.5px; line-height:1.6'>"
                    + "".join(
                        f"<li>{_nowrap_words(_esc(s.lstrip('-•* ').strip()))}</li>"
                        for s in items
                    )
                    + "</ul>"
                    for n, items in with_sum
                ]
                _digest_pages(
                    out, css, "정리본", "슬라이드 핵심 정리 모아 보기", blocks
                )

        # ── 부록 2: 전체 정리본 ──
        doc_note = lecture_document or {}
        if doc_note.get("title"):
            parts: list[str] = []
            if doc_note.get("key_summary"):
                parts.append("<h2>핵심 요약</h2><ul style='font-size:10px; line-height:1.65'>")
                parts += [f"<li>{_esc(s)}</li>" for s in doc_note["key_summary"]]
                parts.append("</ul>")
            for node in doc_note.get("concept_structure") or []:
                parts.append(f"<h2>{_esc(node.get('heading', ''))}</h2>")
                if node.get("items"):
                    parts.append("<ul style='font-size:10px; line-height:1.6'>")
                    parts += [f"<li>{_esc(x)}</li>" for x in node["items"]]
                    parts.append("</ul>")
                for child in node.get("children") or []:
                    parts.append(
                        f"<p style='font-size:10px; font-weight:bold; margin:6px 0 2px 0'>"
                        f"{_esc(child.get('heading',''))}</p>"
                    )
                    if child.get("items"):
                        parts.append("<ul style='font-size:9.5px; line-height:1.6'>")
                        parts += [f"<li>{_esc(x)}</li>" for x in child["items"]]
                        parts.append("</ul>")
            if doc_note.get("exam_questions"):
                parts.append("<h2>시험에 이렇게 나온다</h2><ul style='font-size:10px; line-height:1.6'>")
                parts += [f"<li>{_esc(q)}</li>" for q in doc_note["exam_questions"]]
                parts.append("</ul>")
            if doc_note.get("confusing_points"):
                parts.append("<h2>헷갈리는 부분</h2><ul style='font-size:10px; line-height:1.6'>")
                parts += [f"<li>{_esc(c)}</li>" for c in doc_note["confusing_points"]]
                parts.append("</ul>")
            _digest_pages(
                out, css, doc_note["title"], doc_note.get("subtitle", ""), parts
            )

        # ── 부록 3·4: 퀴즈 / 정답 ──
        quizzes = page_quizzes or {}
        items: list[tuple[int, dict[str, str]]] = []
        for n in sorted(quizzes):
            for q in quizzes[n] or []:
                items.append((n, q))
        if items:
            for label, key in (("복습 퀴즈", "question"), ("퀴즈 정답", "answer")):
                blocks = [
                    f"<p style='font-size:10px; line-height:1.7; margin:0 0 7px 0'>"
                    f"<b>{i}.</b> {_esc(q.get(key, ''))}</p>"
                    for i, (_, q) in enumerate(items, start=1)
                ]
                _digest_pages(out, css, label, "", blocks)

        out.save(output_path, garbage=4, deflate=True)
    finally:
        out.close()
        src.close()

    return output_path, warnings
