"use client";

import type { JobResultResponse, MatchedScript, PageResult } from "@/lib/api";

/**
 * 인쇄(브라우저 → PDF로 저장) 전용 뷰.
 *
 * 구성
 *   표지          — 차시 / 제목 / 교수님 이름을 세로 가운데 정렬
 *   슬라이드 n장   — 첫 페이지 상단에 강의록을 판면 가로폭 꽉 차게,
 *                   그 아래부터 핵심 정리·교수님 설명이 이어짐 (장당 2페이지 고정)
 *   부록          — 전체 정리본, 퀴즈 (데이터가 있을 때만)
 *
 * 서체: 영문·숫자 Helvetica + 한글 명조(Noto Serif KR).
 * 여백·2페이지 고정은 globals.css 의 @media print 에서 관리한다.
 */

export interface CoverInfo {
  session: string;
  title: string;
  professor: string;
}

interface PrintViewProps {
  result: JobResultResponse;
  imageUrlFor: (page: number) => string;
  cover: CoverInfo;
  /** 핵심 정리 박스 배경색 */
  boxColor?: string;
  /** 본문 글씨색 */
  textColor?: string;
}

/** 키워드를 노란 배경으로 강조. 인쇄 시 빨간 글씨보다 눈이 덜 피로하다. */
function withHighlights(text: string, keywords: string[]) {
  if (!keywords.length) return text;
  const pattern = new RegExp(
    `(${keywords
      .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|")})`,
    "g"
  );
  return text.split(pattern).map((part, i) =>
    keywords.includes(part) ? (
      <mark key={i} className="bg-amber-200/70 text-inherit px-0.5 rounded-sm">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="mb-2.5 font-sans text-[9px] font-semibold uppercase tracking-[0.14em] opacity-55">
      {children}
    </h2>
  );
}

export type Density = "loose" | "mid" | "tight";

/** 분량에 따른 본문 크기·간격. 가로 한 장을 넘기지 않게 한 단계씩 조인다. */
const DENSITY: Record<Density, { body: string; gap: string }> = {
  loose: { body: "text-[11px] leading-[1.75]", gap: "mb-3.5" },
  mid: { body: "text-[10px] leading-[1.65]", gap: "mb-3" },
  tight: { body: "text-[9px] leading-[1.55]", gap: "mb-2.5" },
};

function ScriptBlock({
  script,
  readability,
  highlight,
  density = "loose",
}: {
  script: MatchedScript;
  readability: boolean;
  highlight: boolean;
  density?: Density;
}) {
  const base = script.corrected_text || script.raw_text;
  const body = readability && script.clean_text ? script.clean_text : base;
  if (!body?.trim()) return null;

  const d = DENSITY[density];

  return (
    <div className={`${d.gap} last:mb-0`}>
      <p className="mb-0.5 font-sans text-[8px] tracking-wide opacity-40 tabular-nums">
        {script.start_time} – {script.end_time}
      </p>
      <p className={`whitespace-pre-wrap ${d.body}`}>
        {highlight ? withHighlights(body, script.highlights) : body}
      </p>
    </div>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="mb-2 flex gap-2 leading-[1.7] text-[11px] last:mb-0">
      <span className="mt-[0.65em] h-[3px] w-[3px] shrink-0 rounded-full bg-current opacity-45" />
      <span>{children}</span>
    </li>
  );
}

function SlideSection({
  page,
  total,
  imageUrl,
  readability,
  highlight,
  boxColor,
}: {
  page: PageResult;
  total: number;
  imageUrl: string;
  readability: boolean;
  highlight: boolean;
  boxColor?: string;
}) {
  const summary = page.summary || [];
  const scripts = page.matched_scripts || [];
  // 분량이 많은 슬라이드는 글자를 한 단계씩 낮춰 가로 한 장 안에 담는다
  const charCount = scripts.reduce(
    (n, s) =>
      n + (s.clean_text || s.corrected_text || s.raw_text || '').length,
    0
  );
  const density: Density =
    charCount > 1500 ? "tight" : charCount > 850 ? "mid" : "loose";

  return (
    // 가로 한 장 = 왼쪽 6(강의록 + 핵심정리) / 오른쪽 4(교수님 설명)
    <article className="print-slide break-after-page last:break-after-auto grid w-full grid-cols-[60fr_40fr] gap-[7mm]">
      {/* 왼쪽 6 */}
      <div className="flex min-w-0 flex-col gap-[5mm]">
        {imageUrl && (
          <figure className="m-0 break-inside-avoid">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={imageUrl}
              alt={`슬라이드 ${page.page}`}
              className="block w-full border border-black/10"
            />
          </figure>
        )}

        <p className="font-sans text-[9px] uppercase tracking-[0.14em] opacity-45">
          슬라이드 {page.page} / {total}
        </p>

        {summary.length > 0 && (
          <section
            className="flex-1 rounded-lg px-[7mm] py-[6mm]"
            style={boxColor ? { backgroundColor: boxColor } : undefined}
          >
            <SectionLabel>핵심 정리</SectionLabel>
            <ul>
              {summary.map((raw, i) => (
                <Bullet key={i}>{raw.replace(/^[-•*]\s*/, "")}</Bullet>
              ))}
            </ul>
          </section>
        )}
      </div>

      {/* 오른쪽 4 — 교수님 설명 */}
      <div
        className="min-w-0 overflow-hidden rounded-lg px-[6mm] py-[5mm]"
        style={boxColor ? { backgroundColor: boxColor } : undefined}
      >
        {scripts.length > 0 ? (
          <>
            <SectionLabel>교수님 설명</SectionLabel>
            {scripts.map((s) => (
              <ScriptBlock
                key={s.chunk_id}
                script={s}
                readability={readability}
                highlight={highlight}
                density={density}
              />
            ))}
          </>
        ) : (
          <p className="font-sans text-[11px] opacity-45">
            이 슬라이드에는 매칭된 설명이 없습니다.
          </p>
        )}
      </div>
    </article>
  );
}

/** 부록 0 — 슬라이드별 핵심 정리를 한데 모은 정리본 (추가 비용 없이 만들어진다) */
function SummaryDigest({
  pages,
  boxColor,
}: {
  pages: PageResult[];
  boxColor?: string;
}) {
  const withSummary = pages.filter((p) => (p.summary || []).length > 0);
  if (withSummary.length === 0) return null;

  return (
    <article className="print-slide print-flow break-after-page last:break-after-auto w-full">
      <h1 className="mb-1 text-[22px] font-semibold">정리본</h1>
      <p className="mb-6 font-sans text-[9px] uppercase tracking-[0.14em] opacity-45">
        슬라이드 핵심 정리 모아 보기
      </p>
      <div
        className="rounded-lg px-[9mm] py-[8mm] [column-gap:12mm] [columns:2]"
        style={boxColor ? { backgroundColor: boxColor } : undefined}
      >
        {withSummary.map((p) => (
          <section key={p.page} className="mb-5 break-inside-avoid">
            <p className="mb-1.5 font-sans text-[9px] uppercase tracking-[0.12em] opacity-45">
              슬라이드 {p.page}
            </p>
            <ul>
              {(p.summary || []).map((raw, i) => (
                <Bullet key={i}>{raw.replace(/^[-•*]\s*/, "")}</Bullet>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </article>
  );
}

/** 부록 1 — 전체 정리본 */
function LectureNoteAppendix({
  doc,
}: {
  doc: NonNullable<JobResultResponse["lecture_document"]>;
}) {
  const concept = doc.concept_structure || [];
  const renderNode = (
    node: (typeof concept)[number],
    depth = 0,
    key = "0"
  ): React.ReactNode => (
    <div
      key={key}
      className={depth > 0 ? "ml-4 border-l border-slate-200 pl-4 mt-2" : "mb-4"}
    >
      {node.heading && (
        <p className="mb-1.5 font-semibold text-[15px]">{node.heading}</p>
      )}
      {node.items?.map((item, i) => (
        <p key={i} className="mb-1 pl-3 text-[14px] leading-[1.8]">
          {item.replace(/\*\*/g, "")}
        </p>
      ))}
      {node.children?.map((child, i) =>
        renderNode(child, depth + 1, `${key}-${i}`)
      )}
    </div>
  );

  return (
    <article className="break-after-page last:break-after-auto w-full pb-8 pt-4">
      <h1 className="mb-1 text-2xl font-semibold">전체 정리본</h1>
      <p className="mb-8 font-sans text-[11px] uppercase tracking-[0.14em] text-slate-400">
        부록
      </p>

      {doc.key_summary?.length > 0 && (
        <section className="mb-8">
          <SectionLabel>핵심 요약</SectionLabel>
          <ul>
            {doc.key_summary.map((item, i) => (
              <Bullet key={i}>{item.replace(/\*\*/g, "")}</Bullet>
            ))}
          </ul>
        </section>
      )}

      {concept.length > 0 && (
        <section className="mb-8">
          <SectionLabel>개념 구조</SectionLabel>
          {concept.map((node, i) => renderNode(node, 0, String(i)))}
        </section>
      )}

      {doc.comparisons?.length > 0 && (
        <section className="mb-8">
          <SectionLabel>표 · 비교</SectionLabel>
          {doc.comparisons.map((t, ti) => (
            <div key={ti} className="mb-5 break-inside-avoid">
              {t.title && (
                <p className="mb-1.5 text-[14px] font-semibold">{t.title}</p>
              )}
              <table className="w-full border-collapse text-[13px]">
                {t.columns?.length > 0 && (
                  <thead>
                    <tr>
                      {t.columns.map((c, i) => (
                        <th
                          key={i}
                          className="border-b border-slate-300 py-1.5 pr-3 text-left font-semibold"
                        >
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                )}
                <tbody>
                  {t.rows.map((row, ri) => (
                    <tr key={ri}>
                      {row.map((cell, ci) => (
                        <td
                          key={ci}
                          className="border-b border-slate-100 py-1.5 pr-3 align-top leading-[1.7]"
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      )}

      {doc.professor_highlights?.length > 0 && (
        <section className="mb-8">
          <SectionLabel>교수님이 강조한 부분</SectionLabel>
          {doc.professor_highlights.map((h, i) => (
            <div key={i} className="mb-4 text-[14px] leading-[1.8]">
              <p className="italic text-slate-600">&ldquo;{h.quote}&rdquo;</p>
              <p className="mt-1">{h.explanation}</p>
            </div>
          ))}
        </section>
      )}

      {doc.confusing_points?.length > 0 && (
        <section>
          <SectionLabel>헷갈리기 쉬운 부분</SectionLabel>
          <ul>
            {doc.confusing_points.map((p, i) => (
              <Bullet key={i}>{p}</Bullet>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}

/** 부록 2 — 퀴즈 (문제 모아 보기 + 정답) */
function QuizAppendix({ pages }: { pages: PageResult[] }) {
  const items = pages.flatMap((p) =>
    (p.quiz || []).map((q) => ({ ...q, page: p.page }))
  );
  if (items.length === 0) return null;

  return (
    <>
      <article className="break-after-page last:break-after-auto w-full pb-8 pt-4">
        <h1 className="mb-1 text-2xl font-semibold">퀴즈</h1>
        <p className="mb-8 font-sans text-[11px] uppercase tracking-[0.14em] text-slate-400">
          부록 · 정답은 다음 장
        </p>
        <ol>
          {items.map((q, i) => (
            <li key={i} className="mb-6 break-inside-avoid text-[14.5px] leading-[1.8]">
              <p>
                <span className="font-sans text-[12px] text-slate-400 tabular-nums">
                  {i + 1}.
                </span>{" "}
                {q.question}
                <span className="ml-2 font-sans text-[10px] text-slate-300">
                  슬라이드 {q.page}
                </span>
              </p>
              <div className="mt-2 h-px w-full bg-slate-100" />
              <div className="mt-4 h-px w-full bg-slate-100" />
            </li>
          ))}
        </ol>
      </article>

      <article className="break-after-page last:break-after-auto w-full pb-8 pt-4">
        <h1 className="mb-8 text-2xl font-semibold">퀴즈 정답</h1>
        <ol>
          {items.map((q, i) => (
            <li key={i} className="mb-3 text-[14px] leading-[1.8]">
              <span className="font-sans text-[12px] text-slate-400 tabular-nums">
                {i + 1}.
              </span>{" "}
              {q.answer}
            </li>
          ))}
        </ol>
      </article>
    </>
  );
}

export default function PrintView({
  result,
  imageUrlFor,
  cover,
  boxColor,
  textColor,
}: PrintViewProps) {
  const pages = result.pages || [];
  const doc = result.lecture_document;
  const hasQuiz = pages.some((p) => (p.quiz || []).length > 0);
  const title = cover.title || doc?.title || "강의 정리본";

  return (
    <div
      className="font-reading"
      style={{ color: textColor || "#0f172a" }}
    >
      {/* ── 표지 ── */}
      <div className="break-after-page flex h-[174mm] w-full flex-col items-center justify-center text-center">
        {cover.session && (
          <p className="mb-10 font-sans text-[12px] uppercase tracking-[0.3em] opacity-50">
            {cover.session}
          </p>
        )}
        <div className="mb-8 h-px w-16 bg-current opacity-30" />
        <h1 className="max-w-[24em] text-[30px] font-semibold leading-[1.5]">
          {title}
        </h1>
        {doc?.subtitle && (
          <p className="mt-5 max-w-[26em] text-[14px] leading-[1.9] opacity-60">
            {doc.subtitle}
          </p>
        )}
        <div className="mt-8 h-px w-16 bg-current opacity-30" />
        {cover.professor && (
          <p className="mt-10 font-sans text-[13px] tracking-[0.12em] opacity-65">
            {cover.professor}
          </p>
        )}
      </div>

      {/* ── 본문 ── */}
      {pages.map((page) => (
        <SlideSection
          key={page.page}
          page={page}
          total={pages.length}
          imageUrl={imageUrlFor(page.page)}
          readability={!!result.readability_mode}
          highlight={!!result.highlight_mode}
          boxColor={boxColor}
        />
      ))}

      {/* ── 부록 ── */}
      <SummaryDigest pages={pages} boxColor={boxColor} />
      {doc?.title && <LectureNoteAppendix doc={doc} />}
      {hasQuiz && <QuizAppendix pages={pages} />}
    </div>
  );
}
