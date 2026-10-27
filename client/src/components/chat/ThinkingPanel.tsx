// 思考过程面板：接收 thinking 事件，可折叠展示
interface Props {
  thinking: string;
  open: boolean;
  onToggle: (open: boolean) => void;
}

export function ThinkingPanel({ thinking, open, onToggle }: Props) {
  if (!thinking) return null;
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50">
      <button
        onClick={() => onToggle(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-gray-500"
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>▸</span>
        思考过程
        <span className="ml-auto text-gray-400">{open ? "收起" : "展开"}</span>
      </button>
      {open && (
        <pre className="max-h-56 overflow-auto whitespace-pre-wrap px-3 pb-3 text-xs text-gray-600">
          {thinking}
        </pre>
      )}
    </div>
  );
}