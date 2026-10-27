// HITL 待确认卡片：展示待审批动作，提供 approve / edit / reject 三种决策
import { useState } from "react";
import type { HitlState } from "../../hooks/useChat";
import type { HitlDecision } from "../../types/chat";

interface Props {
  hitl: HitlState;
  onDecide: (decision: HitlDecision, editedPrompt?: string) => void;
}

const ACTION_LABEL: Record<string, string> = {
  web_search: "发起联网搜索",
  final_generate_external: "基于外部资料生成最终答案",
  export_table: "保存 / 导出表格",
};

export function HitlCard({ hitl, onDecide }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const label = ACTION_LABEL[hitl.action] ?? hitl.action;

  return (
    <div className="rounded-lg border border-brand-100 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center gap-2">
        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-700">待人工确认</span>
        <span className="text-sm font-medium text-gray-800">{label}</span>
      </div>
      <p className="mb-3 text-xs text-gray-500">
        系统已暂停执行，等待你的决定。
      </p>
      {Object.entries(hitl.context ?? {}).map(([k, v]) => (
        <div key={k} className="mb-1 rounded bg-gray-50 px-2 py-1 text-xs text-gray-600">
          <span className="font-medium">{k}：</span>
          <span className="break-all">{typeof v === "string" ? v : JSON.stringify(v)}</span>
        </div>
      ))}

      {editing && (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="编辑 / 补充指令（可选）"
          rows={2}
          className="mb-2 w-full rounded border border-gray-300 p-2 text-sm"
        />
      )}

      <div className="mt-2 flex gap-2">
        <button
          onClick={() => onDecide("approve")}
          className="rounded-md bg-brand-700 px-3 py-1.5 text-sm text-white hover:bg-brand-800"
        >
          批准
        </button>
        {editing ? (
          <button
            onClick={() => onDecide("edit", draft)}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white"
          >
            提交编辑
          </button>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700"
          >
            编辑
          </button>
        )}
        <button
          onClick={() => onDecide("reject")}
          className="rounded-md border border-red-200 px-3 py-1.5 text-sm text-red-600"
        >
          拒绝
        </button>
      </div>
    </div>
  );
}