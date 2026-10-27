// 文件 API
import client from "./client";

export interface FileItem {
  id: number;
  file_name: string;
  file_type: string;
  size_bytes: number;
  parse_status: string;
  chunk_count: number;
  created_at: string;
  // 上传时命中相似旧文件（相似度 >= 90%）时由后端返回
  similar_file_id?: number | null;
  similar_to?: string | null;
  similarity?: number | null;
}

export async function uploadFile(file: File): Promise<FileItem> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<FileItem>("/files/upload", form);
  return data;
}

export async function listFiles(): Promise<FileItem[]> {
  const { data } = await client.get<{ items: FileItem[] }>("/files");
  return data.items;
}

export async function deleteFile(id: number): Promise<void> {
  await client.delete(`/files/${id}`);
}

// 拉取原文 Blob（用于 PDF.js 预览，走 axios 自动带 JWT + 401 刷新）
export async function fetchFileBlob(id: number): Promise<Blob> {
  const { data } = await client.get(`/files/${id}/raw`, { responseType: "blob" });
  return data as Blob;
}

// 拉取文本预览（用于 docx/xlsx/pptx 等非 PDF 格式在线查看）
export async function fetchFilePreview(id: number): Promise<{ file_name: string; text: string }> {
  const { data } = await client.get<{ file_name: string; text: string }>(`/files/${id}/preview`);
  return data;
}
