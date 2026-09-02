"use client";

import { AccentButton } from "@/components/UploadPanel";

interface SettingsSidebarProps {
  open: boolean;
  onToggle: () => void;
  readabilityMode: boolean;
  highlightMode: boolean;
  onReadabilityChange: (v: boolean) => void;
  onHighlightChange: (v: boolean) => void;
}

function Toggle({
  on,
  onChange,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!on)}
      className={`relative w-12 h-6 rounded-full border border-black/15 transition-colors ${
        on ? "bg-[#C4A55F]" : "bg-[#e8e8e4]"
      }`}
      aria-pressed={on}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white border border-black/10 shadow transition-transform ${
          on ? "translate-x-6" : "translate-x-0"
        }`}
      />
      <span className="sr-only">{on ? "on" : "off"}</span>
      <span
        className={`absolute inset-0 flex items-center text-[9px] font-medium pointer-events-none ${
          on ? "justify-start pl-1.5 text-white" : "justify-end pr-1.5 text-slate-500"
        }`}
      >
        {on ? "on" : "off"}
      </span>
    </button>
  );
}

function SlidersIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-6 h-6" fill="none" aria-hidden>
      <path d="M4 7h10M18 7h2" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <circle cx="16" cy="7" r="2.2" fill="white" />
      <path d="M4 12h4M10 12h10" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <circle cx="8" cy="12" r="2.2" fill="white" />
      <path d="M4 17h12M20 17h0" stroke="white" strokeWidth="2" strokeLinecap="round" />
      <circle cx="18" cy="17" r="2.2" fill="white" />
    </svg>
  );
}

export default function SettingsSidebar({
  open,
  onToggle,
  readabilityMode,
  highlightMode,
  onReadabilityChange,
  onHighlightChange,
}: SettingsSidebarProps) {
  return (
    <aside className="fixed top-[72px] right-0 z-30 flex flex-col items-end">
      <AccentButton
        onClick={onToggle}
        className="w-12 h-12 flex items-center justify-center rounded-none rounded-l-md !px-0"
        title="settings"
      >
        <SlidersIcon />
      </AccentButton>

      {open && (
        <div className="w-[220px] mr-0 bg-white border border-black/15 border-r-0 shadow-[-4px_6px_20px_rgba(0,0,0,0.08)]">
          <div className="p-4 space-y-5">
            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
                    <span aria-hidden>✏️</span> 가독성 모드
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1 leading-snug">
                    구어체를 읽기 쉬운 문장으로 다듬습니다
                  </p>
                </div>
                <Toggle on={readabilityMode} onChange={onReadabilityChange} />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-800 flex items-center gap-1.5">
                    <span aria-hidden>⭐</span> 중요 하이라이트
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1 leading-snug">
                    핵심 키워드를 강조 표시합니다
                  </p>
                </div>
                <Toggle on={highlightMode} onChange={onHighlightChange} />
              </div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
