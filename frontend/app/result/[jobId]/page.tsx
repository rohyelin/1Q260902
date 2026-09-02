"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import PdfPreview from "@/components/PdfPreview";
import ScriptPanel from "@/components/ScriptPanel";
import SummaryPanel from "@/components/SummaryPanel";
import QuizPanel from "@/components/QuizPanel";
import FullLectureNoteView from "@/components/FullLectureNoteView";
import PrintView from "@/components/PrintView";
import ProgressBar from "@/components/ProgressBar";
import CustomizePanel, { type NoteMode } from "@/components/CustomizePanel";
import {
  THEME_PRESETS,
  type TextSizeId,
  type ThemeId,
} from "@/lib/themes";
import {
  getDownloadUrl,
  getJobResult,
  getJobStatus,
  getPageImageUrl,
  rerunNotes,
  apiUrl,
  type JobResultResponse,
} from "@/lib/api";

const NOTE_BG_OPTIONS = [
  { label: "연파랑", value: "#f5f8ff" },
  { label: "연노랑", value: "#fefce8" },
  { label: "연녹색", value: "#f0fdf4" },
  { label: "연회색", value: "#f8fafc" },
  { label: "흰색", value: "#ffffff" },
];

const NOTE_TEXT_OPTIONS = [
  { label: "검정", value: "#1a1f2e" },
  { label: "남색", value: "#1e3a8a" },
  { label: "진녹색", value: "#14532d" },
  { label: "갈색", value: "#713f12" },
];

export default function ResultPage({ params }: { params: { jobId: string } }) {
  const { jobId } = params;
  const [result, setResult] = useState<JobResultResponse | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [showScript, setShowScript] = useState(true);
  // 기본값은 테마 첫 번째(Classic note)와 맞춰 둔다
  const [noteBg, setNoteBg] = useState(THEME_PRESETS[0].background);
  const [noteText, setNoteText] = useState(THEME_PRESETS[0].text);
  const [viewMode, setViewMode] = useState<"document" | "slides">("document");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState("");
  const [transcribeProgress, setTranscribeProgress] = useState(0);
  const [matchingProgress, setMatchingProgress] = useState(0);
  const [phase, setPhase] = useState<"queued" | "transcribe" | "matching" | "polish" | "done">("queued");
  const [noteMode, setNoteMode] = useState<NoteMode>("summary");
  const [customPrompt, setCustomPrompt] = useState("");
  const [themeId, setThemeId] = useState<ThemeId>("classic");
  const [textSize, setTextSize] = useState<TextSizeId>("base");
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);
  // 인쇄물 표지에 들어갈 값 (결과 데이터에 없는 정보라 직접 입력받는다)
  const [coverSession, setCoverSession] = useState("");
  const [coverTitle, setCoverTitle] = useState("");
  const [coverProfessor, setCoverProfessor] = useState("");
  // 다운로드 PDF에 문어체로 다듬은 스크립트를 넣을지, 전사본 원문을 넣을지
  const [scriptRaw, setScriptRaw] = useState(false);
  const noteModeInitRef = useRef(false);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenError(null);
    try {
      const updated = await rerunNotes(jobId, {
        note_mode: noteMode,
        custom_prompt: customPrompt || undefined,
      });
      setResult(updated);
      if (updated.note_mode === "full_note" && updated.lecture_document?.title) {
        setViewMode("document");
      } else {
        setViewMode("slides");
      }
      setCustomizeOpen(false);
    } catch (e) {
      setRegenError(e instanceof Error ? e.message : "정리본 재생성에 실패했습니다.");
    } finally {
      setRegenerating(false);
    }
  };

  const loadResult = useCallback(async () => {
    try {
      const status = await getJobStatus(jobId);
      if (status.status === "error") {
        setError(status.error || "처리 실패");
        setLoading(false);
        return;
      }
      if (status.status !== "done") {
        setTranscribeProgress(status.transcribe_progress);
        setMatchingProgress(status.matching_progress);
        setPhase(status.phase);
        setProgressMessage(status.message);
        return false;
      }
      const data = await getJobResult(jobId);
      setResult(data);
      if (data.note_mode !== "full_note" || !data.lecture_document) {
        setViewMode("slides");
      }
      setLoading(false);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "결과 로드 실패");
      setLoading(false);
      return true;
    }
  }, [jobId]);

  const loadMock = useCallback(async () => {
    const res = await fetch("/sample_result.json");
    const data = await res.json();
    // 데모 JSON의 localhost 이미지 URL은 배포 환경에서 동작하지 않음
    data.pages = (data.pages || []).map((p: { page_image_url?: string }) => ({
      ...p,
      page_image_url: "",
    }));
    setResult(data);
    setLoading(false);
    setError(null);
  }, []);

  useEffect(() => {
    if (jobId === "demo" || jobId === "sample") {
      loadMock();
      return;
    }
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      const done = await loadResult();
      if (!done && !cancelled) {
        setTimeout(poll, 500);
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [loadResult, jobId, loadMock]);

  useEffect(() => {
    if (result && !noteModeInitRef.current) {
      noteModeInitRef.current = true;
      if (result.note_mode) setNoteMode(result.note_mode);
    }
  }, [result]);

  if (loading && !result) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="w-full max-w-lg px-6">
          <ProgressBar
            message={progressMessage || "결과 로딩 중..."}
            transcribeProgress={transcribeProgress}
            matchingProgress={matchingProgress}
            phase={phase}
          />
        </div>
      </main>
    );
  }

  if (error && !result) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-4">
        <p className="text-red-600">{error}</p>
        <button
          onClick={loadMock}
          className="text-brand-600 underline text-sm"
        >
          Mock 결과 보기
        </button>
        <Link href="/" className="text-slate-500 text-sm">
          ← 돌아가기
        </Link>
      </main>
    );
  }

  if (!result || result.pages.length === 0) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-slate-500">결과가 없습니다.</p>
      </main>
    );
  }

  const currentPage = result.pages[pageIndex];
  const totalPages = result.pages.length;
  const hasLectureDoc =
    result.note_mode === "full_note" && !!result.lecture_document?.title;
  const resolveImageUrl = (pageNum: number) => {
    const page = result.pages.find((p) => p.page === pageNum);
    const raw = page?.page_image_url || "";
    if (!raw && jobId !== "demo" && jobId !== "sample") {
      return apiUrl(getPageImageUrl(jobId, pageNum));
    }
    if (!raw) return "";
    return apiUrl(
      raw.startsWith("http") || raw.startsWith("/api")
        ? raw
        : getPageImageUrl(jobId, pageNum)
    );
  };
  const imageUrl = resolveImageUrl(currentPage.page);

  return (
    <main className="min-h-screen bg-slate-100">
      <header className="no-print bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between">
        <div>
          <Link href="/" className="text-sm text-slate-400 hover:text-slate-600">
            ← 새 업로드
          </Link>
          <h1 className="text-lg font-semibold text-slate-800 mt-1">
            강의 스크립트 매칭 결과
          </h1>
        </div>
        <div className="flex gap-2 items-center flex-wrap justify-end">
          <button
            onClick={() => window.print()}
            className="px-4 py-2 text-sm bg-slate-900 text-white rounded-lg hover:bg-slate-700 font-medium"
          >
            인쇄 · PDF로 저장
          </button>
          {jobId !== "demo" && jobId !== "sample" && (
            <>
              {result.summary_mode && result.note_mode === "full_note" && (
                <a
                  href={`${getDownloadUrl(jobId, "pdf")}?note_bg=${encodeURIComponent(
                    noteBg
                  )}&note_text=${encodeURIComponent(noteText)}`}
                  className="px-4 py-2 text-sm bg-brand-600 text-white rounded-lg hover:bg-brand-700 font-medium border border-black"
                >
                  PDF (전체 정리본)
                </a>
              )}
              {result.summary_mode && result.note_mode !== "full_note" && (
                <div className="flex items-center gap-2">
                  <a
                    href={`${getDownloadUrl(jobId, "pdf")}?note_bg=${encodeURIComponent(
                      noteBg
                    )}&note_text=${encodeURIComponent(noteText)}`}
                    className="px-4 py-2 text-sm bg-brand-600 text-white rounded-lg hover:bg-brand-700 font-medium border border-black"
                  >
                    PDF (핵심정리 포함)
                  </a>
                </div>
              )}
              {result.readability_mode && (
                <label className="flex items-center gap-1.5 text-xs text-slate-500">
                  스크립트
                  <select
                    value={scriptRaw ? "raw" : "polished"}
                    onChange={(e) => setScriptRaw(e.target.value === "raw")}
                    className="text-xs border border-slate-200 rounded-md px-1.5 py-1 bg-white"
                    title="아래 PDF에 들어갈 스크립트를 문어체로 다듬을지 고릅니다"
                  >
                    <option value="polished">문어체</option>
                    <option value="raw">원문</option>
                  </select>
                </label>
              )}
              <a
                href={`${getDownloadUrl(jobId, "pdf")}?layout=script_side&readability=${
                  scriptRaw ? "false" : "true"
                }&note_bg=${encodeURIComponent(
                  noteBg
                )}&note_text=${encodeURIComponent(noteText)}`}
                className="px-4 py-2 text-sm bg-white border border-slate-300 rounded-lg hover:bg-slate-50 font-medium text-slate-700"
              >
                PDF (강의록+스크립트)
              </a>
              <a
                href={`${getDownloadUrl(jobId, "pdf")}?layout=summary_script&readability=${
                  scriptRaw ? "false" : "true"
                }&note_bg=${encodeURIComponent(
                  noteBg
                )}&note_text=${encodeURIComponent(noteText)}`}
                className="px-4 py-2 text-sm bg-white border border-slate-300 rounded-lg hover:bg-slate-50 font-medium text-slate-700"
              >
                PDF (요약+스크립트)
              </a>
              <a
                href={getDownloadUrl(jobId, "md")}
                className="px-4 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50"
              >
                Markdown
              </a>
              <a
                href={getDownloadUrl(jobId, "json")}
                className="px-4 py-2 text-sm bg-white border border-slate-200 rounded-lg hover:bg-slate-50"
              >
                JSON
              </a>
            </>
          )}
        </div>
      </header>

      {result.warnings.length > 0 && (
        <div className="no-print mx-6 mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
          {result.warnings.map((w, i) => (
            <p key={i}>⚠ {w}</p>
          ))}
        </div>
      )}

      <div className="no-print mx-auto px-6 py-6 max-w-[1600px]">
        {jobId !== "demo" && jobId !== "sample" && (
          <div className="mb-5">
            <button
              onClick={() => setCustomizeOpen((v) => !v)}
              className="px-4 py-2 text-sm rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium"
            >
              {customizeOpen ? "커스터마이징 닫기" : "✏️ 정리본 다시 만들기 (커스터마이징)"}
            </button>
            {customizeOpen && (
              <div className="mt-3 flex flex-col items-center gap-3">
                <CustomizePanel
                  noteMode={noteMode}
                  customPrompt={customPrompt}
                  themeId={themeId}
                  textSize={textSize}
                  onNoteModeChange={setNoteMode}
                  onCustomPromptChange={setCustomPrompt}
                  onThemeChange={setThemeId}
                  onTextSizeChange={setTextSize}
                />
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleRegenerate}
                    disabled={regenerating}
                    className="px-6 py-2 text-sm rounded-lg bg-brand-600 text-white font-medium hover:bg-brand-700 disabled:opacity-50 border border-black"
                  >
                    {regenerating ? "생성 중… (몇 초)" : "이 설정으로 정리본 다시 만들기"}
                  </button>
                  {regenError && <span className="text-sm text-red-600">{regenError}</span>}
                </div>
              </div>
            )}
          </div>
        )}
        {/* 인쇄물 표지에 찍힐 정보 — 결과 데이터에 없어서 직접 입력받는다 */}
        <div className="mb-5 rounded-xl border border-slate-200 bg-white px-5 py-4">
          <p className="mb-3 font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            인쇄 설정
          </p>
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              차시
              <input
                value={coverSession}
                onChange={(e) => setCoverSession(e.target.value)}
                placeholder="3주차 2차시"
                className="w-40 rounded-md border border-slate-200 px-2.5 py-1.5 text-sm text-slate-800"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              제목
              <input
                value={coverTitle}
                onChange={(e) => setCoverTitle(e.target.value)}
                placeholder="후두의 질환 및 치료"
                className="w-72 rounded-md border border-slate-200 px-2.5 py-1.5 text-sm text-slate-800"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-slate-500">
              교수님
              <input
                value={coverProfessor}
                onChange={(e) => setCoverProfessor(e.target.value)}
                placeholder="홍길동 교수님"
                className="w-44 rounded-md border border-slate-200 px-2.5 py-1.5 text-sm text-slate-800"
              />
            </label>
          </div>
          {/* 테마 팔레트 — 배경·글씨색을 한 쌍으로 고른다 */}
          <div className="mt-4 border-t border-slate-100 pt-4">
            <p className="mb-2.5 text-xs text-slate-500">테마</p>
            <div className="flex flex-wrap gap-3">
              {THEME_PRESETS.map((t) => {
                const selected = themeId === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => {
                      setThemeId(t.id);
                      setNoteBg(t.background);
                      setNoteText(t.text);
                    }}
                    className="flex flex-col items-center gap-1.5"
                    title={t.label}
                  >
                    <span
                      className={`flex h-14 w-14 items-center justify-center rounded-2xl border text-xl font-semibold transition ${
                        selected
                          ? "border-slate-400 ring-2 ring-slate-300 ring-offset-2"
                          : "border-slate-200"
                      }`}
                      style={{ backgroundColor: t.background, color: t.text }}
                    >
                      A
                    </span>
                    <span
                      className={`text-[11px] ${
                        selected ? "text-slate-700" : "text-slate-400"
                      }`}
                    >
                      {t.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
          <p className="mt-3 text-xs text-slate-400">
            표지 항목은 비워 두면 해당 줄이 빠집니다. 테마는 화면과 인쇄본에 함께 반영됩니다.
          </p>
        </div>

        {hasLectureDoc && (
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setViewMode("document")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                viewMode === "document"
                  ? "bg-brand-600 text-white border-brand-600"
                  : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
              }`}
            >
              전체 정리본
            </button>
            <button
              onClick={() => setViewMode("slides")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                viewMode === "slides"
                  ? "bg-brand-600 text-white border-brand-600"
                  : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"
              }`}
            >
              슬라이드별 보기
            </button>
          </div>
        )}

        {viewMode === "document" && result.lecture_document ? (
          <FullLectureNoteView
            document={result.lecture_document}
            onSlideRef={(pageNum) => {
              const idx = result.pages.findIndex((p) => p.page === pageNum);
              if (idx >= 0) {
                setPageIndex(idx);
                setViewMode("slides");
              }
            }}
          />
        ) : (
          <>
        <div className="flex justify-between items-center mb-3">
          <div>
            {currentPage.page_type === "section" && (
              <span className="text-xs text-violet-700 bg-violet-50 px-2 py-1 rounded">
                구분/제목 슬라이드
              </span>
            )}
            {currentPage.page_type === "image_only" && (
              <span className="text-xs text-teal-700 bg-teal-50 px-2 py-1 rounded">
                그림/도표 슬라이드
              </span>
            )}
          </div>
          <button
            onClick={() => setShowScript((v) => !v)}
            className="text-sm px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600"
          >
            {showScript ? "원본 스크립트 숨기기" : "원본 스크립트 보기"}
          </button>
        </div>
        <div
          className={`grid grid-cols-1 gap-6 ${
            showScript ? "xl:grid-cols-3" : "lg:grid-cols-2"
          }`}
        >
          <PdfPreview
            imageUrl={imageUrl}
            pageNumber={currentPage.page}
            totalPages={totalPages}
          />
          {result.note_mode === "quiz" ? (
            <QuizPanel
              quiz={currentPage.quiz || []}
              hasScripts={currentPage.matched_scripts.length > 0}
              pageKey={currentPage.page}
            />
          ) : result.note_mode === "full_note" ? (
            <SummaryPanel
              summary={currentPage.summary || []}
              hasScripts={currentPage.matched_scripts.length > 0}
              title="슬라이드 메모"
              subtitle="전체 정리본은 상단 탭에서 확인"
              boxColor={noteBg}
              textColor={noteText}
            />
          ) : (
            <SummaryPanel
              summary={currentPage.summary || []}
              hasScripts={currentPage.matched_scripts.length > 0}
              boxColor={noteBg}
              textColor={noteText}
            />
          )}
          {showScript && (
            <ScriptPanel
              scripts={currentPage.matched_scripts}
              readabilityMode={!!result.readability_mode}
              highlightMode={!!result.highlight_mode}
              backgroundColor={noteBg}
              textColor={noteText}
              textSize={result.text_size}
            />
          )}
        </div>
          </>
        )}
      </div>

      {viewMode === "slides" && (
      <footer className="no-print fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 py-4">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-center gap-6">
          <button
            onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
            disabled={pageIndex === 0}
            className="px-6 py-2 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
          >
            Prev
          </button>
          <span className="text-sm font-medium text-slate-600">
            Page {currentPage.page} / {totalPages}
          </span>
          <button
            onClick={() => setPageIndex((i) => Math.min(totalPages - 1, i + 1))}
            disabled={pageIndex >= totalPages - 1}
            className="px-6 py-2 rounded-lg border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
          >
            Next
          </button>
        </div>
      </footer>
      )}

      {/* 화면에는 보이지 않고 인쇄할 때만 나타나는 레이아웃 */}
      <div className="hidden print:block">
        <PrintView
          result={result}
          imageUrlFor={resolveImageUrl}
          cover={{
            session: coverSession,
            title: coverTitle,
            professor: coverProfessor,
          }}
          boxColor={noteBg}
          textColor={noteText}
        />
      </div>
    </main>
  );
}
