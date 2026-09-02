from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz

NOTE_HEADER = "핵심 정리"
NOTE_BG = (0.965, 0.973, 1.0)
NOTE_BORDER = (0.55, 0.65, 0.85)
NOTE_TITLE_COLOR = (0.12, 0.22, 0.55)
NOTE_TEXT_COLOR = (0.10, 0.12, 0.18)
EXAMPLE_COLOR = (0.45, 0.32, 0.05)


def hex_to_rgb(hex_str: str | None) -> tuple[float, float, float] | None:
    """'#rrggbb' 문자열을 0~1 RGB 튜플로 변환. 형식이 틀리면 None."""
    if not hex_str:
        return None
    s = hex_str.strip().lstrip("#")
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def _load_cjk_font() -> fitz.Font:
    """한글 렌더링이 보장되는 폰트를 로드한다 (PyMuPDF 내장 CJK 우선)."""
    for name in ("korea", "cjk", "china-s"):
        try:
            return fitz.Font(name)
        except Exception:
            continue
    for path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    ):
        if Path(path).exists():
            try:
                return fitz.Font(fontfile=path)
            except Exception:
                continue
    raise RuntimeError("한글 폰트를 로드할 수 없습니다.")


def _wrap_text(
    text: str,
    font: fitz.Font,
    fontsize: float,
    max_width: float,
    indent: str = "",
) -> list[str]:
    """폰트 실측 너비 기준으로 텍스트를 줄바꿈한다 (한글은 아무 곳에서나 개행 가능)."""
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if font.text_length(candidate, fontsize) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = indent + ch
    if current.strip():
        lines.append(current)
    return lines or [text]


def build_annotated_pdf(
    pdf_path: str,
    page_summaries: dict[int, list[str]],
    output_path: str,
    *,
    note_bg: tuple[float, float, float] | None = None,
    note_text: tuple[float, float, float] | None = None,
) -> tuple[str, list[str]]:
    """
    원본 슬라이드는 그대로 두고, 페이지 높이를 늘려 슬라이드 '아래'에
    핵심 정리 노트 영역을 붙인 새 PDF를 생성한다. (겹침 없음)
    page_summaries: {1-based page number: summary bullets}
    note_bg / note_text: 노트 박스 배경·글씨 색 (None이면 기본값)
    """
    warnings: list[str] = []
    font = _load_cjk_font()

    bg_color = note_bg or NOTE_BG
    text_color = note_text or NOTE_TEXT_COLOR
    title_color = note_text or NOTE_TITLE_COLOR

    src = fitz.open(pdf_path)
    out = fitz.open()
    annotated = 0

    try:
        for page_idx in range(len(src)):
            page_num = page_idx + 1
            spage = src[page_idx]
            w, h = spage.rect.width, spage.rect.height
            summary = page_summaries.get(page_num) or []

            if not summary:
                npage = out.new_page(width=w, height=h)
                npage.show_pdf_page(npage.rect, src, page_idx)
                continue

            fontsize = max(9.0, min(12.5, w / 80))
            line_h = fontsize * 1.55
            pad = max(14.0, w * 0.025)
            max_text_w = w - 2 * pad

            # bullet별 줄바꿈 계산 → 필요한 노트 영역 높이 산출
            wrapped: list[tuple[str, bool]] = []  # (line, is_example/answer 강조)
            for point in summary:
                clean = point.strip().lstrip("-•* ")
                is_example = clean.startswith("예)") or clean.startswith("→")
                is_question = clean.startswith("Q") and ". " in clean[:6]
                prefix = "  ▸ " if is_example else ("" if is_question else "• ")
                for j, ln in enumerate(
                    _wrap_text(prefix + clean, font, fontsize, max_text_w, indent="    ")
                ):
                    wrapped.append((ln, is_example))

            title_h = fontsize * 2.0
            note_h = pad + title_h + len(wrapped) * line_h + pad

            npage = out.new_page(width=w, height=h + note_h)
            # 원본 슬라이드 (벡터 그대로)
            npage.show_pdf_page(fitz.Rect(0, 0, w, h), src, page_idx)

            # 노트 배경 + 구분선
            npage.draw_rect(
                fitz.Rect(0, h, w, h + note_h), fill=bg_color, color=None, overlay=True
            )
            npage.draw_line(
                fitz.Point(0, h), fitz.Point(w, h), color=NOTE_BORDER, width=1.2
            )

            title_writer = fitz.TextWriter(npage.rect)
            body_writer = fitz.TextWriter(npage.rect)
            example_writer = fitz.TextWriter(npage.rect)

            y = h + pad + fontsize
            title_writer.append(
                fitz.Point(pad, y), NOTE_HEADER, font=font, fontsize=fontsize * 1.1
            )
            y += title_h

            for line, is_example in wrapped:
                writer = example_writer if is_example else body_writer
                writer.append(fitz.Point(pad, y), line, font=font, fontsize=fontsize)
                y += line_h

            title_writer.write_text(npage, color=title_color)
            body_writer.write_text(npage, color=text_color)
            example_writer.write_text(npage, color=EXAMPLE_COLOR)
            annotated += 1

        if annotated == 0:
            warnings.append("핵심 정리가 들어간 페이지가 없습니다. 원본 PDF를 그대로 저장합니다.")

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(out_file), garbage=4, deflate=True)
    finally:
        out.close()
        src.close()

    return str(output_path), warnings


def summaries_from_result(
    pages: list[dict[str, Any]], note_mode: str = "summary"
) -> dict[int, list[str]]:
    """페이지별 노트 라인 목록을 만든다. quiz 모드면 Q/A를 줄 형태로 변환."""
    result: dict[int, list[str]] = {}
    for page in pages:
        if note_mode == "quiz":
            quiz = page.get("quiz") or []
            lines: list[str] = []
            for qi, item in enumerate(quiz, start=1):
                q = item.get("question", "").strip()
                a = item.get("answer", "").strip()
                if not q:
                    continue
                lines.append(f"Q{qi}. {q}")
                if a:
                    lines.append(f"→ 정답: {a}")
            if lines:
                result[int(page["page"])] = lines
        else:
            summary = page.get("summary") or []
            if summary:
                result[int(page["page"])] = summary
    return result


SCRIPT_HEADER = "교수님 스크립트"
SCRIPT_BG = (0.955, 0.965, 0.955)
SCRIPT_BORDER = (0.61, 0.70, 0.61)
SCRIPT_TIME_COLOR = (0.30, 0.45, 0.33)


def scripts_from_result(pages: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """페이지별 매칭 스크립트를 {1-based page: [script,...]} 로 만든다."""
    result: dict[int, list[dict[str, Any]]] = {}
    for page in pages:
        ms = page.get("matched_scripts") or []
        if ms:
            result[int(page["page"])] = ms
    return result


def build_script_side_pdf(
    pdf_path: str,
    page_scripts: dict[int, list[dict[str, Any]]],
    output_path: str,
    *,
    note_bg: tuple[float, float, float] | None = None,
    note_text: tuple[float, float, float] | None = None,
    use_readability: bool = True,
) -> tuple[str, list[str]]:
    """슬라이드(강의록)를 왼쪽, 교수님 스크립트를 오른쪽에 나란히 붙인 PDF를 만든다.

    페이지 폭 = 슬라이드 폭 + 스크립트 칸 폭(=슬라이드 폭). 가로로 넓은 페이지.
    스크립트가 길면 페이지 높이를 아래로 늘려 담는다 (슬라이드는 좌상단 고정).
    page_scripts: {1-based page number: matched_scripts 리스트}
    use_readability: True면 문어체로 다듬은 clean_text를, False면 업로드한
        전사본 그대로(corrected_text)를 쓴다.
    """
    warnings: list[str] = []
    font = _load_cjk_font()

    bg_color = note_bg or SCRIPT_BG
    text_color = note_text or NOTE_TEXT_COLOR
    title_color = note_text or SCRIPT_TIME_COLOR

    src = fitz.open(pdf_path)
    out = fitz.open()
    filled = 0

    try:
        for page_idx in range(len(src)):
            page_num = page_idx + 1
            spage = src[page_idx]
            w, h = spage.rect.width, spage.rect.height
            scripts = page_scripts.get(page_num) or []

            script_w = w * 0.6  # 오른쪽 스크립트 칸 폭 (슬라이드보다 좁게)
            fontsize = max(9.0, min(12.5, w / 80))
            line_h = fontsize * 1.55
            pad = max(14.0, w * 0.025)
            max_text_w = script_w - 2 * pad
            title_h = fontsize * 2.2

            # 스크립트 줄 미리 계산 → 필요한 높이 산출
            lines: list[tuple[str, bool]] = []  # (line, is_time)
            for s in scripts:
                if use_readability:
                    body = (
                        s.get("clean_text")
                        or s.get("corrected_text")
                        or s.get("raw_text")
                        or ""
                    ).strip()
                else:
                    body = (s.get("corrected_text") or s.get("raw_text") or "").strip()
                if not body:
                    continue
                st = s.get("start_time") or ""
                et = s.get("end_time") or ""
                if st or et:
                    lines.append((f"[{st} ~ {et}]", True))
                for ln in _wrap_text(body, font, fontsize, max_text_w):
                    lines.append((ln, False))
                lines.append(("", False))  # 발화 사이 간격

            if not scripts:
                lines.append(("(이 슬라이드에 매칭된 발화가 없습니다)", False))
            else:
                filled += 1

            content_h = pad + title_h + len(lines) * line_h + pad
            page_h = max(h, content_h)
            page_w = w + script_w

            npage = out.new_page(width=page_w, height=page_h)
            # 왼쪽: 원본 슬라이드 (좌상단, 벡터 그대로)
            npage.show_pdf_page(fitz.Rect(0, 0, w, h), src, page_idx)
            # 오른쪽: 스크립트 칸 배경 + 구분선
            npage.draw_rect(
                fitz.Rect(w, 0, page_w, page_h), fill=bg_color, color=None, overlay=True
            )
            npage.draw_line(
                fitz.Point(w, 0), fitz.Point(w, page_h), color=SCRIPT_BORDER, width=1.2
            )

            title_writer = fitz.TextWriter(npage.rect)
            body_writer = fitz.TextWriter(npage.rect)
            time_writer = fitz.TextWriter(npage.rect)

            x0 = w + pad
            y = pad + fontsize
            title_writer.append(
                fitz.Point(x0, y), SCRIPT_HEADER, font=font, fontsize=fontsize * 1.1
            )
            y += title_h

            for line, is_time in lines:
                if line:
                    writer = time_writer if is_time else body_writer
                    writer.append(fitz.Point(x0, y), line, font=font, fontsize=fontsize)
                y += line_h

            title_writer.write_text(npage, color=title_color)
            time_writer.write_text(npage, color=SCRIPT_TIME_COLOR)
            body_writer.write_text(npage, color=text_color)

        if filled == 0:
            warnings.append("매칭된 스크립트가 있는 페이지가 없습니다.")

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(out_file), garbage=4, deflate=True)
    finally:
        out.close()
        src.close()

    return str(output_path), warnings


def build_slide_summary_script_pdf(
    pdf_path: str,
    page_summaries: dict[int, list[str]],
    page_scripts: dict[int, list[dict[str, Any]]],
    output_path: str,
    *,
    note_bg: tuple[float, float, float] | None = None,
    note_text: tuple[float, float, float] | None = None,
    use_readability: bool = True,
) -> tuple[str, list[str]]:
    """슬라이드(좌상단) + 핵심정리(오른쪽) + 교수님 스크립트(아래 전체)를 한 장에 담는다.

    page_summaries: {1-based page: 요약 줄 목록}
    page_scripts:   {1-based page: matched_scripts 리스트}
    use_readability: True면 문어체로 다듬은 clean_text를, False면 교정만 거친
        원문(corrected_text)을 쓴다. 같은 작업 결과로 두 버전을 뽑을 수 있다.
    """
    warnings: list[str] = []
    font = _load_cjk_font()

    sum_bg = note_bg or NOTE_BG
    sum_text = note_text or NOTE_TEXT_COLOR
    sum_title = note_text or NOTE_TITLE_COLOR

    src = fitz.open(pdf_path)
    out = fitz.open()
    filled = 0

    try:
        for page_idx in range(len(src)):
            page_num = page_idx + 1
            spage = src[page_idx]
            w, h = spage.rect.width, spage.rect.height
            summary = page_summaries.get(page_num) or []
            scripts = page_scripts.get(page_num) or []

            summary_w = w * 0.5  # 오른쪽 요약 칸 폭
            page_w = w + summary_w
            fontsize = max(9.0, min(12.5, w / 80))
            line_h = fontsize * 1.55
            pad = max(14.0, w * 0.025)
            title_h = fontsize * 2.0

            # 요약(오른쪽) 줄 계산
            sum_max_w = summary_w - 2 * pad
            sum_lines: list[tuple[str, bool]] = []
            for point in summary:
                clean = point.strip().lstrip("-•* ")
                is_example = clean.startswith("예)") or clean.startswith("→")
                prefix = "  ▸ " if is_example else "• "
                for ln in _wrap_text(prefix + clean, font, fontsize, sum_max_w, indent="    "):
                    sum_lines.append((ln, is_example))
            sum_h = pad + title_h + len(sum_lines) * line_h + pad
            top_h = max(h, sum_h)  # 상단(슬라이드/요약) 영역 높이

            # 스크립트(아래 전체) 줄 계산
            scr_max_w = page_w - 2 * pad
            scr_lines: list[tuple[str, bool]] = []
            for s in scripts:
                if use_readability:
                    body = (
                        s.get("clean_text")
                        or s.get("corrected_text")
                        or s.get("raw_text")
                        or ""
                    ).strip()
                else:
                    # 가독성(문어체) 변환 전 — 교정만 거친 실제 발화에 가까운 쪽
                    body = (s.get("corrected_text") or s.get("raw_text") or "").strip()
                if not body:
                    continue
                st = s.get("start_time") or ""
                et = s.get("end_time") or ""
                if st or et:
                    scr_lines.append((f"[{st} ~ {et}]", True))
                for ln in _wrap_text(body, font, fontsize, scr_max_w):
                    scr_lines.append((ln, False))
                scr_lines.append(("", False))
            if not scripts:
                scr_lines.append(("(이 슬라이드에 매칭된 발화가 없습니다)", False))
            else:
                filled += 1
            scr_h = pad + title_h + len(scr_lines) * line_h + pad

            page_h = top_h + scr_h
            npage = out.new_page(width=page_w, height=page_h)

            # 슬라이드 (좌상단)
            npage.show_pdf_page(fitz.Rect(0, 0, w, h), src, page_idx)
            # 요약 배경 (오른쪽 상단) + 경계선
            npage.draw_rect(fitz.Rect(w, 0, page_w, top_h), fill=sum_bg, color=None, overlay=True)
            npage.draw_line(fitz.Point(w, 0), fitz.Point(w, top_h), color=NOTE_BORDER, width=1.2)
            # 스크립트 배경 (아래 전체) + 경계선
            npage.draw_rect(fitz.Rect(0, top_h, page_w, page_h), fill=SCRIPT_BG, color=None, overlay=True)
            npage.draw_line(fitz.Point(0, top_h), fitz.Point(page_w, top_h), color=SCRIPT_BORDER, width=1.2)

            # 요약 글씨 (오른쪽)
            sum_title_w = fitz.TextWriter(npage.rect)
            sum_body_w = fitz.TextWriter(npage.rect)
            sum_ex_w = fitz.TextWriter(npage.rect)
            x0 = w + pad
            y = pad + fontsize
            sum_title_w.append(fitz.Point(x0, y), NOTE_HEADER, font=font, fontsize=fontsize * 1.1)
            y += title_h
            for line, is_ex in sum_lines:
                (sum_ex_w if is_ex else sum_body_w).append(
                    fitz.Point(x0, y), line, font=font, fontsize=fontsize
                )
                y += line_h
            sum_title_w.write_text(npage, color=sum_title)
            sum_body_w.write_text(npage, color=sum_text)
            sum_ex_w.write_text(npage, color=EXAMPLE_COLOR)

            # 스크립트 글씨 (아래)
            scr_title_w = fitz.TextWriter(npage.rect)
            scr_body_w = fitz.TextWriter(npage.rect)
            scr_time_w = fitz.TextWriter(npage.rect)
            x1 = pad
            y = top_h + pad + fontsize
            scr_title_w.append(fitz.Point(x1, y), SCRIPT_HEADER, font=font, fontsize=fontsize * 1.1)
            y += title_h
            for line, is_time in scr_lines:
                if line:
                    (scr_time_w if is_time else scr_body_w).append(
                        fitz.Point(x1, y), line, font=font, fontsize=fontsize
                    )
                y += line_h
            scr_title_w.write_text(npage, color=SCRIPT_TIME_COLOR)
            scr_time_w.write_text(npage, color=SCRIPT_TIME_COLOR)
            scr_body_w.write_text(npage, color=sum_text)

        if filled == 0:
            warnings.append("매칭된 스크립트가 있는 페이지가 없습니다.")

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(out_file), garbage=4, deflate=True)
    finally:
        out.close()
        src.close()

    return str(output_path), warnings


def _strip_md(text: str) -> str:
    return text.replace("**", "").strip()


def build_full_lecture_pdf(
    document: dict[str, Any],
    output_path: str,
    *,
    note_bg: tuple[float, float, float] | None = None,
    note_text: tuple[float, float, float] | None = None,
) -> tuple[str, list[str]]:
    """전체 정리본(lecture_document)을 A4 PDF로 렌더링한다."""
    warnings: list[str] = []
    font = _load_cjk_font()

    page_w, page_h = fitz.paper_size("a4")  # 595 x 842
    margin = 48.0
    content_w = page_w - 2 * margin
    bg = note_bg or (1.0, 1.0, 1.0)
    body_color = note_text or NOTE_TEXT_COLOR
    title_color = note_text or NOTE_TITLE_COLOR
    muted = (0.45, 0.48, 0.55)
    accent = (0.12, 0.45, 0.35)

    out = fitz.open()
    try:
        page = out.new_page(width=page_w, height=page_h)
        page.draw_rect(page.rect, fill=bg, color=None)

        y = margin
        writers: list[tuple[fitz.TextWriter, tuple[float, float, float]]] = []

        def new_page() -> None:
            nonlocal page, y, writers
            for tw, color in writers:
                tw.write_text(page, color=color)
            writers = []
            page = out.new_page(width=page_w, height=page_h)
            page.draw_rect(page.rect, fill=bg, color=None)
            y = margin

        def ensure_space(needed: float) -> None:
            nonlocal y
            if y + needed > page_h - margin:
                new_page()

        def write_lines(
            lines: list[str],
            *,
            fontsize: float,
            color: tuple[float, float, float],
            line_h: float | None = None,
            gap_after: float = 4.0,
        ) -> None:
            nonlocal y
            lh = line_h or fontsize * 1.45
            tw = fitz.TextWriter(page.rect)
            for line in lines:
                ensure_space(lh)
                tw.append(fitz.Point(margin, y + fontsize * 0.85), line, font=font, fontsize=fontsize)
                y += lh
            writers.append((tw, color))
            y += gap_after

        def section(title: str) -> None:
            nonlocal y
            ensure_space(36)
            y += 8
            write_lines([title], fontsize=13, color=title_color, gap_after=8)
            # 구분선
            ensure_space(4)
            page.draw_line(
                fitz.Point(margin, y),
                fitz.Point(page_w - margin, y),
                color=(0.85, 0.87, 0.9),
                width=0.8,
            )
            y += 10

        def bullets(items: list[str], *, prefix: str = "• ") -> None:
            for raw in items:
                text = _strip_md(str(raw))
                if not text:
                    continue
                wrapped = _wrap_text(prefix + text, font, 10.5, content_w, indent="  ")
                write_lines(wrapped, fontsize=10.5, color=body_color, gap_after=3)

        # --- 헤더 ---
        title = _strip_md(str(document.get("title") or "강의 정리본"))
        subtitle = _strip_md(str(document.get("subtitle") or ""))
        write_lines(
            _wrap_text(title, font, 20, content_w),
            fontsize=20,
            color=title_color,
            line_h=26,
            gap_after=6,
        )
        if subtitle:
            write_lines(
                _wrap_text(subtitle, font, 10, content_w),
                fontsize=10,
                color=muted,
                gap_after=14,
            )

        # --- 핵심 요약 ---
        key_summary = document.get("key_summary") or []
        if key_summary:
            section("핵심 요약")
            bullets(key_summary)

        # --- 개념 구조 ---
        def render_concept(node: dict[str, Any], depth: int = 0) -> None:
            heading = _strip_md(str(node.get("heading") or ""))
            indent = "  " * depth
            if heading:
                write_lines(
                    _wrap_text(f"{indent}{heading}", font, 11.5 if depth == 0 else 10.5, content_w),
                    fontsize=11.5 if depth == 0 else 10.5,
                    color=title_color if depth == 0 else body_color,
                    gap_after=3,
                )
            for item in node.get("items") or []:
                text = _strip_md(str(item))
                if not text:
                    continue
                wrapped = _wrap_text(f"{indent}▪ {text}", font, 10, content_w - depth * 8, indent=indent + "  ")
                write_lines(wrapped, fontsize=10, color=body_color, gap_after=2)
            callout = _strip_md(str(node.get("callout_question") or ""))
            if callout:
                wrapped = _wrap_text(f"{indent}※ {callout}", font, 10, content_w - depth * 8, indent=indent + "  ")
                write_lines(wrapped, fontsize=10, color=accent, gap_after=4)
            for child in node.get("children") or []:
                if isinstance(child, dict):
                    render_concept(child, depth + 1)

        concepts = document.get("concept_structure") or []
        if concepts:
            section("개념 구조")
            for node in concepts:
                if isinstance(node, dict):
                    render_concept(node)

        # --- 비교 표 ---
        comparisons = document.get("comparisons") or []
        if comparisons:
            section("비교 · 정리 표")
            for table in comparisons:
                if not isinstance(table, dict):
                    continue
                t_title = _strip_md(str(table.get("title") or "표"))
                slide_ref = table.get("slide_ref")
                if slide_ref:
                    t_title = f"{t_title}  (슬라이드 {slide_ref})"
                write_lines(
                    _wrap_text(t_title, font, 11, content_w),
                    fontsize=11,
                    color=title_color,
                    gap_after=4,
                )
                columns = [str(c) for c in (table.get("columns") or [])]
                rows = table.get("rows") or []
                if columns:
                    header = " | ".join(_strip_md(c) for c in columns)
                    write_lines(
                        _wrap_text(header, font, 9.5, content_w),
                        fontsize=9.5,
                        color=muted,
                        gap_after=2,
                    )
                for row in rows:
                    cells = row if isinstance(row, list) else [row]
                    line = " | ".join(_strip_md(str(c)) for c in cells)
                    write_lines(
                        _wrap_text(line, font, 9.5, content_w),
                        fontsize=9.5,
                        color=body_color,
                        gap_after=2,
                    )
                y += 6

        # --- 교수 강조 ---
        highlights = document.get("professor_highlights") or []
        if highlights:
            section("교수님이 강조한 포인트")
            for h in highlights:
                if not isinstance(h, dict):
                    continue
                quote = _strip_md(str(h.get("quote") or ""))
                expl = _strip_md(str(h.get("explanation") or ""))
                slide_ref = h.get("slide_ref")
                if quote:
                    label = f"“{quote}”"
                    if slide_ref:
                        label += f"  (슬라이드 {slide_ref})"
                    write_lines(
                        _wrap_text(label, font, 10.5, content_w),
                        fontsize=10.5,
                        color=title_color,
                        gap_after=2,
                    )
                if expl:
                    write_lines(
                        _wrap_text(f"→ {expl}", font, 10, content_w),
                        fontsize=10,
                        color=body_color,
                        gap_after=6,
                    )

        # --- 시험 ---
        exams = document.get("exam_questions") or []
        if exams:
            section("시험에서 이렇게 나온다")
            bullets(exams, prefix="□ ")

        # --- 헷갈리는 포인트 ---
        confusing = document.get("confusing_points") or []
        if confusing:
            section("헷갈리기 쉬운 포인트")
            bullets(confusing)

        for tw, color in writers:
            tw.write_text(page, color=color)

        if len(out) == 0:
            warnings.append("전체 정리본 내용이 비어 있습니다.")

        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out.save(str(out_file), garbage=4, deflate=True)
    finally:
        out.close()

    return str(output_path), warnings
