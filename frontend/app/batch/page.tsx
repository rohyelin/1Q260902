"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { createTranscriptJob, getJobStatus } from "@/lib/api";

const STORAGE_KEY = "batchJobs_v1";

type Row = { id: number; transcript: File | null; pdf: File | null };
type Job = {
  jobId: string;
  name: string;
  status: "queued" | "processing" | "done" | "error";
  progress: number;
  message: string;
};

let _rid = 1;

function FilePick({
  label,
  accept,
  file,
  onPick,
}: {
  label: string;
  accept: string;
  file: File | null;
  onPick: (f: File | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="flex-1 min-w-0">
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
      />
      <button
        type="button"
        onClick={() => ref.current?.click()}
        className={`w-full text-left text-sm px-3 py-2 rounded-lg border truncate transition ${
          file
            ? "border-[#C4A55F] bg-[#C4A55F]/10 text-slate-800"
            : "border-slate-300 bg-white text-slate-500 hover:bg-slate-50"
        }`}
        title={file?.name || label}
      >
        {file ? `✓ ${file.name}` : label}
      </button>
    </div>
  );
}

function Badge({ job }: { job: Job }) {
  const map: Record<string, { text: string; cls: string }> = {
    queued: { text: "대기 중", cls: "bg-slate-100 text-slate-600" },
    processing: { text: `처리 중 ${job.progress}%`, cls: "bg-blue-100 text-blue-700" },
    done: { text: "완료", cls: "bg-green-100 text-green-700" },
    error: { text: "오류", cls: "bg-red-100 text-red-700" },
  };
  const s = map[job.status] || map.queued;
  return <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${s.cls}`}>{s.text}</span>;
}

export default function BatchPage() {
  const [rows, setRows] = useState<Row[]>([
    { id: _rid++, transcript: null, pdf: null },
    { id: _rid++, transcript: null, pdf: null },
    { id: _rid++, transcript: null, pdf: null },
  ]);
  const [noteMode, setNoteMode] = useState<"summary" | "quiz" | "full_note">("summary");
  const [readability, setReadability] = useState(true);
  const [highlight, setHighlight] = useState(true);
  const [customPrompt, setCustomPrompt] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [started, setStarted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 새로고침/재방문 시 이전 배치 복원
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved: { jobId: string; name: string }[] = JSON.parse(raw);
        if (saved.length) {
          setJobs(saved.map((s) => ({ ...s, status: "queued", progress: 0, message: "확인 중" })));
          setStarted(true);
        }
      }
    } catch {}
  }, []);

  const setFile = (id: number, key: "transcript" | "pdf", f: File | null) =>
    setRows((r) => r.map((x) => (x.id === id ? { ...x, [key]: f } : x)));
  const addRow = () => setRows((r) => [...r, { id: _rid++, transcript: null, pdf: null }]);
  const removeRow = (id: number) => setRows((r) => (r.length > 1 ? r.filter((x) => x.id !== id) : r));

  const ready = rows.filter((r) => r.transcript && r.pdf);

  const startAll = async () => {
    if (!ready.length || submitting) return;
    setSubmitting(true);
    setError(null);
    const created: Job[] = [];
    try {
      for (const r of ready) {
        const base = (r.pdf!.name || r.transcript!.name).replace(/\.(pdf|txt|md|docx|vtt|srt)$/i, "");
        const { job_id } = await createTranscriptJob(r.transcript!, r.pdf!, {
          readability_mode: readability,
          highlight_mode: highlight,
          summary_mode: true,
          note_mode: noteMode,
          custom_prompt: customPrompt || undefined,
        });
        created.push({ jobId: job_id, name: base, status: "queued", progress: 0, message: "대기 중" });
      }
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(created.map((j) => ({ jobId: j.jobId, name: j.name }))));
      } catch {}
      setJobs(created);
      setStarted(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "업로드 중 오류가 발생했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  const resetBatch = () => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
    setJobs([]);
    setStarted(false);
    setRows([
      { id: _rid++, transcript: null, pdf: null },
      { id: _rid++, transcript: null, pdf: null },
      { id: _rid++, transcript: null, pdf: null },
    ]);
  };

  // 상태 폴링
  useEffect(() => {
    if (!started) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const ids = jobs.map((j) => j.jobId);
    if (!ids.length) return;

    const loop = async () => {
      if (cancelled) return;
      const results = await Promise.all(
        ids.map(async (id) => {
          try {
            const s = await getJobStatus(id);
            return { id, s };
          } catch {
            return { id, s: null as null | Awaited<ReturnType<typeof getJobStatus>> };
          }
        })
      );
      if (cancelled) return;
      setJobs((prev) =>
        prev.map((j) => {
          const found = results.find((x) => x.id === j.jobId);
          if (found && found.s) {
            return { ...j, status: found.s.status, progress: found.s.progress, message: found.s.message };
          }
          return j;
        })
      );
      const allDone = results.every((x) => x.s && (x.s.status === "done" || x.s.status === "error"));
      if (!cancelled && !allDone) timer = setTimeout(loop, 1500);
    };
    loop();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [started]);

  const doneCount = jobs.filter((j) => j.status === "done").length;

  return (
    <main className="min-h-screen bg-[#f5f5f0]">
      <header className="border-b border-black/10 bg-[#f5f5f0]">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <Link href="/" className="text-sm text-slate-400 hover:text-slate-600">
              ← 단일 업로드로
            </Link>
            <h1 className="text-lg font-semibold text-slate-800 mt-1">여러 강의 한번에 처리</h1>
          </div>
          <span className="text-sm text-[#C4A55F]">전사본 배치</span>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6 py-8">
        {!started ? (
          <>
            <div className="flex items-center gap-2 mb-5 text-sm">
              <span className="text-slate-600">정리본 형식:</span>
              <select
                value={noteMode}
                onChange={(e) => setNoteMode(e.target.value as "summary" | "quiz" | "full_note")}
                className="border border-slate-300 rounded-md px-2 py-1 bg-white"
              >
                <option value="summary">핵심 요약</option>
                <option value="quiz">복습 퀴즈</option>
                <option value="full_note">전체 정리본</option>
              </select>
              <span className="text-slate-400 text-xs">(배치 전체에 공통 적용)</span>
            </div>

            <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
              <label className="flex items-center gap-1.5 text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={readability}
                  onChange={(e) => setReadability(e.target.checked)}
                />
                가독성 (문어체 변환)
              </label>
              <label className="flex items-center gap-1.5 text-slate-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={highlight}
                  onChange={(e) => setHighlight(e.target.checked)}
                />
                핵심 하이라이트
              </label>
            </div>

            <div className="mb-5">
              <input
                type="text"
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                placeholder="커스텀 프롬프트 (선택) — 예: 표 위주로 정리해줘"
                className="w-full border border-slate-300 rounded-md px-3 py-2 bg-white text-sm"
              />
            </div>

            <div className="space-y-3">
              {rows.map((r, i) => (
                <div
                  key={r.id}
                  className="bg-white rounded-xl border border-black/[0.06] p-3 flex items-center gap-3 shadow-sm"
                >
                  <span className="text-sm font-medium text-slate-500 w-16 shrink-0">강의 {i + 1}</span>
                  <FilePick
                    label="전사본 (txt·docx·pdf…)"
                    accept=".txt,.md,.vtt,.srt,.pdf,.docx,text/plain"
                    file={r.transcript}
                    onPick={(f) => setFile(r.id, "transcript", f)}
                  />
                  <FilePick
                    label="강의록 PDF"
                    accept=".pdf,application/pdf"
                    file={r.pdf}
                    onPick={(f) => setFile(r.id, "pdf", f)}
                  />
                  <button
                    type="button"
                    onClick={() => removeRow(r.id)}
                    className="text-slate-300 hover:text-red-500 text-lg px-1 shrink-0"
                    title="이 줄 삭제"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>

            <button
              type="button"
              onClick={addRow}
              className="mt-3 text-sm text-[#C4A55F] hover:underline"
            >
              + 강의 추가
            </button>

            {error && (
              <p className="mt-4 text-sm text-red-600 bg-red-50 py-2 px-4 rounded-lg border border-red-200">{error}</p>
            )}

            <div className="mt-6 flex items-center gap-3">
              <button
                type="button"
                onClick={startAll}
                disabled={ready.length === 0 || submitting}
                className="px-6 py-2.5 rounded-lg text-black font-medium bg-[#C4A55F] border border-black/30 shadow-sm hover:brightness-105 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? "올리는 중…" : `전체 시작 (${ready.length}개)`}
              </button>
              <span className="text-xs text-slate-500">
                전사본+강의록 둘 다 고른 줄만 시작돼요. 동시에 2개씩, 나머진 대기열에서 순서대로.
              </span>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <p className="text-sm text-slate-600">
                전체 {jobs.length}개 중 <b className="text-green-700">{doneCount}개 완료</b>
              </p>
              <button
                type="button"
                onClick={resetBatch}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700"
              >
                새 배치 시작
              </button>
            </div>

            <div className="space-y-2">
              {jobs.map((j) => (
                <div
                  key={j.jobId}
                  className="bg-white rounded-xl border border-black/[0.06] p-4 flex items-center gap-3 shadow-sm"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate" title={j.name}>
                      {j.name}
                    </p>
                    <p className="text-xs text-slate-400 truncate">{j.message}</p>
                  </div>
                  <Badge job={j} />
                  {j.status === "done" ? (
                    <Link
                      href={`/result/${j.jobId}`}
                      className="text-sm px-3 py-1.5 rounded-lg bg-[#C4A55F] text-black font-medium border border-black/25 hover:brightness-105 shrink-0"
                    >
                      결과 보기
                    </Link>
                  ) : (
                    <span className="w-[70px] shrink-0" />
                  )}
                </div>
              ))}
            </div>

            <p className="mt-6 text-xs text-slate-500">
              창을 닫거나 새로고침해도 처리는 백그라운드에서 계속되고, 이 페이지를 다시 열면 목록이 그대로 나와요.
              (단, 백엔드 서버가 켜져 있어야 해요.)
            </p>
          </>
        )}
      </div>
    </main>
  );
}
