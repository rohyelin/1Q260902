export interface JobCreateResponse {
  job_id: string;
  status: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: "queued" | "processing" | "done" | "error";
  progress: number;
  transcribe_progress: number;
  matching_progress: number;
  phase: "queued" | "transcribe" | "matching" | "polish" | "done";
  message: string;
  error: string | null;
}

export interface MatchedScript {
  chunk_id: number;
  start: number;
  end: number;
  start_time: string;
  end_time: string;
  raw_text: string;
  corrected_text?: string;
  clean_text: string;
  score: number;
  highlights: string[];
  carried_over?: boolean;
  low_confidence?: boolean;
}

export interface QuizItem {
  question: string;
  answer: string;
}

export interface ConceptNode {
  heading: string;
  items: string[];
  children?: ConceptNode[];
  callout_question?: string | null;
}

export interface ComparisonTable {
  title: string;
  columns: string[];
  rows: string[][];
  slide_ref?: number | null;
}

export interface ProfessorHighlight {
  quote: string;
  explanation: string;
  slide_ref?: number | null;
}

export interface LectureDocument {
  title: string;
  subtitle: string;
  key_summary: string[];
  concept_structure: ConceptNode[];
  comparisons: ComparisonTable[];
  professor_highlights: ProfessorHighlight[];
  exam_questions: string[];
  confusing_points: string[];
}

export interface PageResult {
  page: number;
  page_image_url: string;
  page_text: string;
  page_caption?: string;
  page_type?: string;
  summary?: string[];
  quiz?: QuizItem[];
  matched_scripts: MatchedScript[];
}

export interface JobResultResponse {
  job_id: string;
  status: "done";
  warnings: string[];
  pages: PageResult[];
  readability_mode?: boolean;
  highlight_mode?: boolean;
  summary_mode?: boolean;
  note_mode?: "summary" | "quiz" | "full_note";
  lecture_document?: LectureDocument | null;
  background_color?: string | null;
  text_color?: string | null;
  text_size?: string | null;
}

export interface UploadOptions {
  readability_mode: boolean;
  highlight_mode: boolean;
  summary_mode: boolean;
  note_mode?: "summary" | "quiz" | "full_note";
  custom_prompt?: string;
  background_color?: string;
  text_color?: string;
  text_size?: string;
}

export interface DefaultPrompts {
  summary: string;
  quiz: string;
  full_note: string;
}

/** 로컬: 빈 문자열(Next rewrite). 프로덕션: Railway 등 백엔드 URL */
const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

/** 상대 /api 경로 또는 절대 URL을 실제 요청 URL로 변환 */
export function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${normalized}` : normalized;
}

export async function getDefaultPrompts(): Promise<DefaultPrompts> {
  const res = await fetch(apiUrl("/api/prompts"));
  if (!res.ok) throw new Error("프롬프트 조회에 실패했습니다.");
  return res.json();
}

/** 전사본(텍스트) + PDF로 작업 생성. 전사·교정·가독성 단계는 백엔드에서 건너뛴다. */
export async function createTranscriptJob(
  transcriptFile: File,
  pdfFile: File,
  options: UploadOptions
): Promise<JobCreateResponse> {
  const form = new FormData();
  form.append("transcript_file", transcriptFile);
  form.append("pdf_file", pdfFile);
  form.append("readability_mode", String(options.readability_mode));
  form.append("highlight_mode", String(options.highlight_mode));
  form.append("summary_mode", String(options.summary_mode));
  if (options.note_mode) form.append("note_mode", options.note_mode);
  if (options.custom_prompt) form.append("custom_prompt", options.custom_prompt);
  if (options.background_color) form.append("background_color", options.background_color);
  if (options.text_color) form.append("text_color", options.text_color);
  if (options.text_size) form.append("text_size", options.text_size);

  const res = await fetch(apiUrl("/api/jobs"), {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "업로드에 실패했습니다.");
  }
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(apiUrl(`/api/jobs/${jobId}/status`));
  if (!res.ok) throw new Error("상태 조회에 실패했습니다.");
  return res.json();
}

export async function getJobResult(jobId: string): Promise<JobResultResponse> {
  const res = await fetch(apiUrl(`/api/jobs/${jobId}/result`));
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "결과 조회에 실패했습니다.");
  }
  return res.json();
}

/** 저장된 교정 스크립트를 재사용해 정리본만 다시 생성한다 (전사·매칭 없음, 몇 초). */
export async function rerunNotes(
  jobId: string,
  options: { note_mode?: "summary" | "quiz" | "full_note"; custom_prompt?: string }
): Promise<JobResultResponse> {
  const form = new FormData();
  if (options.note_mode) form.append("note_mode", options.note_mode);
  if (options.custom_prompt) form.append("custom_prompt", options.custom_prompt);

  const res = await fetch(apiUrl(`/api/jobs/${jobId}/rerun-notes`), {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "정리본 재생성에 실패했습니다.");
  }
  return res.json();
}

export function getDownloadUrl(jobId: string, format: "md" | "json" | "pdf"): string {
  return apiUrl(`/api/jobs/${jobId}/download.${format}`);
}

export function getPageImageUrl(jobId: string, page: number): string {
  return apiUrl(`/api/jobs/${jobId}/pages/${page}.png`);
}
