"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import UploadPanel from "@/components/UploadPanel";
import CustomizePanel from "@/components/CustomizePanel";
import SettingsSidebar from "@/components/SettingsSidebar";
import ProgressBar from "@/components/ProgressBar";
import { createTranscriptJob } from "@/lib/api";
import { getThemeById, type TextSizeId, type ThemeId } from "@/lib/themes";

export default function HomePage() {
  const router = useRouter();
  const [transcriptFile, setTranscriptFile] = useState<File | null>(null);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [readabilityMode, setReadabilityMode] = useState(false);
  const [highlightMode, setHighlightMode] = useState(true);
  const [noteMode, setNoteMode] = useState<"summary" | "quiz" | "full_note">("summary");
  const [customPrompt, setCustomPrompt] = useState("");
  const [themeId, setThemeId] = useState<ThemeId>("classic");
  const [textSize, setTextSize] = useState<TextSizeId>("base");
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [doneJobId, setDoneJobId] = useState<string | null>(null);
  const [progressMessage, setProgressMessage] = useState("");
  const [transcribeProgress, setTranscribeProgress] = useState(0);
  const [matchingProgress, setMatchingProgress] = useState(0);
  const [phase, setPhase] = useState<"queued" | "transcribe" | "matching" | "polish" | "done">("queued");
  const startedRef = useRef(false);

  const handleSubmit = async () => {
    if (!transcriptFile || !pdfFile || startedRef.current) return;
    startedRef.current = true;
    setLoading(true);
    setError(null);
    setDoneJobId(null);

    try {
      const theme = getThemeById(themeId);
      const options = {
        readability_mode: readabilityMode,
        highlight_mode: highlightMode,
        summary_mode: true,
        note_mode: noteMode,
        custom_prompt: customPrompt,
        background_color: theme.background,
        text_color: theme.text,
        text_size: textSize,
      };
      const { job_id } = await createTranscriptJob(transcriptFile, pdfFile, options);
      setProcessing(true);
      setTranscribeProgress(0);
      setMatchingProgress(0);
      setPhase("queued");
      setProgressMessage("처리 시작...");

      const poll = async () => {
        const { getJobStatus } = await import("@/lib/api");
        const status = await getJobStatus(job_id);
        setTranscribeProgress(status.transcribe_progress);
        setMatchingProgress(status.matching_progress);
        setPhase(status.phase);
        setProgressMessage(status.message);

        if (status.status === "done") {
          setPhase("done");
          setProgressMessage("완료");
          setTranscribeProgress(100);
          setMatchingProgress(100);
          setDoneJobId(job_id);
          setLoading(false);
          return;
        }
        if (status.status === "error") {
          setError(status.error || "처리 중 오류가 발생했습니다.");
          setProcessing(false);
          setLoading(false);
          startedRef.current = false;
          return;
        }
        setTimeout(poll, 500);
      };
      poll();
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 실패");
      setLoading(false);
      setProcessing(false);
      startedRef.current = false;
    }
  };

  return (
    <main className="min-h-screen bg-[#FAFAF7] relative overflow-x-hidden text-[#3F3F46]">
      <header className="border-b border-black/[0.07]">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between gap-6">
          <Link href="/" className="inline-flex items-center gap-3 leading-none">
            <span className="font-reading text-[1.8rem] font-semibold tracking-[-0.045em] text-black">
              1Q
            </span>
            <span className="hidden sm:block h-[18px] w-px bg-black/15" />
            <span className="hidden sm:block font-sans text-[9px] uppercase tracking-[0.28em] text-black/35">
              lecture notes
            </span>
          </Link>
          <nav className="flex items-center gap-5 font-sans text-[12px] tracking-wide text-black/45">
            <Link href="/batch" className="hover:text-black/80 transition-colors">
              여러 강의 한번에
            </Link>
            <a href="#how-to-use" className="hover:text-black/80 transition-colors">
              how to use
            </a>
            <a href="#help" className="hover:text-black/80 transition-colors">
              help
            </a>
          </nav>
        </div>
      </header>

      {/* 표제 — 인쇄물 표지와 같은 짜임 */}
      {!processing && (
        <section className="max-w-5xl mx-auto px-6 pt-20 pb-4 text-center">
          <p className="font-sans text-[11px] uppercase tracking-[0.3em] text-black/35">
            Lecture Script Matcher
          </p>
          <div className="mx-auto mt-7 h-px w-14 bg-black/15" />
          <h1 className="font-reading mt-7 text-[30px] md:text-[34px] font-semibold leading-[1.5] tracking-[-0.01em]">
            한 번의 클릭으로 완성되는 필기
          </h1>
          <p className="font-reading mx-auto mt-4 max-w-[30em] text-[15px] leading-[1.9] text-black/50">
            강의 전사본과 강의록을 올리면, 슬라이드마다 교수님이 하신 말을 붙여
            정리본으로 만들어 드립니다.
          </p>
          <div className="mx-auto mt-7 h-px w-14 bg-black/15" />
        </section>
      )}

      {!processing && (
        <SettingsSidebar
          open={settingsOpen}
          onToggle={() => setSettingsOpen((v) => !v)}
          readabilityMode={readabilityMode}
          highlightMode={highlightMode}
          onReadabilityChange={setReadabilityMode}
          onHighlightChange={setHighlightMode}
        />
      )}

      <div className="max-w-5xl mx-auto px-6 pt-10 md:pt-12 pb-16">
        <UploadPanel
          transcriptFile={transcriptFile}
          pdfFile={pdfFile}
          onTranscriptSelect={setTranscriptFile}
          onPdfSelect={setPdfFile}
          onSubmit={handleSubmit}
          loading={loading}
          processing={processing}
          error={error}
          optionsOpen={optionsOpen}
          onToggleOptions={() => setOptionsOpen((v) => !v)}
        >
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
        </UploadPanel>

        {processing && (
          <ProgressBar
            message={progressMessage}
            transcribeProgress={transcribeProgress}
            matchingProgress={matchingProgress}
            phase={phase}
            canView={!!doneJobId}
            onView={() => doneJobId && router.push(`/result/${doneJobId}`)}
          />
        )}

        <section
          id="how-to-use"
          className="font-reading mt-24 pt-8 border-t border-black/[0.07] text-[14px] leading-[1.9] text-black/55 space-y-3 max-w-[860px] mx-auto"
        >
          <h2 className="font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-black/40">
            how to use
          </h2>
          <ol className="list-decimal list-inside space-y-1.5">
            <li>Upload transcript로 텍스트 스크립트(전사본)를 올립니다.</li>
            <li>Upload lecture로 PDF 강의록을 올립니다.</li>
            <li>오른쪽 설정에서 가독성·하이라이트를, customizing에서 테마·노트 모드를 고릅니다.</li>
            <li>두 파일을 올린 뒤 Done을 누르면 처리가 시작됩니다.</li>
          </ol>
        </section>

        <section
          id="help"
          className="font-reading mt-10 text-[14px] leading-[1.9] text-black/55 space-y-2 max-w-[860px] mx-auto"
        >
          <h2 className="font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-black/40">
            help
          </h2>
          <p>지원 전사본: txt, md, 워드(docx), pdf, vtt, srt · 강의록: PDF</p>
          <Link href="/result/demo" className="underline underline-offset-4 hover:text-black/80">
            demo 결과 미리보기 →
          </Link>
        </section>
      </div>
    </main>
  );
}
