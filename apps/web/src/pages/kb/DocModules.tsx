/** 资料预览里的小模块。处理是怎么做，查看是看哪一块。以后加模块，往这两个列表里加一项即可。 */

import type { KbDocFlow } from "@/api/types";

const inputClass = "border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px]";
const btnClass = "border border-[var(--line)] bg-[var(--paper)] px-2.5 py-1.5 text-[13px] disabled:opacity-50";

export const FLOW_MODULES = [
  { id: "parse", label: "解析" },
  { id: "clean", label: "清洗" },
  { id: "chunk", label: "切片" },
  { id: "vector", label: "向量" },
] as const;

export const VIEW_MODULES = [
  { id: "file", label: "原文" },
  { id: "images", label: "图" },
  { id: "chunks", label: "切片" },
  { id: "wiki", label: "摘要" },
] as const;

export type FlowPane = (typeof FLOW_MODULES)[number]["id"];
export type ViewPane = (typeof VIEW_MODULES)[number]["id"];
export type DocPane = FlowPane | ViewPane;

type ModuleItem = { id: DocPane; label: string };

export function isFlowPane(pane: DocPane): pane is FlowPane {
  return FLOW_MODULES.some((item) => item.id === pane);
}

export function DocModuleBar({ pane, onChange }: { pane: DocPane; onChange: (id: DocPane) => void }) {
  return (
    <div className="mb-2 border border-[var(--line)] text-[13px]">
      <ModuleRow title="处理" items={[...FLOW_MODULES]} pane={pane} onChange={onChange} />
      <ModuleRow title="查看" items={[...VIEW_MODULES]} pane={pane} onChange={onChange} />
    </div>
  );
}

function ModuleRow({
  title,
  items,
  pane,
  onChange,
}: {
  title: string;
  items: ModuleItem[];
  pane: DocPane;
  onChange: (id: DocPane) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-[var(--line)] px-2 py-1 last:border-b-0">
      <span className="mr-1 text-[var(--muted)]">{title}</span>
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`px-2 py-1 ${pane === item.id ? "bg-[var(--bg)] font-medium" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function FlowModulePanel({
  pane,
  flow,
  chunkSize,
  chunkOverlap,
  maxChunks,
  busy,
  onFlow,
  onChunkSize,
  onChunkOverlap,
  onMaxChunks,
  onApply,
}: {
  pane: FlowPane;
  flow: KbDocFlow;
  chunkSize: string;
  chunkOverlap: string;
  maxChunks: string;
  busy: boolean;
  onFlow: (next: KbDocFlow) => void;
  onChunkSize: (value: string) => void;
  onChunkOverlap: (value: string) => void;
  onMaxChunks: (value: string) => void;
  onApply: () => void;
}) {
  return (
    <div className="mb-2 border border-[var(--line)] px-2 py-2 text-[13px]">
      {pane === "parse" ? (
        <label className="flex flex-wrap items-center gap-2">
          这一份怎么抽
          <select className={inputClass} value={flow.parse} onChange={(e) => onFlow({ ...flow, parse: e.target.value === "head" ? "head" : "standard" })}>
            <option value="standard">标准抽出</option>
            <option value="head">只抽开头（更短）</option>
          </select>
        </label>
      ) : null}
      {pane === "clean" ? (
        <label className="flex flex-wrap items-center gap-2">
          这一份怎么洗
          <select className={inputClass} value={flow.clean} onChange={(e) => onFlow({ ...flow, clean: e.target.value as KbDocFlow["clean"] })}>
            <option value="collapse">收成一行</option>
            <option value="keep">保留换行</option>
            <option value="blank">去掉空行</option>
            <option value="dedupe">去掉重复行</option>
          </select>
        </label>
      ) : null}
      {pane === "chunk" ? (
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2">
            这一份怎么切
            <select className={inputClass} value={flow.chunk} onChange={(e) => onFlow({ ...flow, chunk: e.target.value as KbDocFlow["chunk"] })}>
              <option value="chars">按字数</option>
              <option value="paragraph">按段落</option>
              <option value="whole">整篇一段</option>
            </select>
          </label>
          {flow.chunk === "chars" ? (
            <>
              <label>
                长度
                <input className={`${inputClass} ml-1 w-20`} inputMode="numeric" value={chunkSize} onChange={(e) => onChunkSize(e.target.value)} />
              </label>
              <label>
                重叠
                <input className={`${inputClass} ml-1 w-20`} inputMode="numeric" value={chunkOverlap} onChange={(e) => onChunkOverlap(e.target.value)} />
              </label>
              <label>
                最多段
                <input className={`${inputClass} ml-1 w-20`} inputMode="numeric" value={maxChunks} onChange={(e) => onMaxChunks(e.target.value)} />
              </label>
            </>
          ) : null}
        </div>
      ) : null}
      {pane === "vector" ? (
        <label className="flex flex-wrap items-center gap-2">
          这一份要不要向量
          <select className={inputClass} value={flow.vector ? "on" : "off"} onChange={(e) => onFlow({ ...flow, vector: e.target.value !== "off" })}>
            <option value="on">要向量</option>
            <option value="off">只按关键词</option>
          </select>
        </label>
      ) : null}
      <button type="button" className={`${btnClass} mt-2`} disabled={busy} onClick={onApply}>
        {busy ? "在处理…" : "按这个处理这一份"}
      </button>
    </div>
  );
}
