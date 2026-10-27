// 问答主界面：侧边文件区（宽度可拖拽）+ 思考面板 + 正文 + HITL 卡片 + 文件在线预览
import { useCallback, useEffect, useState } from "react";
import { listFiles, type FileItem } from "../api/files";
import { FileUpload } from "../components/files/FileUpload";
import { ChatMessageView } from "../components/chat/ChatMessage";
import { ThinkingPanel } from "../components/chat/ThinkingPanel";
import { ToolStatus } from "../components/chat/ToolStatus";
import { HitlCard } from "../components/chat/HitlCard";
import { PdfViewer, type PdfViewTarget } from "../components/PdfViewer";
import { useChat } from "../hooks/useChat";
import { useAuth } from "../store/auth";
import type { Citation } from "../types/chat";

export function Chat() {
  const { messages, thinking, thinkingOpen, setThinkingOpen, toolStatus, hitl, streaming, error, send, decide, stop } = useChat();
  const { email, logout } = useAuth();
  const [files, setFiles] = useState<FileItem[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [input, setInput] = useState("");
  const [pdfTarget, setPdfTarget] = useState<PdfViewTarget | null>(null);
  // 知识库面板宽度（拖拽可调，200~560px）
  const [asideWidth, setAsideWidth] = useState(288);

  useEffect(() => {
    listFiles().then(setFiles).catch(() => {});
  }, []);

  const handleFilesChange = useCallback((f: FileItem[]) => setFiles(f), []);

  // 点击引用角标：文件来源 -> 打开原文并跳转到对应页码（PDF）
  const handleCiteClick = useCallback((c: Citation) => {
    if (c.source_type !== "file" || !c.file_id) return;
    const m = /page=(\d+)/.exec(c.location || "");
    setPdfTarget({ fileId: c.file_id, page: m ? parseInt(m[1], 10) : 1, fileName: c.file_name });
  }, []);

  // 点击文件名：在线预览（PDF 走渲染，docx/xlsx/pptx 走文本提取）
  const handleFileClick = useCallback((f: FileItem) => {
    setPdfTarget({ fileId: f.id, page: 1, fileName: f.file_name });
  }, []);

  // 拖拽分隔条调整知识库面板宽度
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = asideWidth;
    function onMove(ev: MouseEvent) {
      setAsideWidth(Math.min(560, Math.max(200, startW + ev.clientX - startX)));
    }
    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [asideWidth]);

  function toggleFile(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="flex h-screen">
      <aside style={{ width: asideWidth }} className="flex shrink-0 flex-col bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold">知识库</span>
        </div>
        <FileUpload files={files} onFilesChange={handleFilesChange} />
        <div className="mt-3 text-xs font-medium text-gray-500">选择检索范围（不选则全部）</div>
        <ul className="mt-1 flex-1 space-y-1 overflow-auto text-xs">
          {files.map((f) => (
            <li key={f.id} className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-gray-50">
              <input type="checkbox" checked={selected.has(f.id)} onChange={() => toggleFile(f.id)} />
              <button
                title="点击在线预览"
                onClick={() => handleFileClick(f)}
                className="min-w-0 flex-1 cursor-pointer truncate text-left text-gray-700 hover:text-brand-700 hover:underline"
              >
                {f.file_name}
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-3 border-t border-gray-200 pt-3 text-xs text-gray-500">
          <div className="mb-1 truncate">{email}</div>
          <button onClick={logout} className="text-red-500 hover:underline">退出登录</button>
        </div>
      </aside>

      {/* 拖拽分隔条：调整知识库 / 咨询窗口宽度 */}
      <div
        onMouseDown={handleDragStart}
        className="w-1 shrink-0 cursor-col-resize bg-gray-200 transition-colors hover:bg-brand-600"
        title="拖拽调整宽度"
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2">
          <h2 className="text-sm font-medium">企业信息咨询</h2>
          <span className="text-xs text-gray-400">引用角标：📄文件(可点击看原文) ／ 🌐网页</span>
        </div>

        <div className="flex-1 space-y-4 overflow-auto px-4 py-4">
          {messages.length === 0 && (
            <div className="pt-20 text-center text-sm text-gray-400">
              上传文档后，向我提问，答案将带来源角标。
            </div>
          )}
          {thinking && <ThinkingPanel thinking={thinking} open={thinkingOpen} onToggle={setThinkingOpen} />}
          {toolStatus && <ToolStatus status={toolStatus} />}
          {hitl && <HitlCard hitl={hitl} onDecide={decide} />}
          {error && <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>}
          {messages.map((m) => (
            <ChatMessageView key={m.id} message={m} onCiteClick={handleCiteClick} />
          ))}
        </div>

        {pdfTarget && <PdfViewer target={pdfTarget} onClose={() => setPdfTarget(null)} />}

        <div className="border-t border-gray-200 p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input, selected.size ? [...selected] : undefined);
                  setInput("");
                }
              }}
              rows={2}
              placeholder="输入问题，Enter 发送"
              className="flex-1 resize-none rounded-lg border border-gray-300 p-2 text-sm"
            />
            {streaming ? (
              <button onClick={stop} className="rounded-lg bg-gray-500 px-4 py-2 text-sm text-white">停止</button>
            ) : (
              <button
                onClick={() => { send(input, selected.size ? [...selected] : undefined); setInput(""); }}
                disabled={!input.trim()}
                className="rounded-lg bg-brand-700 px-4 py-2 text-sm text-white disabled:opacity-50"
              >
                发送
              </button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
