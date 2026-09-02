"use client";

import type { LectureDocument } from "@/lib/api";

interface FullLectureNoteViewProps {
  document: LectureDocument;
  onSlideRef?: (page: number) => void;
}

function SectionTitle({
  icon,
  children,
}: {
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 mb-3 mt-6 first:mt-0">
      <span className="text-base">{icon}</span>
      {children}
    </h3>
  );
}

function renderBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function ConceptBlock({
  node,
  depth = 0,
}: {
  node: LectureDocument["concept_structure"][0];
  depth?: number;
}) {
  return (
    <div className={depth > 0 ? "ml-4 border-l-2 border-slate-200 pl-4 mt-2" : "mb-4"}>
      {node.heading && (
        <p className="font-semibold text-slate-800 mb-1.5">{node.heading}</p>
      )}
      {node.items?.map((item, i) => (
        <p key={i} className="text-sm text-slate-700 leading-relaxed pl-3 relative before:content-['▪'] before:absolute before:left-0 before:text-slate-400 mb-1">
          {renderBold(item)}
        </p>
      ))}
      {node.callout_question && (
        <div className="mt-2 px-3 py-2 bg-emerald-50 border border-emerald-100 rounded-lg text-sm text-emerald-800">
          {node.callout_question}
        </div>
      )}
      {node.children?.map((child, i) => (
        <ConceptBlock key={i} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

export default function FullLectureNoteView({
  document: doc,
  onSlideRef,
}: FullLectureNoteViewProps) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      {/* 헤더 */}
      <div className="px-8 pt-8 pb-6 border-b border-slate-100">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 leading-tight">
          {doc.title}
        </h1>
        <p className="text-sm text-slate-400 mt-2">{doc.subtitle}</p>
      </div>

      <div className="px-8 py-6 grid grid-cols-1 lg:grid-cols-2 gap-x-10 gap-y-2">
        {/* 왼쪽 열 */}
        <div>
          {doc.key_summary.length > 0 && (
            <section>
              <SectionTitle icon="🎯">핵심 요약</SectionTitle>
              <ul className="space-y-2">
                {doc.key_summary.map((item, i) => (
                  <li
                    key={i}
                    className="text-sm text-slate-700 leading-relaxed flex gap-2"
                  >
                    <span className="text-brand-500 shrink-0">•</span>
                    <span>{renderBold(item)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {doc.concept_structure.length > 0 && (
            <section>
              <SectionTitle icon="🧠">개념 구조</SectionTitle>
              {doc.concept_structure.map((node, i) => (
                <ConceptBlock key={i} node={node} />
              ))}
            </section>
          )}
        </div>

        {/* 오른쪽 열 */}
        <div>
          {doc.comparisons.length > 0 && (
            <section>
              <SectionTitle icon="📊">표 · 비교 · 정리</SectionTitle>
              {doc.comparisons.map((table, ti) => (
                <div key={ti} className="mb-6">
                  <div className="flex items-center justify-between gap-2 mb-2">
                    {table.title && (
                      <p className="text-sm font-semibold text-slate-700">
                        {table.title}
                      </p>
                    )}
                    {table.slide_ref && onSlideRef && (
                      <button
                        onClick={() => onSlideRef(table.slide_ref!)}
                        className="text-xs text-brand-600 hover:underline shrink-0"
                      >
                        슬라이드 {table.slide_ref} 참고 →
                      </button>
                    )}
                  </div>
                  <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
                    <table className="w-full text-sm">
                      {table.columns.length > 0 && (
                        <thead>
                          <tr className="bg-slate-100">
                            {table.columns.map((col, ci) => (
                              <th
                                key={ci}
                                className="px-3 py-2.5 text-left font-semibold text-slate-700 border-b border-slate-200"
                              >
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                      )}
                      <tbody>
                        {table.rows.map((row, ri) => (
                          <tr
                            key={ri}
                            className={`border-b border-slate-100 last:border-0 ${
                              ri % 2 === 1 ? "bg-slate-50/60" : "bg-white"
                            }`}
                          >
                            {row.map((cell, ci) => (
                              <td
                                key={ci}
                                className={`px-3 py-2.5 text-slate-700 ${
                                  ci === 0 ? "font-medium text-slate-800" : ""
                                }`}
                              >
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </section>
          )}

          {doc.professor_highlights.length > 0 && (
            <section>
              <SectionTitle icon="✏️">교수 강조 구간</SectionTitle>
              <div className="space-y-3">
                {doc.professor_highlights.map((h, i) => (
                  <div key={i} className="text-sm leading-relaxed">
                    <p className="italic text-slate-600">&ldquo;{h.quote}&rdquo;</p>
                    <p className="text-slate-800 mt-1">{h.explanation}</p>
                    {h.slide_ref && onSlideRef && (
                      <button
                        onClick={() => onSlideRef(h.slide_ref!)}
                        className="text-xs text-brand-600 hover:underline mt-1"
                      >
                        → 슬라이드 {h.slide_ref} 보기
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {doc.exam_questions.length > 0 && (
            <section>
              <SectionTitle icon="❓">시험에서 이렇게 나온다</SectionTitle>
              <ul className="space-y-2">
                {doc.exam_questions.map((q, i) => (
                  <li key={i} className="text-sm text-slate-700 flex gap-2">
                    <span className="text-slate-400 shrink-0">{i + 1}.</span>
                    <span>{q}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {doc.confusing_points.length > 0 && (
            <section>
              <SectionTitle icon="⚠️">헷갈리기 쉬운 포인트</SectionTitle>
              <ul className="space-y-2">
                {doc.confusing_points.map((p, i) => (
                  <li key={i} className="text-sm text-slate-700 flex gap-2">
                    <span className="text-amber-500 shrink-0">△</span>
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
