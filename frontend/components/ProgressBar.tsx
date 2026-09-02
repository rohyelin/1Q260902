"use client";

import { AccentButton } from "@/components/UploadPanel";

export type JobPhase = "queued" | "transcribe" | "matching" | "polish" | "done";

interface ProgressBarProps {
  message: string;
  transcribeProgress: number;
  matchingProgress: number;
  phase?: JobPhase;
  onView?: () => void;
  canView?: boolean;
}

export default function ProgressBar({
  message,
  transcribeProgress,
  matchingProgress,
  phase = "queued",
  onView,
  canView = false,
}: ProgressBarProps) {
  // 전체 진행률: 전사 55% + 매칭/폴리시 45%
  let overall = 0;
  if (phase === "queued") overall = 2;
  else if (phase === "transcribe") overall = Math.min(55, transcribeProgress * 0.55);
  else if (phase === "matching") overall = 55 + matchingProgress * 0.35;
  else if (phase === "polish") overall = 90 + matchingProgress * 0.08;
  else overall = 100;

  const pct = Math.round(Math.min(100, Math.max(0, overall)));

  return (
    <div className="w-full max-w-[520px] mx-auto mt-10 flex flex-col items-center gap-8">
      <div
        className="w-full h-9 rounded-md bg-[#6b8e6b] relative overflow-hidden
          shadow-[inset_0_3px_8px_rgba(0,0,0,0.35),inset_0_-1px_2px_rgba(255,255,255,0.15)]
          border border-black/20"
      >
        <div
          className="absolute inset-y-0 left-0 bg-[#5a7a5a] transition-all duration-500"
          style={{ width: `${pct}%`, opacity: 0.35 }}
        />
        <p className="absolute inset-0 flex items-center justify-center text-sm font-medium text-black/80 tabular-nums">
          {pct}%
        </p>
      </div>
      {message && (
        <p className="text-xs text-slate-500 -mt-6">{message}</p>
      )}

      {onView && (
        <AccentButton
          className="px-10 py-2.5 min-w-[100px]"
          onClick={onView}
          disabled={!canView}
        >
          view
        </AccentButton>
      )}
    </div>
  );
}
