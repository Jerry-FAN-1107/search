// SSE 事件类型定义（与后端 schemas/chat.py 对齐）
export type SourceType = "file" | "web";

export interface Citation {
  ref: number;
  file_name: string;
  location: string;
  source_type: SourceType;
  title: string;
  url: string;
  file_id?: number | null; // 文件来源时携带，用于点击角标打开原文
}

export interface ThinkingData {
  reasoning: string;
}
export interface TokenData {
  text: string;
}
export interface ToolStatusData {
  tool: string;
  message: string;
}
export interface CitationData extends Citation {}
export interface HitlPendingData {
  thread_id: string;
  action: string;
  context: Record<string, unknown>;
}
export interface DoneData {
  citations: Citation[];
  answer: string;
}
export interface ErrorData {
  message: string;
}

export type ChatEventData =
  | { event: "thinking"; data: ThinkingData }
  | { event: "token"; data: TokenData }
  | { event: "tool_status"; data: ToolStatusData }
  | { event: "citation"; data: CitationData }
  | { event: "hitl_pending"; data: HitlPendingData }
  | { event: "done"; data: DoneData }
  | { event: "error"; data: ErrorData };

export type HitlDecision = "approve" | "edit" | "reject";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  isStreaming?: boolean;
  hasUncited?: boolean;
}