"use client";

import { useRef, type ReactNode } from "react";

export const ACCENT = "#C4A55F";

export function AccentButton({
  children,
  className = "",
  onClick,
  type = "button",
  disabled,
  title,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit";
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type={type}
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`bg-[#C4A55F] text-black text-sm font-medium
        border border-black/30 rounded-[4px]
        shadow-[0_2px_0_rgba(0,0,0,0.28),0_3px_8px_rgba(0,0,0,0.12)]
        hover:brightness-105 active:translate-y-[1px] active:shadow-[0_1px_0_rgba(0,0,0,0.28)]
        disabled:opacity-50 disabled:cursor-not-allowed transition
        ${className}`}
    >
      {children}
    </button>
  );
}

/* 아이콘은 채우기 대신 얇은 선으로. 종이·잉크 느낌에 맞춘다. */
const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

function MicIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <g {...STROKE}>
        <rect x="19" y="7" width="10" height="20" rx="5" />
        <path d="M13.5 22.5a10.5 10.5 0 0 0 21 0" />
        <path d="M24 33v6" />
        <path d="M18.5 39h11" />
        <path d="M22 12.5h4M22 16.5h4M22 20.5h4" opacity="0.45" />
      </g>
    </svg>
  );
}

function LectureIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 56 48" className={className} aria-hidden>
      <g {...STROKE}>
        <rect x="8" y="6" width="40" height="26" rx="1.5" />
        <path d="M14 13h16M14 19h22M14 25h12" opacity="0.45" />
        <path d="M28 32v4" />
        <path d="M20 42h16" />
        <path d="M24 42l4-6 4 6" />
      </g>
    </svg>
  );
}

function TranscriptIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden>
      <g {...STROKE}>
        <path d="M12 6h16l8 8v28H12z" />
        <path d="M28 6v8h8" />
        <path d="M18 22h12M18 28h12M18 34h8" opacity="0.45" />
      </g>
    </svg>
  );
}

interface UploadCardProps {
  title: string;
  accept: string;
  file: File | null;
  onFileSelect: (file: File | null) => void;
  icon: ReactNode;
  processing?: boolean;
}

function UploadCard({
  title,
  accept,
  file,
  onFileSelect,
  icon,
  processing,
}: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  if (processing) {
    return (
      <div
        className="flex-1 min-h-[260px] md:min-h-[300px] rounded-[42px] bg-[#EDEAE0]
          flex items-center justify-center
          shadow-[inset_0_2px_10px_rgba(255,255,255,0.35),0_6px_18px_rgba(60,90,80,0.12)]"
      >
        <div className="w-28 h-28 text-[#8A8375] drop-shadow-[0_2px_6px_rgba(40,80,60,0.35)]">
          {icon}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex-1 min-h-[260px] md:min-h-[300px] rounded-[20px] bg-white px-8 py-10
        flex flex-col items-center justify-between
        shadow-[0_1px_2px_rgba(63,63,70,0.04)]
        border border-[#E7E4DA]
        ${file ? "outline outline-2 outline-[#C4A55F]/50" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onFileSelect(e.target.files?.[0] ?? null)}
      />
      <div className="flex-1 flex items-center justify-center text-[#6E6A5E] w-28 h-28">
        {icon}
      </div>
      <div className="w-full flex flex-col items-center gap-2">
        <AccentButton
          className="w-full max-w-[190px] py-2.5"
          onClick={() => inputRef.current?.click()}
        >
          {title}
        </AccentButton>
        {file && (
          <p
            className="text-[11px] text-slate-600 truncate max-w-full bg-[#FAFAF7] rounded px-2 py-0.5"
            title={file.name}
          >
            {file.name}
          </p>
        )}
      </div>
    </div>
  );
}

type InputMode = "audio" | "transcript";

interface UploadPanelProps {
  inputMode: InputMode;
  onInputModeChange: (m: InputMode) => void;
  audioFile: File | null;
  transcriptFile: File | null;
  pdfFile: File | null;
  onAudioSelect: (f: File | null) => void;
  onTranscriptSelect: (f: File | null) => void;
  onPdfSelect: (f: File | null) => void;
  onSubmit: () => void;
  loading: boolean;
  processing: boolean;
  error: string | null;
  optionsOpen: boolean;
  onToggleOptions: () => void;
  children?: ReactNode;
}

function ModeToggle({
  mode,
  onChange,
}: {
  mode: InputMode;
  onChange: (m: InputMode) => void;
}) {
  const base =
    "px-4 py-1.5 text-sm font-medium rounded-full transition select-none";
  const active = "bg-[#C4A55F] text-black shadow-[0_1px_0_rgba(0,0,0,0.25)]";
  const idle = "text-slate-500 hover:text-slate-800";
  return (
    <div className="inline-flex items-center gap-1 p-1 rounded-full bg-white border border-[#E7E4DA]">
      <button
        type="button"
        onClick={() => onChange("audio")}
        className={`${base} ${mode === "audio" ? active : idle}`}
      >
        녹음본 업로드
      </button>
      <button
        type="button"
        onClick={() => onChange("transcript")}
        className={`${base} ${mode === "transcript" ? active : idle}`}
      >
        전사본 업로드
      </button>
    </div>
  );
}

export default function UploadPanel({
  inputMode,
  onInputModeChange,
  audioFile,
  transcriptFile,
  pdfFile,
  onAudioSelect,
  onTranscriptSelect,
  onPdfSelect,
  onSubmit,
  loading,
  processing,
  error,
  optionsOpen,
  onToggleOptions,
  children,
}: UploadPanelProps) {
  const primaryFile = inputMode === "audio" ? audioFile : transcriptFile;
  const canSubmit = !!(primaryFile && pdfFile && !loading && !processing);

  return (
    <div className="relative w-full max-w-[860px] mx-auto">
      {!processing && (
        <div className="flex justify-center mb-6">
          <ModeToggle mode={inputMode} onChange={onInputModeChange} />
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-8 md:gap-10 px-2">
        {inputMode === "audio" ? (
          <UploadCard
            title="Upload record"
            accept=".mp3,.m4a,.wav,.mp4,.webm,audio/*"
            file={audioFile}
            onFileSelect={onAudioSelect}
            icon={<MicIcon className="w-full h-full" />}
            processing={processing}
          />
        ) : (
          <UploadCard
            title="Upload transcript"
            accept=".txt,.md,.vtt,.srt,.pdf,.docx,text/plain"
            file={transcriptFile}
            onFileSelect={onTranscriptSelect}
            icon={<TranscriptIcon className="w-full h-full" />}
            processing={processing}
          />
        )}
        <UploadCard
          title="Upload lecture"
          accept=".pdf,application/pdf"
          file={pdfFile}
          onFileSelect={onPdfSelect}
          icon={<LectureIcon className="w-full h-full" />}
          processing={processing}
        />
      </div>

      {!processing && (
        <div className="mt-10 relative flex flex-col sm:flex-row sm:items-start gap-4">
          <div className="flex-1">
            <AccentButton
              onClick={onToggleOptions}
              className="inline-flex items-center gap-0 px-0 overflow-hidden"
            >
              <span className="px-5 py-2.5">customizing</span>
              <span className="px-3 py-2.5 border-l border-black/25 text-[10px] text-white/90">
                {optionsOpen ? "▲" : "▼"}
              </span>
            </AccentButton>

            {optionsOpen && <div className="mt-3">{children}</div>}
          </div>

          <AccentButton
            onClick={onSubmit}
            disabled={!canSubmit}
            className="px-10 py-2.5 self-start sm:ml-auto"
          >
            {loading ? "업로드 중..." : "Done"}
          </AccentButton>
        </div>
      )}

      {error && (
        <p className="mt-4 text-center text-red-600 text-sm bg-red-50 py-2 px-4 rounded-lg border border-red-200">
          {error}
        </p>
      )}
    </div>
  );
}
