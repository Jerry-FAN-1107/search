// 聊天 API：发起问答（POST SSE）与 HITL 决策提交
// 说明：EventSource 仅支持 GET，故用 fetch + ReadableStream 手动解析 SSE。
import type { ChatEventData, HitlDecision } from "../types/chat";
import { API_BASE } from "./client";

export interface AskParams {
  question: string;
  conversation_id?: number | null;
  file_ids?: number[];
  force_web?: boolean;
}

export function ask(
  params: AskParams,
  onEvent: (ev: ChatEventData) => void,
  onError: (msg: string) => void,
  signal?: AbortSignal
): void {
  const token = localStorage.getItem("token");
  fetch(`${API_BASE}/chat/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify(params),
    signal,
  }).then(async (resp) => {
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => "");
      onError(text || `HTTP ${resp.status}`);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const process = () => {
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        parseEventBlock(part, onEvent);
      }
    };

    const loop = async () => {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          process();
        }
        if (buffer.trim()) parseEventBlock(buffer, onEvent);
      } catch (e) {
        if ((e as Error).name !== "AbortError") onError("连接中断");
      }
    };
    loop();
  }).catch((e) => {
    if ((e as Error).name !== "AbortError") onError("请求失败");
  });
}

function parseEventBlock(block: string, onEvent: (ev: ChatEventData) => void) {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }
  onEvent({ event: event as ChatEventData["event"], data: data as never });
}

export function submitHitl(
  threadId: string,
  decision: HitlDecision,
  editedPrompt: string | undefined,
  onEvent: (ev: ChatEventData) => void,
  onError: (msg: string) => void,
  signal?: AbortSignal
): void {
  const token = localStorage.getItem("token");

  // 确保字段名和后端 Pydantic 模型一模一样
  const bodyData = {
    thread_id: threadId,
    decision: decision, // 确保这里传的是字符串 'approve'
    edited_prompt: editedPrompt || null, // undefined 全部转成 null
  };

  fetch(`${API_BASE}/chat/hitl/${threadId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
    },
    body: JSON.stringify(bodyData),
    signal,
  }).then(async (resp) => {
    if (!resp.ok || !resp.body) {
      // 👇 这里把后端的错误详情打出来
      const errText = await resp.text();
      console.error("422 错误详情:", errText);
      onError(`HITL 提交失败 HTTP ${resp.status}`);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) parseEventBlock(part, onEvent);
    }
  }).catch(() => onError("HITL 提交失败"));
}