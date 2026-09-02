"use client";

import { useEffect, useState } from "react";
import { getDefaultPrompts, type DefaultPrompts } from "@/lib/api";
import {
  TEXT_SIZE_OPTIONS,
  THEME_PRESETS,
  type TextSizeId,
  type ThemeId,
} from "@/lib/themes";

export type NoteMode = "summary" | "quiz" | "full_note";

interface OptionPanelProps {
  readabilityMode: boolean;
  highlightMode: boolean;
  summaryMode: boolean;
  noteMode: NoteMode;
  customPrompt: string;
  themeId: ThemeId;
  textSize: TextSizeId;
  onReadabilityChange: (v: boolean) => void;
  onHighlightChange: (v: boolean) => void;
  onSummaryChange: (v: boolean) => void;
  onNoteModeChange: (v: NoteMode) => void;
  onCustomPromptChange: (v: string) => void;
  onThemeChange: (v: ThemeId) => void;
  onTextSizeChange: (v: TextSizeId) => void;
}

export default function OptionPanel({
  readabilityMode,
  highlightMode,
  summaryMode,
  noteMode,
  customPrompt,
  themeId,
  textSize,
  onReadabilityChange,
  onHighlightChange,
  onSummaryChange,
  onNoteModeChange,
  onCustomPromptChange,
  onThemeChange,
  onTextSizeChange,
}: OptionPanelProps) {
  const [defaultPrompts, setDefaultPrompts] = useState<DefaultPrompts | null>(null);
  const [showPromptEditor, setShowPromptEditor] = useState(false);

  useEffect(() => {
    getDefaultPrompts()
      .then(setDefaultPrompts)
      .catch(() => setDefaultPrompts(null));
  }, []);

  // 모드 변경 시 해당 모드의 기본 프롬프트로 교체
  const handleModeChange = (mode: NoteMode) => {
    onNoteModeChange(mode);
    if (defaultPrompts) {
      onCustomPromptChange(defaultPrompts[mode]);
    }
  };

  // 기본 프롬프트가 로드되고 아직 프롬프트가 비어 있으면 채운다
  useEffect(() => {
    if (defaultPrompts && !customPrompt) {
      onCustomPromptChange(defaultPrompts[noteMode]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultPrompts]);
  return (
    <div className="bg-white rounded-2xl border border-black/[0.06] p-6 shadow-sm space-y-5">
      <h3 className="text-sm font-semibold text-slate-700">
        Options
      </h3>

      <label className="flex items-center justify-between cursor-pointer">
        <span className="text-slate-700">가독성 모드</span>
        <input
          type="checkbox"
          checked={readabilityMode}
          onChange={(e) => onReadabilityChange(e.target.checked)}
          className="w-5 h-5 rounded accent-brand-600"
        />
      </label>

      <label className="flex items-center justify-between cursor-pointer">
        <span className="text-slate-700">중요 하이라이트</span>
        <input
          type="checkbox"
          checked={highlightMode}
          onChange={(e) => onHighlightChange(e.target.checked)}
          className="w-5 h-5 rounded accent-brand-600"
        />
      </label>

      <label className="flex items-center justify-between cursor-pointer">
        <span className="text-slate-700">
          AI 노트 생성 <span className="text-xs text-slate-400">(슬라이드별 정리/퀴즈)</span>
        </span>
        <input
          type="checkbox"
          checked={summaryMode}
          onChange={(e) => onSummaryChange(e.target.checked)}
          className="w-5 h-5 rounded accent-brand-600"
        />
      </label>

      {summaryMode && (
        <div className="space-y-3 pl-1 border-l-2 border-brand-100 ml-1">
          <div className="flex gap-2 pl-3">
            {(
              [
                {
                  mode: "summary" as const,
                  label: "핵심 정리",
                  desc: "개조식 요약 노트",
                },
                {
                  mode: "quiz" as const,
                  label: "복습 퀴즈",
                  desc: "발화량 비례 출제",
                },
                {
                  mode: "full_note" as const,
                  label: "전체 정리본",
                  desc: "강의 통합 문서 1장",
                },
              ] as { mode: NoteMode; label: string; desc: string }[]
            ).map(({ mode, label, desc }) => (
              <button
                key={mode}
                type="button"
                onClick={() => handleModeChange(mode)}
                className={`flex-1 text-sm px-2 py-2 rounded-lg border transition ${
                  noteMode === mode
                    ? "border-brand-500 bg-brand-50 text-brand-700 font-medium"
                    : "border-slate-200 text-slate-500 hover:bg-slate-50"
                }`}
              >
                {label}
                <span className="block text-[11px] font-normal text-slate-400">
                  {desc}
                </span>
              </button>
            ))}
          </div>

          <div className="pl-3">
            <button
              type="button"
              onClick={() => setShowPromptEditor((v) => !v)}
              className="text-xs text-slate-500 hover:text-slate-700 underline"
            >
              {showPromptEditor ? "시스템 프롬프트 접기" : "시스템 프롬프트 직접 수정"}
            </button>
            {showPromptEditor && (
              <div className="mt-2 space-y-2">
                <textarea
                  value={customPrompt}
                  onChange={(e) => onCustomPromptChange(e.target.value)}
                  rows={10}
                  spellCheck={false}
                  className="w-full text-xs font-mono border border-slate-200 rounded-lg p-3 leading-relaxed text-slate-700 focus:outline-none focus:ring-2 focus:ring-brand-200"
                  placeholder="시스템 프롬프트를 입력하세요..."
                />
                <div className="flex items-center justify-between">
                  <p className="text-[11px] text-slate-400">
                    이 프롬프트가{" "}
                    {noteMode === "quiz"
                      ? "퀴즈 출제"
                      : noteMode === "full_note"
                      ? "전체 정리본"
                      : "핵심 정리"}{" "}
                    AI에게 그대로 전달됩니다.
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      defaultPrompts && onCustomPromptChange(defaultPrompts[noteMode])
                    }
                    className="text-[11px] text-brand-600 hover:underline shrink-0 ml-2"
                  >
                    기본값 복원
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="pt-2 border-t border-slate-100 space-y-6">
        {/* Theme */}
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          <span className="text-sm font-semibold text-slate-800 shrink-0 sm:w-24 pt-1">
            Theme
          </span>
          <div className="flex flex-wrap gap-4 flex-1">
            {THEME_PRESETS.map((theme) => {
              const selected = themeId === theme.id;
              return (
                <button
                  key={theme.id}
                  type="button"
                  onClick={() => onThemeChange(theme.id)}
                  className={`flex flex-col items-center gap-1.5 rounded-xl px-2 py-2 transition ${
                    selected ? "bg-slate-200/70 ring-1 ring-slate-300" : "hover:bg-slate-50"
                  }`}
                >
                  <div
                    className="w-14 h-14 rounded-xl flex items-center justify-center text-2xl font-semibold shadow-sm"
                    style={{
                      backgroundColor: theme.background,
                      color: theme.text,
                      border: `1px solid ${theme.tileBorder || "#e2e8f0"}`,
                    }}
                  >
                    A
                  </div>
                  <span className="text-[11px] text-slate-500 whitespace-nowrap">
                    {theme.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Text size */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
          <span className="text-sm font-semibold text-slate-800 shrink-0 sm:w-24">
            Text size
          </span>
          <div className="flex items-end gap-6 flex-wrap">
            {TEXT_SIZE_OPTIONS.map((opt) => {
              const selected = textSize === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => onTextSizeChange(opt.id)}
                  className={`rounded-lg px-3 py-1.5 transition ${
                    selected ? "bg-slate-200/70 ring-1 ring-slate-300" : "hover:bg-slate-50"
                  }`}
                >
                  <span
                    className={`font-medium text-slate-700 ${opt.previewClass}`}
                  >
                    {opt.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 미리보기 */}
        <div className="rounded-xl border border-slate-200 p-4">
          <p className="text-xs text-slate-400 mb-2">스크립트 미리보기</p>
          <div
            className={`rounded-lg p-4 leading-relaxed ${
              textSize === "lg" ? "text-lg" : textSize === "sm" ? "text-sm" : "text-base"
            }`}
            style={{
              backgroundColor: THEME_PRESETS.find((t) => t.id === themeId)?.background,
              color: THEME_PRESETS.find((t) => t.id === themeId)?.text,
            }}
          >
            후두연화증은 성대 위 연부 연골의 연화로 인한 기도 협착 질환임. 교수님이
            강조하신 stridor 소견을 기억할 것.
          </div>
        </div>
      </div>
    </div>
  );
}
