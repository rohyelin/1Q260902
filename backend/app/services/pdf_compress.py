"""PDF 용량 줄이기 — 노션 업로드 한도(PDF 20MB)에 맞추기 위한 유틸.

슬라이드를 통째로 얹은 결과 PDF는 25MB를 넘기 쉬운데, 노션 유료 플랜도
PDF는 20MB까지만 받는다. 여기서는 PDF 안에 박힌 이미지만 다시 압축한다
(텍스트·폰트는 그대로라 복사/검색이 계속 된다).

외부 프로그램(ghostscript 등) 없이 PyMuPDF만 쓴다.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pymupdf

# (이미지 재압축 기준 DPI, 목표 DPI, JPEG 품질) — 화질 좋은 것부터 시도한다.
_STEPS: list[tuple[int, int, int]] = [
    (200, 150, 80),  # 거의 손실 없음. 보통 여기서 절반 이하로 줄어든다.
    (150, 110, 70),  # 조금 더 세게
    (120, 90, 60),   # 최후의 수단 (사진 많은 슬라이드용)
]

MB = 1_000_000


def _size_mb(path: str | Path) -> float:
    return Path(path).stat().st_size / MB


def _rewrite(src: Path, dst: Path, dpi_threshold: int, dpi_target: int, quality: int) -> None:
    doc = pymupdf.open(str(src))
    try:
        doc.rewrite_images(
            dpi_threshold=dpi_threshold,
            dpi_target=dpi_target,
            quality=quality,
        )
        # subset_fonts() 는 쓰지 않는다.
        # 강의록에 박힌 한글 서브셋 폰트(MalgunGothic/HCRBatang 등)를 다시 쓰는데,
        # PyMuPDF·Ghostscript로는 멀쩡해 보여도 노션 미리보기(PDF.js)나 맥 미리보기에서
        # 글자 간격이 무너져 글자들이 한자리에 겹쳐 보이는 사례가 있었다.
        # 용량 이득은 10% 남짓이라 안정성과 바꿀 값어치가 없다.
        doc.save(str(dst), garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def compress_pdf(
    src_path: str | Path,
    out_path: str | Path | None = None,
    max_mb: float = 19.0,
) -> tuple[str, str]:
    """`max_mb` 밑으로 내려갈 때까지 이미지를 점점 세게 재압축한다.

    Args:
        src_path: 원본 PDF
        out_path: 결과 PDF 경로. None이면 원본 옆에 `*_compressed.pdf`로 만든다.
        max_mb: 목표 상한(MB). 노션 PDF 한도 20MB보다 살짝 낮게 잡아둔다.

    Returns:
        (결과 파일 경로, 사람이 읽을 수 있는 요약 문자열)

    이미 상한보다 작으면 아무것도 하지 않고 원본 경로를 그대로 돌려준다.
    모든 단계를 시도해도 상한을 못 넘기면, 그중 가장 작은 결과를 돌려주고
    요약 문자열에 그 사실을 적는다 (호출하는 쪽에서 판단하라는 뜻).
    """
    src = Path(src_path)
    before = _size_mb(src)
    if before <= max_mb:
        return str(src), f"{before:.1f}MB — 압축 불필요"

    dst = Path(out_path) if out_path else src.with_name(f"{src.stem}_compressed.pdf")
    dst.parent.mkdir(parents=True, exist_ok=True)

    best_size: float | None = None
    best_tmp: Path | None = None

    for idx, (threshold, target, quality) in enumerate(_STEPS):
        tmp = dst.with_name(f"{dst.stem}.step{idx}.pdf")
        try:
            _rewrite(src, tmp, threshold, target, quality)
        except Exception:
            tmp.unlink(missing_ok=True)
            continue

        size = _size_mb(tmp)
        if best_size is None or size < best_size:
            if best_tmp is not None:
                best_tmp.unlink(missing_ok=True)
            best_size, best_tmp = size, tmp
        else:
            tmp.unlink(missing_ok=True)

        if size <= max_mb:
            break

    if best_tmp is None:
        return str(src), f"{before:.1f}MB — 압축 실패(원본 사용)"

    best_tmp.replace(dst)
    assert best_size is not None
    pct = 100 * (1 - best_size / before)
    note = "" if best_size <= max_mb else f" ⚠️ 여전히 {max_mb:.0f}MB 초과"
    return str(dst), f"{before:.1f}MB → {best_size:.1f}MB ({pct:.0f}% 감소){note}"


def compress_in_place(src_path: str | Path, max_mb: float = 19.0) -> str:
    """원본을 압축본으로 덮어쓴다. 요약 문자열만 돌려준다."""
    src = Path(src_path)
    out, report = compress_pdf(src, src.with_name(f"{src.stem}.__tmp__.pdf"), max_mb=max_mb)
    if Path(out) != src:
        shutil.move(out, src)
    return report


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("사용법: python -m app.services.pdf_compress <파일.pdf> [최대MB]")
        raise SystemExit(1)
    limit = float(sys.argv[2]) if len(sys.argv) > 2 else 19.0
    path, summary = compress_pdf(sys.argv[1], max_mb=limit)
    print(summary)
    print(path)
