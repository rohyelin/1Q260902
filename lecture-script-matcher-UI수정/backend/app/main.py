from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from app.config import get_settings
from app.job_store import job_store
from app.schemas import JobCreateResponse, JobResultResponse, JobStatusResponse
from app.services.chunking import chunk_segments
from app.services.correction import build_glossary, correct_transcript
from app.services.embedding import embed_texts
from app.services.highlight import find_highlights
from app.services.matching import match_pages_to_chunks
from app.services.pdf_extract import extract_pdf
from app.services.polish import polish_texts
from app.services.full_lecture_note import (
    FULL_LECTURE_DOCUMENT_PROMPT,
    generate_full_lecture_document,
)
from app.services.pdf_export import (
    build_annotated_pdf,
    build_full_lecture_pdf,
    build_script_side_pdf,
    build_slide_summary_script_pdf,
    hex_to_rgb,
    scripts_from_result,
    summaries_from_result,
)
from app.services.quiz import QUIZ_SYSTEM_PROMPT, generate_quiz
from app.services.summarize import SUMMARY_SYSTEM_PROMPT, summarize_page
from app.services.vision_caption import caption_pages, get_page_embedding_texts
from app.services.storage import (
    cleanup_audio,
    get_job_dir,
    get_original_pdf_stem,
    get_pages_dir,
    save_job_files,
    save_json,
    save_transcript_files,
)
from app.services.transcribe import seconds_to_hhmmss, transcribe_audio
from app.services.transcript_ingest import chunk_transcript, extract_transcript_text

app = FastAPI(title="Lecture Script Matcher API", version="0.1.0")

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _set_progress(
    job_id: str,
    *,
    message: str,
    phase: str,
    transcribe: int | None = None,
    matching: int | None = None,
    overall: int | None = None,
) -> None:
    kwargs: dict = {
        "status": "processing",
        "message": message,
        "phase": phase,
    }
    if transcribe is not None:
        kwargs["transcribe_progress"] = transcribe
    if matching is not None:
        kwargs["matching_progress"] = matching
    if overall is not None:
        kwargs["progress"] = overall
    job_store.update(job_id, **kwargs)


def _run_pipeline(job_id: str) -> None:
    record = job_store.get(job_id)
    if not record:
        return

    options = record.options
    warnings: list[str] = []

    try:
        _set_progress(
            job_id,
            message="파일 업로드 완료",
            phase="transcribe",
            transcribe=5,
            matching=0,
            overall=5,
        )

        input_mode = options.get("input_mode", "audio")
        job_dir = get_job_dir(job_id)
        pdf_files = list(job_dir.glob("lecture.*"))
        if not pdf_files:
            raise FileNotFoundError("업로드된 PDF를 찾을 수 없습니다.")
        pdf_path = str(pdf_files[0])

        # PDF를 먼저 추출해 용어집(glossary)을 만들고, 이를 Whisper initial_prompt로
        # 넘겨 도메인 용어 인식률을 높인다.
        _set_progress(
            job_id,
            message="PDF 슬라이드 분석 중",
            phase="transcribe",
            transcribe=5,
            overall=8,
        )
        pages_dir = get_pages_dir(job_id)
        pages, pdf_warnings = extract_pdf(pdf_path, pages_dir)
        warnings.extend(pdf_warnings)
        save_json(job_id, "pages.json", pages)

        glossary = build_glossary(pages)

        settings = get_settings()
        caption_warnings: list[str] = []
        caption_thread = None

        # 저메모리: Whisper와 caption 동시 실행 금지 (Railway OOM 방지)
        # 전사본 모드는 Whisper를 안 쓰므로 병렬 caption을 띄우지 않고 뒤에서 순차 실행한다.
        if input_mode == "audio" and not settings.low_memory:

            def _caption_worker() -> None:
                _, cw = caption_pages(pages)
                caption_warnings.extend(cw)

            caption_thread = threading.Thread(target=_caption_worker, daemon=True)
            caption_thread.start()

        if input_mode == "transcript":
            # 전사본 업로드 경로: 전사(Whisper)·용어교정 단계를 건너뛰고
            # 업로드된 텍스트를 바로 chunk로 만들어 매칭으로 넘어간다.
            _set_progress(
                job_id,
                message="전사본 불러오는 중",
                phase="transcribe",
                transcribe=30,
                overall=20,
            )
            transcript_files = list(job_dir.glob("transcript.*"))
            if not transcript_files:
                raise FileNotFoundError("업로드된 전사본을 찾을 수 없습니다.")
            transcript_text = extract_transcript_text(str(transcript_files[0]))
            chunks = chunk_transcript(transcript_text)
            if not chunks:
                raise ValueError(
                    "전사본에서 읽을 수 있는 텍스트가 없습니다. 파일 내용을 확인해 주세요. "
                    "(스캔한 이미지 PDF라면 글자를 인식하지 못할 수 있어요.)"
                )
            save_json(job_id, "chunks.json", chunks)
            # 전사본은 이미 정리된 텍스트로 보고 교정 단계를 생략한다.
            save_json(job_id, "chunks_corrected.json", chunks)
            _set_progress(
                job_id,
                message="전사본 준비 완료 (전사·교정 단계 건너뜀)",
                phase="transcribe",
                transcribe=100,
                overall=48,
            )
        else:
            _set_progress(
                job_id,
                message="음성 전사 준비 중",
                phase="transcribe",
                transcribe=8,
                overall=10,
            )

            audio_files = list(job_dir.glob("audio.*"))
            if not audio_files:
                raise FileNotFoundError("업로드된 음성 파일을 찾을 수 없습니다.")
            audio_path = str(audio_files[0])

            def on_transcribe_progress(pct: int, msg: str) -> None:
                _set_progress(
                    job_id,
                    message=msg,
                    phase="transcribe",
                    transcribe=pct,
                    overall=10 + int(pct * 0.28),
                )

            segments = transcribe_audio(
                audio_path, on_progress=on_transcribe_progress, glossary=glossary
            )
            save_json(job_id, "segments.json", segments)

            _set_progress(
                job_id,
                message="전사문 청크 분할 중",
                phase="transcribe",
                transcribe=97,
                overall=38,
            )
            chunks = chunk_segments(segments)
            save_json(job_id, "chunks.json", chunks)

            _set_progress(
                job_id,
                message="전사문 용어 교정 중 (fuzzy + LLM)",
                phase="transcribe",
                transcribe=98,
                overall=44,
            )

            def on_correction_progress(pct: int, msg: str) -> None:
                _set_progress(
                    job_id,
                    message=msg,
                    phase="transcribe",
                    transcribe=min(99, 98 + int(pct * 0.01)),
                    overall=44 + int(pct * 0.05),
                )

            chunks, correction_warnings = correct_transcript(
                chunks, pages, on_progress=on_correction_progress
            )
            warnings.extend(correction_warnings)
            save_json(job_id, "chunks_corrected.json", chunks)

            _set_progress(
                job_id,
                message="음성 → 텍스트 변환 완료",
                phase="transcribe",
                transcribe=100,
                overall=48,
            )

        # 전사와 병렬로 돌던 vision caption이 끝나길 기다린다 (보통 이미 완료됨).
        # low_memory면 여기서 순차 실행한다.
        _set_progress(
            job_id,
            message="슬라이드 시각 분석 중",
            phase="matching",
            matching=20,
            overall=55,
        )
        if caption_thread is not None:
            caption_thread.join()
        else:
            _, cw = caption_pages(pages)
            caption_warnings.extend(cw)
        warnings.extend(caption_warnings)
        save_json(job_id, "pages_captioned.json", pages)

        _set_progress(
            job_id,
            message="페이지·스크립트 임베딩 생성 중",
            phase="matching",
            matching=45,
            overall=62,
        )
        page_texts = get_page_embedding_texts(pages)
        chunk_texts = [c["text"] for c in chunks]
        page_embeddings = embed_texts(page_texts)
        chunk_embeddings = embed_texts(chunk_texts)

        _set_progress(
            job_id,
            message="텍스트 → 슬라이드 매칭 중",
            phase="matching",
            matching=75,
            overall=82,
        )
        page_matches, match_warnings = match_pages_to_chunks(
            pages, chunks, page_embeddings, chunk_embeddings
        )
        warnings.extend(match_warnings)

        readability_mode = bool(options.get("readability_mode"))
        highlight_mode = bool(options.get("highlight_mode"))
        summary_mode = bool(options.get("summary_mode"))
        note_mode = options.get("note_mode") or "summary"
        custom_prompt = (options.get("custom_prompt") or "").strip() or None

        if readability_mode:
            _set_progress(
                job_id,
                message="가독성 모드 적용 중",
                phase="polish",
                matching=85,
                overall=88,
            )

        n_pages = len(pages)

        # 1) 페이지별 matched_scripts를 먼저 구성 (가벼운 로컬 작업)
        page_scripts: list[list[dict]] = []
        for i, page in enumerate(pages):
            matched_scripts = []
            for ch in page_matches[i]:
                raw_text = ch.get("raw_text", ch["text"])
                display_text = ch["text"]
                clean_text = ""  # 가독성 모드면 루프 뒤 배치에서 채움
                highlights = find_highlights(clean_text or display_text) if highlight_mode else []
                matched_scripts.append(
                    {
                        "chunk_id": ch["chunk_id"],
                        "start": ch["start"],
                        "end": ch["end"],
                        "start_time": ch["start_time"],
                        "end_time": ch["end_time"],
                        "raw_text": raw_text,
                        "corrected_text": display_text,
                        "clean_text": clean_text,
                        "score": round(float(ch.get("score", 0)), 4),
                        "highlights": highlights,
                        "carried_over": bool(ch.get("carried_over", False)),
                        "low_confidence": bool(ch.get("low_confidence", False)),
                    }
                )
            page_scripts.append(matched_scripts)

        # 1-b) 가독성 모드: 매칭된 스크립트 전체를 한 번의 호출로 문어체 다듬기 (저가 모델, 배치)
        if readability_mode:
            flat = [s for scripts in page_scripts for s in scripts]
            if flat:
                polished = polish_texts([s["corrected_text"] for s in flat])
                for s, clean in zip(flat, polished):
                    s["clean_text"] = clean
                    if highlight_mode:
                        s["highlights"] = find_highlights(clean or s["corrected_text"])

        # 2) 요약/퀴즈/전체정리본 생성
        summaries: list[list[str]] = [[] for _ in range(n_pages)]
        quizzes: list[list[dict]] = [[] for _ in range(n_pages)]
        lecture_document: dict[str, Any] = {}

        if summary_mode:
            from app.services.parallel import parallel_map

            if note_mode == "full_note":
                _set_progress(
                    job_id,
                    message="전체 강의 정리본 생성 중",
                    phase="polish",
                    matching=88,
                    overall=90,
                )
                lecture_document = generate_full_lecture_document(
                    pages, page_scripts, system_prompt=custom_prompt
                )
            else:
                phase_labels = {"quiz": "퀴즈 생성 중"}
                phase_label = phase_labels.get(note_mode, "핵심 요약 생성 중")

                def _note(i: int, page: dict):
                    if note_mode == "quiz":
                        if not page_scripts[i]:
                            return []
                        return generate_quiz(
                            page.get("text", ""),
                            page.get("caption", ""),
                            page_scripts[i],
                            system_prompt=custom_prompt,
                        )
                    if not page_scripts[i]:
                        return []
                    return summarize_page(
                        page.get("text", ""),
                        page.get("caption", ""),
                        page_scripts[i],
                        system_prompt=custom_prompt,
                    )

                def _note_progress(done: int, total: int) -> None:
                    pct = int(done / max(total, 1) * 100)
                    _set_progress(
                        job_id,
                        message=f"{phase_label} ({done}/{total}페이지)",
                        phase="polish",
                        matching=85 + int(pct * 0.14),
                        overall=88 + int(pct * 0.10),
                    )

                results = parallel_map(_note, list(pages), on_progress=_note_progress)
                if note_mode == "quiz":
                    quizzes = results
                else:
                    summaries = results

        result_pages = []
        for i, page in enumerate(pages):
            result_pages.append(
                {
                    "page": page["page"],
                    "page_image_url": f"/api/jobs/{job_id}/pages/{page['page']}.png",
                    "page_text": page["text"],
                    "page_caption": page.get("caption", ""),
                    "page_type": page.get("page_type", "content"),
                    "summary": summaries[i],
                    "quiz": quizzes[i],
                    "matched_scripts": page_scripts[i],
                }
            )

        _set_progress(
            job_id,
            message="텍스트 → 슬라이드 매칭 완료",
            phase="matching",
            matching=100,
            overall=98,
        )

        result = {
            "job_id": job_id,
            "status": "done",
            "warnings": warnings,
            "pages": result_pages,
            "readability_mode": readability_mode,
            "highlight_mode": highlight_mode,
            "summary_mode": summary_mode,
            "note_mode": note_mode,
            "lecture_document": lecture_document if lecture_document.get("title") else None,
            "background_color": options.get("background_color"),
            "text_color": options.get("text_color"),
            "text_size": options.get("text_size"),
        }

        save_json(job_id, "result.json", result)
        cleanup_audio(job_id)

        job_store.update(
            job_id,
            status="done",
            progress=100,
            transcribe_progress=100,
            matching_progress=100,
            phase="done",
            message="완료",
            result=result,
            warnings=warnings,
        )
    except Exception as exc:
        job_store.update(
            job_id,
            status="error",
            progress=0,
            message="처리 중 오류가 발생했습니다.",
            error=str(exc),
        )
        traceback.print_exc()


# 여러 강의를 한꺼번에 올려도 컴퓨터가 죽지 않게, 한 번에 하나씩만 처리하고
# 나머지는 대기열에서 순서대로 처리한다. (안전 우선; 속도가 필요하면 max_workers를 2로)
_pipeline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


def _start_pipeline(job_id: str) -> None:
    # 제출만 하고 바로 반환. 처리 슬롯이 차 있으면 job은 "queued" 상태로 대기한다.
    _pipeline_executor.submit(_run_pipeline, job_id)


def generate_notes(
    pages: list[dict],
    page_scripts: list[list[dict]],
    *,
    note_mode: str = "summary",
    custom_prompt: str | None = None,
) -> tuple[list[list[str]], list[list[dict]], dict]:
    """저장된 pages + page_scripts로 정리본만 생성한다 (전사·매칭 재실행 없음).
    _run_pipeline과 rerun-notes 엔드포인트가 공유하는 2단계 엔진."""
    n_pages = len(pages)
    summaries: list[list[str]] = [[] for _ in range(n_pages)]
    quizzes: list[list[dict]] = [[] for _ in range(n_pages)]
    lecture_document: dict = {}

    if note_mode == "full_note":
        lecture_document = generate_full_lecture_document(
            pages, page_scripts, system_prompt=custom_prompt
        )
        return summaries, quizzes, lecture_document

    from app.services.parallel import parallel_map

    def _note(i: int, page: dict):
        if not page_scripts[i]:
            return []
        if note_mode == "quiz":
            return generate_quiz(
                page.get("text", ""),
                page.get("caption", ""),
                page_scripts[i],
                system_prompt=custom_prompt,
            )
        return summarize_page(
            page.get("text", ""),
            page.get("caption", ""),
            page_scripts[i],
            system_prompt=custom_prompt,
        )

    results = parallel_map(_note, list(pages))
    if note_mode == "quiz":
        quizzes = results
    else:
        summaries = results
    return summaries, quizzes, lecture_document


@app.post("/api/jobs", response_model=JobCreateResponse)
async def create_job(
    background_tasks: BackgroundTasks,
    pdf_file: UploadFile = File(...),
    audio_file: UploadFile | None = File(None),
    transcript_file: UploadFile | None = File(None),
    readability_mode: bool = Form(False),
    highlight_mode: bool = Form(False),
    summary_mode: bool = Form(True),
    note_mode: str = Form("summary"),
    custom_prompt: str | None = Form(None),
    background_color: str | None = Form(None),
    text_color: str | None = Form(None),
    text_size: str | None = Form(None),
):
    # 녹음본(audio) 또는 전사본(transcript) 중 하나를 받는다.
    has_audio = audio_file is not None and (audio_file.filename or "").strip() != ""
    has_transcript = (
        transcript_file is not None and (transcript_file.filename or "").strip() != ""
    )
    if has_audio and has_transcript:
        raise HTTPException(
            status_code=400, detail="녹음본과 전사본 중 하나만 올려주세요."
        )
    if not has_audio and not has_transcript:
        raise HTTPException(
            status_code=400, detail="녹음본 또는 전사본을 올려주세요."
        )

    input_mode = "transcript" if has_transcript else "audio"
    # 가독성(문어체 변환)은 입력 방식과 무관하게 사용자 선택(토글)을 그대로 따른다.
    effective_readability = readability_mode

    job_id = str(uuid.uuid4())
    options = {
        "input_mode": input_mode,
        "readability_mode": effective_readability,
        "highlight_mode": highlight_mode,
        "summary_mode": summary_mode,
        "note_mode": note_mode if note_mode in ("summary", "quiz", "full_note") else "summary",
        "custom_prompt": custom_prompt,
        "background_color": background_color,
        "text_color": text_color,
        "text_size": text_size,
    }
    job_store.create(job_id, options)
    if input_mode == "transcript":
        save_transcript_files(job_id, transcript_file, pdf_file)
    else:
        save_job_files(job_id, audio_file, pdf_file)
    _start_pipeline(job_id)
    return JobCreateResponse(job_id=job_id)


@app.get("/api/prompts")
def get_default_prompts():
    """업로드 페이지에서 편집할 수 있는 기본 시스템 프롬프트."""
    return {
        "summary": SUMMARY_SYSTEM_PROMPT,
        "quiz": QUIZ_SYSTEM_PROMPT,
        "full_note": FULL_LECTURE_DOCUMENT_PROMPT,
    }


@app.post("/api/jobs/{job_id}/rerun-notes", response_model=JobResultResponse)
def rerun_notes(
    job_id: str,
    note_mode: str = Form("summary"),
    custom_prompt: str | None = Form(None),
):
    """저장된 교정 스크립트를 재사용해 정리본만 다시 생성한다 (전사·매칭 없음, 몇 초)."""
    result = _load_done_result(job_id)

    note_mode = note_mode if note_mode in ("summary", "quiz", "full_note") else "summary"
    custom_prompt = (custom_prompt or "").strip() or None

    pages = [
        {
            "page": p["page"],
            "text": p.get("page_text", ""),
            "caption": p.get("page_caption", ""),
            "page_type": p.get("page_type", "content"),
        }
        for p in result["pages"]
    ]
    page_scripts = [p.get("matched_scripts", []) for p in result["pages"]]

    summaries, quizzes, lecture_document = generate_notes(
        pages, page_scripts, note_mode=note_mode, custom_prompt=custom_prompt
    )

    # 모드별로 한 종류만 생성되므로, 이번에 안 만든 항목은 기존 값을 유지한다.
    # (요약 → 퀴즈 → 전체정리본 순서로 여러 번 돌리면 셋을 함께 가질 수 있다)
    result["pages"] = [
        {
            **p,
            "summary": summaries[i] or p.get("summary") or [],
            "quiz": quizzes[i] or p.get("quiz") or [],
        }
        for i, p in enumerate(result["pages"])
    ]
    result["note_mode"] = note_mode
    result["summary_mode"] = True
    result["lecture_document"] = (
        lecture_document
        if lecture_document.get("title")
        else result.get("lecture_document")
    )

    save_json(job_id, "result.json", result)
    record = job_store.get(job_id)
    if record:
        job_store.update(job_id, result=result)

    return JobResultResponse(**result)


@app.get("/api/jobs/{job_id}/status", response_model=JobStatusResponse)
def get_job_status(job_id: str):
    record = job_store.get(job_id)
    if not record:
        # 메모리에 없어도 디스크에 완료 결과가 있으면 done으로 응답 (서버 재시작 후에도 조회 가능)
        if (get_job_dir(job_id) / "result.json").exists():
            return JobStatusResponse(
                job_id=job_id,
                status="done",
                progress=100,
                transcribe_progress=100,
                matching_progress=100,
                phase="done",
                message="완료",
                error=None,
            )
        raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다.")
    return JobStatusResponse(
        job_id=job_id,
        status=record.status,  # type: ignore[arg-type]
        progress=record.progress,
        transcribe_progress=record.transcribe_progress,
        matching_progress=record.matching_progress,
        phase=record.phase,  # type: ignore[arg-type]
        message=record.message,
        error=record.error,
    )


@app.get("/api/jobs/{job_id}/result", response_model=JobResultResponse)
def get_job_result(job_id: str):
    record = job_store.get(job_id)
    if record and record.status == "done" and record.result:
        return JobResultResponse(**record.result)
    if record and record.status != "done":
        raise HTTPException(status_code=400, detail="아직 처리가 완료되지 않았습니다.")
    # 메모리에 없으면 디스크 result.json에서 (서버 재시작 후에도 조회 가능)
    result = _load_done_result(job_id)
    return JobResultResponse(**result)


@app.get("/api/jobs/{job_id}/pages/{page_num}.png")
def get_page_image(job_id: str, page_num: int):
    pages_dir = get_pages_dir(job_id)
    image_path = pages_dir / f"page_{page_num:03d}.png"
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="페이지 이미지를 찾을 수 없습니다.")
    return FileResponse(str(image_path), media_type="image/png")


@app.get("/api/jobs/{job_id}/download.md")
def download_markdown(job_id: str):
    record = job_store.get(job_id)
    if not record or record.status != "done" or not record.result:
        raise HTTPException(status_code=400, detail="결과를 사용할 수 없습니다.")

    lines = [f"# Lecture Script Match — Job {job_id}\n"]
    doc = record.result.get("lecture_document") or {}
    if doc and doc.get("title"):
        lines.append(f"\n# {doc['title']}\n")
        lines.append(f"*{doc.get('subtitle', '')}*\n")
        if doc.get("key_summary"):
            lines.append("\n## 핵심 요약\n")
            for p in doc["key_summary"]:
                lines.append(f"- {p}")
        if doc.get("exam_questions"):
            lines.append("\n## 시험에서 이렇게 나온다\n")
            for q in doc["exam_questions"]:
                lines.append(f"- {q}")
        lines.append("\n---\n")

    for page in record.result["pages"]:
        lines.append(f"\n## Page {page['page']}\n")
        summary = page.get("summary") or []
        if summary:
            lines.append("### 핵심 정리\n")
            for point in summary:
                lines.append(f"- {point}")
            lines.append("")
        quiz = page.get("quiz") or []
        if quiz:
            lines.append("### 복습 퀴즈\n")
            for qi, item in enumerate(quiz, start=1):
                lines.append(f"**Q{qi}. {item.get('question', '')}**")
                if item.get("answer"):
                    lines.append(f"<details><summary>정답 보기</summary>{item['answer']}</details>")
                lines.append("")
        if page["matched_scripts"]:
            lines.append("### 교수님 스크립트\n")
        for script in page["matched_scripts"]:
            text = script.get("clean_text") or script.get("corrected_text") or script["raw_text"]
            lines.append(
                f"**[{script['start_time']} ~ {script['end_time']}]**\n\n{text}\n"
            )

    content = "\n".join(lines)
    md_path = get_job_dir(job_id) / "export.md"
    md_path.write_text(content, encoding="utf-8")
    return FileResponse(
        str(md_path),
        media_type="text/markdown",
        filename=f"lecture_script_{job_id[:8]}.md",
    )


@app.get("/api/jobs/{job_id}/download.json")
def download_json(job_id: str):
    record = job_store.get(job_id)
    if not record or record.status != "done" or not record.result:
        raise HTTPException(status_code=400, detail="결과를 사용할 수 없습니다.")
    json_path = get_job_dir(job_id) / "result.json"
    return FileResponse(
        str(json_path),
        media_type="application/json",
        filename=f"lecture_script_{job_id[:8]}.json",
    )


def _load_done_result(job_id: str) -> dict:
    """메모리 job store 또는 디스크 result.json에서 완료된 결과를 불러온다."""
    record = job_store.get(job_id)
    if record and record.status == "done" and record.result:
        return record.result
    json_path = get_job_dir(job_id) / "result.json"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="Job을 찾을 수 없습니다.")


@app.get("/api/jobs/{job_id}/download.pdf")
def download_pdf(
    job_id: str,
    note_bg: str | None = None,
    note_text: str | None = None,
    layout: str | None = None,
    readability: bool = True,
):
    result = _load_done_result(job_id)

    job_dir = get_job_dir(job_id)

    # 강의록(슬라이드) 왼쪽 + 스크립트 오른쪽 나란히 PDF
    if layout == "script_side":
        pdf_files = list(job_dir.glob("lecture.*"))
        if not pdf_files:
            raise HTTPException(status_code=404, detail="원본 PDF를 찾을 수 없습니다.")
        page_scripts = scripts_from_result(result["pages"])
        out_path = job_dir / (
            "lecture_with_script_readable.pdf"
            if readability
            else "lecture_with_script_raw.pdf"
        )
        try:
            _, export_warnings = build_script_side_pdf(
                str(pdf_files[0]),
                page_scripts,
                str(out_path),
                note_bg=hex_to_rgb(note_bg),
                note_text=hex_to_rgb(note_text),
                use_readability=readability,
            )
            record = job_store.get(job_id)
            if record:
                for w in export_warnings:
                    record.warnings.append(w)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {exc}") from exc
        if not out_path.exists():
            raise HTTPException(status_code=500, detail="PDF 파일 생성에 실패했습니다.")
        return FileResponse(
            str(out_path),
            media_type="application/pdf",
            filename=f"{get_original_pdf_stem(job_id)}_스크립트.pdf",
        )

    # 슬라이드 + 요약(오른쪽) + 스크립트(아래) 한 장에
    if layout == "summary_script":
        pdf_files = list(job_dir.glob("lecture.*"))
        if not pdf_files:
            raise HTTPException(status_code=404, detail="원본 PDF를 찾을 수 없습니다.")
        page_summaries = summaries_from_result(
            result["pages"], note_mode=result.get("note_mode", "summary")
        )
        page_scripts = scripts_from_result(result["pages"])
        suffix = "readable" if readability else "raw"
        out_path = job_dir / f"lecture_summary_script_{suffix}.pdf"
        try:
            _, export_warnings = build_slide_summary_script_pdf(
                str(pdf_files[0]),
                page_summaries,
                page_scripts,
                str(out_path),
                note_bg=hex_to_rgb(note_bg),
                note_text=hex_to_rgb(note_text),
                use_readability=readability,
            )
            record = job_store.get(job_id)
            if record:
                for w in export_warnings:
                    record.warnings.append(w)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {exc}") from exc
        if not out_path.exists():
            raise HTTPException(status_code=500, detail="PDF 파일 생성에 실패했습니다.")
        label = "스크립트+핵심정리 (문어체)" if readability else "스크립트+핵심정리 (원문)"
        return FileResponse(
            str(out_path),
            media_type="application/pdf",
            filename=f"{get_original_pdf_stem(job_id)}_{label}.pdf",
        )

    result_note_mode = result.get("note_mode", "summary")
    out_path = job_dir / (
        "full_lecture_note.pdf" if result_note_mode == "full_note" else "lecture_with_notes.pdf"
    )

    try:
        if result_note_mode == "full_note":
            doc = result.get("lecture_document") or {}
            if not doc.get("title"):
                raise HTTPException(
                    status_code=400,
                    detail="전체 정리본이 없습니다. 업로드 시 '전체 정리본' 모드로 다시 처리해 주세요.",
                )
            _, export_warnings = build_full_lecture_pdf(
                doc,
                str(out_path),
                note_bg=hex_to_rgb(note_bg),
                note_text=hex_to_rgb(note_text),
            )
        else:
            pdf_files = list(job_dir.glob("lecture.*"))
            if not pdf_files:
                raise HTTPException(status_code=404, detail="원본 PDF를 찾을 수 없습니다.")
            page_summaries = summaries_from_result(result["pages"], note_mode=result_note_mode)
            if not page_summaries:
                raise HTTPException(
                    status_code=400,
                    detail="핵심 정리/퀴즈가 없습니다. 업로드 시 '핵심 요약' 옵션을 켜고 다시 처리해 주세요.",
                )
            _, export_warnings = build_annotated_pdf(
                str(pdf_files[0]),
                page_summaries,
                str(out_path),
                note_bg=hex_to_rgb(note_bg),
                note_text=hex_to_rgb(note_text),
            )

        record = job_store.get(job_id)
        if record:
            for w in export_warnings:
                record.warnings.append(w)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {exc}") from exc

    if not out_path.exists():
        raise HTTPException(status_code=500, detail="PDF 파일 생성에 실패했습니다.")

    stem = get_original_pdf_stem(job_id)
    filename = (
        f"{stem}_전체정리본.pdf"
        if result_note_mode == "full_note"
        else f"{stem}_핵심정리.pdf"
    )
    return FileResponse(
        str(out_path),
        media_type="application/pdf",
        filename=filename,
    )


@app.get("/")
def root():
    return {
        "service": "Lecture Script Matcher API",
        "status": "ok",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
