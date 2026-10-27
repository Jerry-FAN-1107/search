// 工具状态条：tool_status 事件，提示当前正在调用哪个工具/检索哪份文件
interface Props {
  status: string | null;
}

export function ToolStatus({ status }: Props) {
  if (!status) return null;
  return (
    <div className="flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs text-blue-700">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-blue-300 border-t-blue-700" />
      {status}
    </div>
  );
}