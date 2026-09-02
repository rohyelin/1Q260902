"use client";

interface PdfPreviewProps {
  imageUrl: string;
  pageNumber: number;
  totalPages: number;
}

export default function PdfPreview({ imageUrl, pageNumber, totalPages }: PdfPreviewProps) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3 px-1">
        <h2 className="font-sans text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          강의록
        </h2>
        <span className="font-sans text-[10px] text-slate-400 tabular-nums">
          {pageNumber} / {totalPages}
        </span>
      </div>
      <div className="flex-1 bg-slate-100 rounded-xl overflow-hidden border border-slate-200 flex items-start justify-center p-4 min-h-[500px]">
        {imageUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={imageUrl}
            alt={`Page ${pageNumber}`}
            className="max-w-full h-auto shadow-lg rounded"
          />
        ) : (
          <p className="text-sm text-slate-400 text-center px-6">
            데모 모드입니다. 슬라이드 이미지는 실제 PDF 업로드 후 표시됩니다.
          </p>
        )}
      </div>
    </div>
  );
}
