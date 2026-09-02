"use client";

import { useEffect, useState } from "react";
import type { QuizItem } from "@/lib/api";

interface QuizPanelProps {
  quiz: QuizItem[];
  hasScripts: boolean;
  pageKey: number;
}

function QuizCard({ item, index }: { item: QuizItem; index: number }) {
  const [revealed, setRevealed] = useState(false);
  const important = item.question.includes("⭐");

  return (
    <div
      className={`rounded-lg border p-4 bg-white ${
        important ? "border-amber-300" : "border-slate-200"
      }`}
    >
      <p className="text-slate-800 leading-relaxed">
        <span className="font-semibold text-brand-600 mr-1.5">Q{index + 1}.</span>
        {item.question}
      </p>
      {item.answer && (
        <div className="mt-3">
          {revealed ? (
            <p className="text-sm text-emerald-800 bg-emerald-50 border border-emerald-100 rounded-md px-3 py-2 leading-relaxed">
              <span className="font-semibold mr-1">정답:</span>
              {item.answer}
            </p>
          ) : (
            <button
              onClick={() => setRevealed(true)}
              className="text-xs px-3 py-1.5 rounded-md border border-slate-200 text-slate-500 hover:bg-slate-50 hover:text-slate-700"
            >
              정답 보기
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function QuizPanel({ quiz, hasScripts, pageKey }: QuizPanelProps) {
  // 페이지 이동 시 정답 공개 상태 초기화를 위해 key 재마운트
  const [mountKey, setMountKey] = useState(pageKey);
  useEffect(() => setMountKey(pageKey), [pageKey]);

  return (
    <div className="flex flex-col h-full">
      <h2 className="text-sm font-semibold text-slate-600 mb-3 px-1 flex items-center gap-2">
        <span>복습 퀴즈</span>
        <span className="text-xs font-normal text-slate-400">
          교수님 설명 기반 문제
        </span>
      </h2>
      <div className="flex-1 rounded-xl border border-brand-100 bg-brand-50/40 p-5 overflow-y-auto min-h-[500px]">
        {quiz && quiz.length > 0 ? (
          <div className="space-y-3" key={mountKey}>
            {quiz.map((item, i) => (
              <QuizCard key={`${mountKey}-${i}`} item={item} index={i} />
            ))}
          </div>
        ) : (
          <div className="text-center py-12 px-4">
            <p className="text-3xl mb-3">❓</p>
            <p className="text-slate-500 font-medium">출제할 문제가 없습니다</p>
            <p className="text-slate-400 text-sm mt-2 leading-relaxed">
              {hasScripts
                ? "이 슬라이드의 발화량이 적어 퀴즈를 만들지 않았습니다."
                : "이 슬라이드에는 매칭된 교수님 발화가 없습니다."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
