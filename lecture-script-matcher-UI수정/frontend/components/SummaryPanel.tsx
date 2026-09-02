"use client";

interface SummaryPanelProps {
  summary: string[];
  hasScripts: boolean;
  title?: string;
  subtitle?: string;
  /** 상단 '박스색' 선택값 */
  boxColor?: string;
  /** 상단 '글씨색' 선택값 */
  textColor?: string;
}

function renderPoint(point: string, idx: number) {
  const important = point.includes("⭐") || point.includes("중요");
  const clean = point.replace(/^[-•*]\s*/, "");
  const isExample = clean.startsWith("예)");
  return (
    <li
      key={idx}
      // 색은 부모(박스)에서 상속받는다 — 상단 '글씨색' 선택이 먹도록
      className={`flex gap-2.5 font-reading leading-[1.8] ${
        important ? "font-semibold" : ""
      } ${isExample ? "pl-2 border-l-2 border-slate-200 py-1 pr-2" : ""}`}
    >
      <span className="mt-[0.7em] shrink-0 w-[3px] h-[3px] rounded-full bg-slate-400" />
      <span>
        {isExample && (
          <span className="font-sans text-[10px] uppercase tracking-wider text-slate-400 mr-1.5">
            예시
          </span>
        )}
        {clean}
      </span>
    </li>
  );
}

export default function SummaryPanel({
  summary,
  hasScripts,
  title = "핵심 정리",
  subtitle = "교수님 설명·예시 요약",
  boxColor,
  textColor,
}: SummaryPanelProps) {
  return (
    <div className="flex flex-col h-full">
      <h2 className="mb-3 px-1 flex items-baseline gap-2 font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        <span>{title}</span>
        <span className="text-[10px] font-normal normal-case tracking-normal text-slate-400">
          {subtitle}
        </span>
      </h2>
      <div
        className="flex-1 rounded-xl border border-slate-200 px-6 py-6 overflow-y-auto min-h-[500px]"
        style={{
          backgroundColor: boxColor || "#faf9f6",
          color: textColor || undefined,
        }}
      >
        {summary && summary.length > 0 ? (
          <ul className="space-y-4">{summary.map(renderPoint)}</ul>
        ) : (
          <div className="text-center py-12 px-4">
            <p className="text-3xl mb-3">📝</p>
            <p className="text-slate-500 font-medium">정리할 내용이 없습니다</p>
            <p className="text-slate-400 text-sm mt-2 leading-relaxed">
              {hasScripts
                ? "요약 모드가 꺼져 있거나, 이 슬라이드에서 정리할 핵심 발화를 찾지 못했습니다."
                : "이 슬라이드에는 매칭된 교수님 발화가 없습니다."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
