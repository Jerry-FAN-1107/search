// 文件在线查看器：点击文件名/引用角标后弹出
// PDF 走 react-pdf 渲染（支持页码跳转）；docx/xlsx/pptx 走后端文本提取接口展示
import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { fetchFileBlob, fetchFilePreview } from "../api/files";

// Vite 方式配置 PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

export interface PdfViewTarget {
  fileId: number;
  page: number;
  fileName: string;
}

export function PdfViewer({ target, onClose }: { target: PdfViewTarget; onClose: () => void }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(target.page);
  const [error, setError] = useState<string | null>(null);
  const [textPreview, setTextPreview] = useState<string | null>(null);
  const isPdf = target.fileName.toLowerCase().endsWith(".pdf");

  useEffect(() => {
    setPage(target.page);
    setError(null);
    setTextPreview(null);
    let cancelled = false;
    if (!isPdf) {
      // 非 PDF：拉取后端提取的文本做在线预览
      fetchFilePreview(target.fileId)
        .then((d) => { if (!cancelled) setTextPreview(d.text || "（未提取到文本内容）"); })
        .catch((e) => { if (!cancelled) setError(e?.response?.data?.detail || "预览加载失败"); });
      return () => { cancelled = true; };
    }
    let url: string | null = null;
    fetchFileBlob(target.fileId)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch(() => setError("原文加载失败（无权限或文件已删除）"));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
      setBlobUrl(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target.fileId, target.page]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="flex max-h-[90vh] w-[820px] max-w-[92vw] flex-col rounded-xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
          <div className="truncate text-sm font-medium">
            📄 {target.fileName}
            {isPdf && numPages > 0 && (
              <span className="ml-2 text-xs text-gray-400">
                第 {page} / {numPages} 页
              </span>
            )}
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">✕</button>
        </div>

        <div className="flex-1 overflow-auto bg-gray-100 p-4">
          {!isPdf ? (
            error ? (
              <div className="pt-16 text-center text-sm text-red-500">{error}</div>
            ) : textPreview === null ? (
              <div className="pt-16 text-center text-sm text-gray-400">加载中…</div>
            ) : (
              <div className="mx-auto max-w-3xl rounded-lg bg-white p-6 shadow-sm">
                <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-gray-800">{textPreview}</pre>
              </div>
            )
          ) : error ? (
            <div className="pt-16 text-center text-sm text-red-500">{error}</div>
          ) : !blobUrl ? (
            <div className="pt-16 text-center text-sm text-gray-400">加载中…</div>
          ) : (
            <Document
              file={blobUrl}
              onLoadSuccess={({ numPages }) => setNumPages(numPages)}
              onLoadError={() => setError("PDF 解析失败")}
              loading={<div className="pt-16 text-center text-sm text-gray-400">解析中…</div>}
            >
              <div className="flex justify-center">
                <Page pageNumber={Math.min(page, numPages || 1)} width={720} />
              </div>
            </Document>
          )}
        </div>

        {isPdf && numPages > 1 && (
          <div className="flex items-center justify-center gap-3 border-t border-gray-200 py-2 text-sm">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded border border-gray-300 px-3 py-1 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              disabled={page >= numPages}
              onClick={() => setPage((p) => Math.min(numPages, p + 1))}
              className="rounded border border-gray-300 px-3 py-1 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
