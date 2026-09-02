"use client";

import { useState } from "react";
import type { MatchedScript } from "@/lib/api";

interface ScriptPanelProps {
  scripts: MatchedScript[];
  readabilityMode: boolean;
  highlightMode: boolean;
  backgroundColor?: string | null;
  textColor?: string | null;
  textSize?: string | null;
}

function highlightText(text: string, keywords: string[]): React.ReactNode {
  if (!keywords.length) return text;

  const pattern = new RegExp(
    `(${keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
    "g"
  );
  const parts = text.split(pattern);

  return parts.map((part, i) =>
    keywords.includes(part) ? (
      // 빨간 글씨 대신 노란 배경. 색을 늘리지 않고 강조만 남긴다.
      <mark key={i} className="bg-amber-200/70 text-inherit font-semibold px-0.5 rounded-sm">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

function ScriptBlock({
  script,
  readabilityMode,
  highlightMode,
}: {
  script: MatchedScript;
  readabilityMode: boolean;
  highlightMode: boolean;
}) {
  const [showRaw, setShowRaw] = useState(false);
  const baseText = script.corrected_text || script.raw_text;
  const displayText =
    readabilityMode && script.clean_text ? script.clean_text : baseText;
  const keywords = highlightMode ? script.highlights : [];

  return (
    <div className="border-b border-slate-100 pb-5 mb-5 last:border-0 last:mb-0 last:pb-0">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        {/* 부가정보이므로 본문보다 작고 옅게 */}
        <div className="text-[10px] font-sans tracking-wide text-slate-400 tabular-nums">
          {script.start_time} – {script.end_time}
        </div>
        {script.carried_over && (
          <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
            이전 슬라이드 연속
          </span>
        )}
        {script.low_confidence && !script.carried_over && (
          <span className="text-xs text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">
            매칭 신뢰도 낮음
          </span>
        )}
      </div>
      <p className="font-reading leading-[1.85] whitespace-pre-wrap">
        {highlightMode ? highlightText(displayText, keywords) : displayText}
      </p>
      {(readabilityMode && script.clean_text) ||
      (script.corrected_text && script.corrected_text !== script.raw_text) ? (
        <button
          onClick={() => setShowRaw(!showRaw)}
          className="mt-2 text-xs text-slate-400 hover:text-slate-600 underline"
        >
          {showRaw ? "원문 접기" : "전사 원문 보기"}
        </button>
      ) : null}
      {showRaw && (
        <p className="mt-2 text-sm text-slate-500 italic border-l-2 border-slate-200 pl-3">
          {highlightMode ? highlightText(script.raw_text, keywords) : script.raw_text}
        </p>
      )}
    </div>
  );
}

const TEXT_SIZE_MAP: Record<string, string> = {
  sm: "text-sm",
  base: "text-base",
  lg: "text-lg",
};

export default function ScriptPanel({
  scripts,
  readabilityMode,
  highlightMode,
  backgroundColor,
  textColor,
  textSize,
}: ScriptPanelProps) {
  const sizeClass = TEXT_SIZE_MAP[textSize || "base"] || "text-base";

  return (
    <div className="flex flex-col h-full">
      <h2 className="mb-3 px-1 font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        교수님 설명
      </h2>
      <div
        className={`flex-1 rounded-xl border border-slate-200 px-6 py-6 overflow-y-auto min-h-[500px] ${sizeClass}`}
        style={{
          backgroundColor: backgroundColor || "#ffffff",
          color: textColor || "#0f172a",
        }}
      >
        {scripts.length === 0 ? (
          <div className="text-center py-12 px-4">
            <p className="text-3xl mb-3">🗒️</p>
            <p className="text-slate-500 font-medium">매칭된 발화가 없습니다</p>
            <p className="text-slate-400 text-sm mt-2 leading-relaxed">
              교수님이 설명 없이 넘어갔거나, 제목·그림 위주 슬라이드로 보입니다.
            </p>
          </div>
        ) : (
          scripts.map((script) => (
            <ScriptBlock
              key={script.chunk_id}
              script={script}
              readabilityMode={readabilityMode}
              highlightMode={highlightMode}
            />
          ))
        )}
      </div>
    </div>
  );
}
