// 引用标注工具：把正文中的 [n] 拆分为可渲染片段，并检测无依据陈述
export interface Segment {
  text: string;
  refs: number[];
}

export function renderSegments(content: string): Segment[] {
  const re = /\[(\d+)\]/g;
  const segments: Segment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  let cur = { text: "", refs: [] as number[] };
  while ((m = re.exec(content)) !== null) {
    cur.text += content.slice(last, m.index);
    cur.refs.push(Number(m[1]));
    last = m.index + m[0].length;
  }
  cur.text += content.slice(last);
  if (cur.text.trim()) segments.push(cur);
  return segments;
}

export function hasUncitedStatement(content: string): boolean {
  if (!content) return false;
  const stripped = content.replace(/\[\d+\]/g, "");
  const sentences = stripped.split(/(?<=[。；！？\n])/);
  for (const s of sentences) {
    const t = s.trim();
    if (t.length < 8) continue;
    if (t.startsWith("#") || t.startsWith("-")) continue;
    if (/\d+/.test(t) && /\[\d+\]/.test(content)) continue;
    return true;
  }
  return false;
}