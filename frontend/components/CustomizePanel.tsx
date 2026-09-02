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

interface CustomizePanelProps {
  noteMode: NoteMode;
  customPrompt: string;
  themeId: ThemeId;
  textSize: TextSizeId;
  onNoteModeChange: (v: NoteMode) => void;
  onCustomPromptChange: (v: string) => void;
  onThemeChange: (v: ThemeId) => void;
  onTextSizeChange: (v: TextSizeId) => void;
}

export default function CustomizePanel({
  noteMode,
  customPrompt,
  themeId,
  textSize,
  onNoteModeChange,
  onCustomPromptChange,
  onThemeChange,
  onTextSizeChange,
}: CustomizePanelProps) {
  const [defaultPrompts, setDefaultPrompts] = useState<DefaultPrompts | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    getDefaultPrompts()
      .then(setDefaultPrompts)
      .catch(() => setDefaultPrompts(null));
  }, []);

  useEffect(() => {
    if (defaultPrompts && !customPrompt) {
      onCustomPromptChange(defaultPrompts[noteMode]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultPrompts]);

  const handleModeChange = (mode: NoteMode) => {
    onNoteModeChange(mode);
    if (defaultPrompts) onCustomPromptChange(defaultPrompts[mode]);
  };

  return (
    <div
      className="w-full max-w-[720px] rounded-xl bg-[#ecece8] border border-black/20
        shadow-[inset_2px_2px_6px_rgba(0,0,0,0.08),0_4px_14px_rgba(0,0,0,0.08)]
        px-5 py-4 space-y-5"
    >
      {/* Note mode */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <span className="text-sm font-semibold text-slate-700 shrink-0 sm:w-24">
          Note
        </span>
        <div className="flex flex-wrap gap-2">
          {(
            [
              { mode: "summary" as const, label: "핵심 정리" },
              { mode: "quiz" as const, label: "복습 퀴즈" },
              { mode: "full_note" as const, label: "전체 정리본" },
            ] as const
          ).map(({ mode, label }) => (
            <button
              key={mode}
              type="button"
              onClick={() => handleModeChange(mode)}
              className={`text-xs px-3 py-1.5 rounded-md border transition ${
                noteMode === mode
                  ? "bg-white border-slate-400 text-slate-800 font-medium shadow-sm"
                  : "bg-transparent border-transparent text-slate-500 hover:bg-white/50"
              }`}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setShowPrompt((v) => !v)}
            className="text-[11px] text-slate-500 underline ml-1"
          >
            {showPrompt ? "프롬프트 접기" : "프롬프트"}
          </button>
        </div>
      </div>

      {showPrompt && (
        <textarea
          value={customPrompt}
          onChange={(e) => onCustomPromptChange(e.target.value)}
          rows={6}
          spellCheck={false}
          className="w-full text-xs font-mono border border-slate-300 rounded-lg p-3 bg-white text-slate-700"
        />
      )}

      {/* Theme */}
      <div className="flex flex-col sm:flex-row sm:items-start gap-3">
        <span className="text-sm font-semibold text-slate-700 shrink-0 sm:w-24 pt-2">
          Theme
        </span>
        <div className="flex flex-wrap gap-3">
          {THEME_PRESETS.map((theme) => {
            const selected = themeId === theme.id;
            return (
              <button
                key={theme.id}
                type="button"
                onClick={() => onThemeChange(theme.id)}
                className={`flex flex-col items-center gap-1 rounded-lg px-1.5 py-1.5 transition ${
                  selected ? "bg-white ring-1 ring-slate-300 shadow-sm" : "hover:bg-white/40"
                }`}
              >
                <div
                  className="w-12 h-12 rounded-lg flex items-center justify-center text-xl font-semibold"
                  style={{
                    backgroundColor: theme.background,
                    color: theme.text,
                    border: `1px solid ${theme.tileBorder || "#e2e8f0"}`,
                  }}
                >
                  A
                </div>
                <span className="text-[10px] text-slate-500 whitespace-nowrap">
                  {theme.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Text size */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <span className="text-sm font-semibold text-slate-700 shrink-0 sm:w-24">
          Text size
        </span>
        <div className="flex items-end gap-5">
          {TEXT_SIZE_OPTIONS.map((opt) => {
            const selected = textSize === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => onTextSizeChange(opt.id)}
                className={`rounded-md px-2.5 py-1 transition ${
                  selected ? "bg-white ring-1 ring-slate-300 shadow-sm" : "hover:bg-white/40"
                }`}
              >
                <span className={`font-medium text-slate-700 ${opt.previewClass}`}>
                  {opt.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
