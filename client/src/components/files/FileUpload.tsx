// 文件上传组件：选择并上传 docx/pdf/xlsx/pptx，展示解析状态
// 上传为异步解析：pending/parsing 状态下自动轮询列表直至 ready/failed；支持删除（联动清理向量库）
// 上传检测：内容完全一致（409）拒绝并提示；相似度 >= 90% 提示可能存在新旧版本，可选择删除旧版本
import { useEffect, useRef, useState } from "react";
import { isAxiosError } from "axios";
import { uploadFile, listFiles, deleteFile, type FileItem } from "../../api/files";

interface Props {
  files: FileItem[];
  onFilesChange: (files: FileItem[]) => void;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "排队中",
  parsing: "解析中",
  ready: "就绪",
  failed: "失败",
};

export function FileUpload({ files, onFilesChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // 有 pending/parsing 文件时，每 2s 轮询一次列表
  useEffect(() => {
    const inflight = files.some((f) => f.parse_status === "pending" || f.parse_status === "parsing");
    if (!inflight) return;
    const timer = setInterval(async () => {
      try {
        onFilesChange(await listFiles());
      } catch {
        /* 轮询失败静默，下轮重试 */
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [files, onFilesChange]);

  // 相似文件提示：询问是否删除旧版本（错误消息拼接，不覆盖已有提示）
  async function handleSimilarWarning(uploaded: FileItem) {
    if (!uploaded.similar_file_id || !uploaded.similar_to) return;
    const pct = Math.round((uploaded.similarity ?? 0) * 100);
    const remove = window.confirm(
      `检测到「${uploaded.file_name}」与已有文件「${uploaded.similar_to}」内容相似度约 ${pct}%，\n可能存在新旧版本。是否删除旧版本「${uploaded.similar_to}」？\n（删除将同步清理其向量数据，不可恢复）`
    );
    if (!remove) return;
    try {
      await deleteFile(uploaded.similar_file_id);
    } catch {
      setErr((prev) => (prev ? `${prev}；` : "") + `旧版本「${uploaded.similar_to}」删除失败，可稍后手动删除`);
    }
  }

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? []);
    if (selected.length === 0) return;
    setBusy(true);
    setErr(null);
    const failed: string[] = [];
    const similarHits: FileItem[] = [];
    try {
      // 循环内只做上传：window.confirm 会同步阻塞，不能放在循环里，否则批量上传被弹窗卡住
      for (const file of selected) {
        try {
          const uploaded = await uploadFile(file); // 接口立即返回 pending，解析在后台进行
          if (uploaded.similar_file_id && uploaded.similar_to) {
            similarHits.push(uploaded);
          }
        } catch (err) {
          if (isAxiosError(err) && err.response?.status === 409) {
            // 内容完全一致：显示后端返回的具体原因
            failed.push(`${file.name}（${(err.response.data as { detail?: string })?.detail ?? "内容重复"}）`);
          } else {
            failed.push(file.name);
          }
        }
      }
      onFilesChange(await listFiles());
      if (failed.length > 0) {
        setErr(`以下 ${failed.length} 个文件未上传：${failed.join("、")}`);
      }
      // 全部上传完成后，统一处理相似文件确认（此时弹窗不再阻塞上传）
      for (const hit of similarHits) {
        await handleSimilarWarning(hit);
      }
      if (similarHits.length > 0) {
        onFilesChange(await listFiles()); // 可能删除了旧版本，再刷新一次
      }
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleDelete(f: FileItem) {
    if (!window.confirm(`确定删除「${f.file_name}」？\n将同步删除其向量数据，不可恢复。`)) return;
    try {
      await deleteFile(f.id);
      onFilesChange(await listFiles());
    } catch {
      setErr("删除失败，请重试");
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".docx,.pdf,.xlsx,.pptx"
          onChange={handleChange}
          className="block w-full text-sm text-gray-500 file:mr-3 file:rounded file:border-0 file:bg-brand-700 file:px-3 file:py-1.5 file:text-sm file:text-white"
          disabled={busy}
        />
        {busy && <span className="text-xs text-gray-400">批量上传中…</span>}
      </div>
      {err && <div className="text-xs text-red-600">{err}</div>}
      {files.length > 0 && (
        <ul className="max-h-40 space-y-1 overflow-auto text-xs">
          {files.map((f) => (
            <li key={f.id} className="group flex items-center justify-between rounded bg-gray-100 px-2 py-1">
              <span className="truncate">
                📄 {f.file_name}
                <span className="ml-1 text-gray-400">（{f.chunk_count} chunks）</span>
              </span>
              <span className="flex items-center gap-1">
                <span
                  className={`rounded px-1.5 text-[10px] ${
                    f.parse_status === "ready"
                      ? "bg-green-100 text-green-700"
                      : f.parse_status === "failed"
                      ? "bg-red-100 text-red-600"
                      : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {STATUS_LABEL[f.parse_status] ?? f.parse_status}
                </span>
                <button
                  title="删除文件（含向量数据）"
                  onClick={() => handleDelete(f)}
                  className="hidden rounded px-1 text-gray-400 hover:bg-red-50 hover:text-red-600 group-hover:inline"
                >
                  🗑
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
