from typing import Literal, Optional

from pydantic import BaseModel, Field


class JobCreateResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "error"]
    progress: int = Field(ge=0, le=100)
    transcribe_progress: int = Field(default=0, ge=0, le=100)
    matching_progress: int = Field(default=0, ge=0, le=100)
    phase: Literal["queued", "transcribe", "matching", "polish", "done"] = "queued"
    message: str = ""
    error: Optional[str] = None


class MatchedScript(BaseModel):
    chunk_id: int
    start: float
    end: float
    start_time: str
    end_time: str
    raw_text: str
    corrected_text: str = ""
    clean_text: str = ""
    score: float
    highlights: list[str] = Field(default_factory=list)
    carried_over: bool = False
    low_confidence: bool = False


class QuizItem(BaseModel):
    question: str
    answer: str = ""


class ConceptNode(BaseModel):
    heading: str = ""
    items: list[str] = Field(default_factory=list)
    children: list["ConceptNode"] = Field(default_factory=list)
    callout_question: Optional[str] = None


class ComparisonTable(BaseModel):
    title: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    slide_ref: Optional[int] = None


class ProfessorHighlight(BaseModel):
    quote: str = ""
    explanation: str = ""
    slide_ref: Optional[int] = None


class LectureDocument(BaseModel):
    title: str = "강의 정리본"
    subtitle: str = "강의 정리본 · 자동 생성 · 1Q"
    key_summary: list[str] = Field(default_factory=list)
    concept_structure: list[ConceptNode] = Field(default_factory=list)
    comparisons: list[ComparisonTable] = Field(default_factory=list)
    professor_highlights: list[ProfessorHighlight] = Field(default_factory=list)
    exam_questions: list[str] = Field(default_factory=list)
    confusing_points: list[str] = Field(default_factory=list)


class PageResult(BaseModel):
    page: int
    page_image_url: str
    page_text: str
    page_caption: str = ""
    page_type: str = "content"
    summary: list[str] = Field(default_factory=list)
    quiz: list[QuizItem] = Field(default_factory=list)
    matched_scripts: list[MatchedScript] = Field(default_factory=list)


class JobResultResponse(BaseModel):
    job_id: str
    status: Literal["done"] = "done"
    warnings: list[str] = Field(default_factory=list)
    pages: list[PageResult] = Field(default_factory=list)
    readability_mode: bool = False
    highlight_mode: bool = False
    summary_mode: bool = False
    note_mode: str = "summary"
    lecture_document: Optional[LectureDocument] = None
    background_color: Optional[str] = None
    text_color: Optional[str] = None
    text_size: Optional[str] = None
