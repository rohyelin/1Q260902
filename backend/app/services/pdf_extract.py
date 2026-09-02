from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz


def extract_pdf(pdf_path: str, pages_dir: Path, dpi: int = 150) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    pages: list[dict[str, Any]] = []
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    empty_page_count = 0
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        blocks = page.get_text("blocks")
        sorted_blocks = sorted(blocks, key=lambda b: (b[1], b[0]))
        texts = []
        for block in sorted_blocks:
            if len(block) >= 5 and block[4].strip():
                texts.append(block[4].strip())
        page_text = "\n".join(texts).strip()

        if len(page_text) < 20:
            empty_page_count += 1

        page_num = page_idx + 1
        image_name = f"page_{page_num:03d}.png"
        image_path = pages_dir / image_name
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        pix.save(str(image_path))

        pages.append(
            {
                "page": page_num,
                "text": page_text,
                "image_path": str(image_path),
            }
        )

    doc.close()

    if pages and empty_page_count > len(pages) * 0.5:
        warnings.append("이 PDF는 이미지 기반일 수 있어 OCR이 필요합니다.")

    return pages, warnings
