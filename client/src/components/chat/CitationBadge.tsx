// 引用角标：sup 标签，区分文件来源 / 网页来源；文件来源可点击打开原文（PDF 页码跳转）
import type { Citation } from "../../types/chat";

interface Props {
  citation: Citation;
  onCiteClick?: (citation: Citation) => void;
}

export function CitationBadge({ citation, onCiteClick }: Props) {
  const isWeb = citation.source_type === "web";
  const clickable = !isWeb && !!citation.file_id && !!onCiteClick;
  return (
    <sup
      title={`${isWeb ? "网页" : "文件"}: ${citation.file_name}${citation.location ? ` / ${citation.location}` : ""}${citation.url ? `\n${citation.url}` : ""}${clickable ? "\n点击查看原文" : ""}`}
      onClick={clickable ? () => onCiteClick(citation) : undefined}
      className={`inline-block -top-0.5 rounded px-1 text-[10px] font-semibold leading-none align-super mx-0.5 select-none ${
        clickable ? "cursor-pointer hover:ring-1 hover:ring-blue-400" : "cursor-help"
      } ${isWeb ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"}`}
    >
      {isWeb ? "🌐" : "📄"}
      {citation.ref}
    </sup>
  );
}
