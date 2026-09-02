from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_settings

ALLOWED_PDF_EXTENSIONS = {".pdf"}
# 전사본(이미 텍스트로 된 강의 스크립트). 텍스트/자막뿐 아니라 PDF·워드(docx)도 허용
# (업로드 후 백엔드에서 텍스트를 추출한다).
ALLOWED_TRANSCRIPT_EXTENSIONS = {".txt", ".md", ".text", ".vtt", ".srt", ".pdf", ".docx"}
MAX_TRANSCRIPT_SIZE_MB = 50


def get_job_dir(job_id: str) -> Path:
    settings = get_settings()
    job_dir = settings.storage_path / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def get_pages_dir(job_id: str) -> Path:
    pages_dir = get_job_dir(job_id) / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    return pages_dir


def _validate_extension(filename: str, allowed: set[str]) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"허용되지 않는 파일 형식입니다: {ext}. 허용: {', '.join(sorted(allowed))}",
        )
    return ext


def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 제한({max_bytes // (1024 * 1024)}MB)을 초과했습니다.",
        )
    return data


def save_upload_file(file: UploadFile, dest: Path, max_bytes: int) -> None:
    data = _read_limited(file, max_bytes)
    dest.write_bytes(data)


def save_transcript_files(
    job_id: str, transcript_file: UploadFile, pdf_file: UploadFile
) -> tuple[Path, Path]:
    """전사본(.txt/.md/.vtt/.srt) + PDF를 저장한다. (녹음본 대신 전사본 경로)"""
    settings = get_settings()
    job_dir = get_job_dir(job_id)

    transcript_ext = _validate_extension(
        transcript_file.filename or "transcript.txt", ALLOWED_TRANSCRIPT_EXTENSIONS
    )
    pdf_ext = _validate_extension(pdf_file.filename or "lecture.pdf", ALLOWED_PDF_EXTENSIONS)

    transcript_path = job_dir / f"transcript{transcript_ext}"
    pdf_path = job_dir / f"lecture{pdf_ext}"

    save_upload_file(
        transcript_file,
        transcript_path,
        MAX_TRANSCRIPT_SIZE_MB * 1024 * 1024,
    )
    save_upload_file(
        pdf_file,
        pdf_path,
        settings.max_pdf_size_mb * 1024 * 1024,
    )
    _save_original_pdf_name(job_dir, pdf_file.filename or pdf_path.name)
    return transcript_path, pdf_path


def _save_original_pdf_name(job_dir: Path, original_filename: str) -> None:
    """업로드된 강의록 PDF의 원래 파일명을 저장해둔다 (다운로드 파일명에 쓰기 위함)."""
    (job_dir / "pdf_original_name.txt").write_text(original_filename, encoding="utf-8")


def get_original_pdf_stem(job_id: str) -> str:
    """업로드된 강의록 PDF의 원래 파일명(확장자 제외)을 돌려준다. 못 찾으면 'lecture'."""
    name_path = get_job_dir(job_id) / "pdf_original_name.txt"
    if name_path.exists():
        raw = name_path.read_text(encoding="utf-8").strip()
        if raw:
            return Path(raw).stem
    return "lecture"


def save_json(job_id: str, name: str, data: dict | list) -> Path:
    import json

    path = get_job_dir(job_id) / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(job_id: str, name: str) -> dict | list:
    import json

    path = get_job_dir(job_id) / name
    return json.loads(path.read_text(encoding="utf-8"))
