// 单条消息渲染：用户提问 / 助手回答（含角标 + 无依据警示）
import { CitationBadge } from "./CitationBadge";
import { hasUncitedStatement, renderSegments } from "../../utils/citation";
import type { ChatMessage, Citation } from "../../types/chat";

interface Props {
  message: ChatMessage;
  onCiteClick?: (citation: Citation) => void;
}

export function ChatMessageView({ message, onCiteClick }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-brand-700 px-4 py-2.5 text-white">
          {message.content}
        </div>
      </div>
    );
  }

  const segments = renderSegments(message.content);
  const refMap = new Map(message.citations.map((c) => [c.ref, c]));
  const uncited = !message.isStreaming && hasUncitedStatement(message.content);

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        {uncited && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs text-amber-700">
            ⚠️ 本回答含无引用编号的陈述，可能缺少资料依据，请核对。
          </div>
        )}
        <div className="rounded-2xl rounded-bl-sm border border-gray-200 bg-white px-4 py-3 text-[15px] leading-relaxed">
          {segments.length === 0 && <span className="text-gray-400">{message.isStreaming ? "正在生成…" : ""}</span>}
          {segments.map((seg, i) => (
            <span key={i}>
              {seg.text}
              {seg.refs.map((r, j) => {
                const c = refMap.get(r);
                // key 用 ref+序号：同一编号可能在同段多次出现（如连续引用 [4][4]）
                return c ? <CitationBadge key={`${r}-${j}`} citation={c} onCiteClick={onCiteClick} /> : null;
              })}
            </span>
          ))}
          {message.isStreaming && <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-gray-400" />}
        </div>
      </div>
    </div>
  );
}
