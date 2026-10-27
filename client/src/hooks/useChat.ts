// useChat：管理一次问答的 SSE 状态机（thinking / token / citation / hitl / done）
import { useCallback, useRef, useState } from "react";
import { ask, submitHitl } from "../api/chat";
import type { ChatEventData, ChatMessage, Citation, HitlDecision } from "../types/chat";

export interface HitlState {
  threadId: string;
  action: string;
  context: Record<string, unknown>;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [thinking, setThinking] = useState<string>("");
  const [thinkingOpen, setThinkingOpen] = useState(false);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [hitl, setHitl] = useState<HitlState | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleEvent = useCallback((ev: ChatEventData) => {
    switch (ev.event) {
      case "thinking":
        setThinking((t) => t + ev.data.reasoning);
        break;
      case "token":
        setMessages((msgs) => {
          const arr = [...msgs];
          const last = arr[arr.length - 1];
          if (last && last.role === "assistant" && last.isStreaming) {
            arr[arr.length - 1] = { ...last, content: last.content + ev.data.text };
          } else {
            arr.push({ id: crypto.randomUUID(), role: "assistant", content: ev.data.text, citations: [], isStreaming: true });
          }
          return arr;
        });
        break;
      case "tool_status":
        setToolStatus(ev.data.message);
        break;
      case "citation":
        setMessages((msgs) => {
          const arr = [...msgs];
          const last = arr[arr.length - 1];
          if (last && last.role === "assistant") {
            const exists = last.citations.some((c) => c.ref === ev.data.ref);
            arr[arr.length - 1] = {
              ...last,
              citations: exists ? last.citations : [...last.citations, ev.data],
            };
          }
          return arr;
        });
        break;
      case "hitl_pending":
        // 👇 改这里，打印所有键名，以及看看 ev.data 到底是什么格式
        console.log("🚨 收到 HITL:", ev.data);
        if (ev.data) {
          console.log("🚨 包含的键名:", Object.keys(ev.data));
        }

        setHitl({ threadId: ev.data.thread_id, action: ev.data.action, context: ev.data.context });
        setStreaming(false);
        break;
      case "done":
        setMessages((msgs) => {
          const arr = [...msgs];
          const last = arr[arr.length - 1];
          if (last && last.role === "assistant") {
            arr[arr.length - 1] = { ...last, citations: ev.data.citations, isStreaming: false };
          }
          return arr;
        });
        setStreaming(false);
        setThinking("");
        setToolStatus(null);
        break;
      case "error":
        setError(ev.data.message);
        setStreaming(false);
        break;
    }
  }, []);

  const send = useCallback(
    (question: string, fileIds?: number[], conversationId?: number) => {
      if (!question.trim() || streaming) return;
      setError(null);
      setThinking("");
      setToolStatus(null);
      setHitl(null);
      setMessages((msgs) => [...msgs, { id: crypto.randomUUID(), role: "user", content: question, citations: [] }]);
      setStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;
      ask(
        { question, file_ids: fileIds, conversation_id: conversationId },
        handleEvent,
        (msg) => {
          setError(msg);
          setStreaming(false);
        },
        controller.signal
      );
    },
    [handleEvent, streaming]
  );

  const decide = useCallback(
    (decision: HitlDecision, editedPrompt?: string) => {
      if (!hitl || streaming) return;
      if (!hitl.threadId || hitl.threadId === "undefined") {
        alert("后端未返回有效的 Thread ID，请刷新页面重试！");
        return;
      }

      // 点击后立即关闭弹窗：否则 SSE 结束后 hitl 仍在，重复点击会再次提交生成相同内容
      setHitl(null);
      setStreaming(true);
      console.log("【前端准备提交HITL】", { hitl, decision, editedPrompt });
      const controller = new AbortController();
      abortRef.current = controller;
      submitHitl(
        hitl.threadId,
        decision,
        editedPrompt,
        handleEvent,
        (msg) => {
          setError(msg);
          setStreaming(false);
        },
        controller.signal
      );
    },
    [hitl, streaming, handleEvent]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
  }, []);

  return { messages, thinking, thinkingOpen, setThinkingOpen, toolStatus, hitl, streaming, error, send, decide, stop };
}