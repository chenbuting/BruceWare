/** 资料预览里的小模块。点开哪一块只显示那一块，按钮也只做那一块。 */

import type { KbCleanRule, KbDocFlow, KbQuality } from "@/api/types";

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

/** 清洗按数仓质量那几类分组。默认只勾「收成一行」，和以前一样。 */
const CLEAN_GROUPS = [
  { name: "完整性", hint: "空的不要", options: [{ id: "blank", label: "去掉空行" }] },
  { name: "唯一性", hint: "重复只留一份", options: [{ id: "dedupe", label: "去掉重复段落" }] },
  { name: "规范性", hint: "写法统一", options: [
    { id: "collapse", label: "收成一行" },
    { id: "half", label: "全角转半角" },
    { id: "punct", label: "统一中文标点" },
  ] },
  { name: "有效性", hint: "不像正文的去掉", options: [{ id: "page", label: "去掉页码" }] },
  { name: "安全性", hint: "敏感信息打码", options: [{ id: "mask", label: "手机号和身份证打码" }] },
] as const;

export type FlowPane = (typeof FLOW_MODULES)[number]["id"];
export type ViewPane = (typeof VIEW_MODULES)[number]["id"];
export type DocPane = FlowPane | ViewPane;

export function isFlowPane(pane: DocPane): pane is FlowPane {
  return FLOW_MODULES.some((item) => item.id === pane);
}

export function DocModuleBar({ pane, onChange }: { pane: DocPane; onChange: (id: DocPane) => void }) {
  return (
    <div className="mb-2 border border-[var(--line)] text-[13px]">
      <ModuleRow title="处理" items={FLOW_MODULES} pane={pane} onChange={onChange} />
      <ModuleRow title="查看" items={VIEW_MODULES} pane={pane} onChange={onChange} />
    </div>
  );
}

function ModuleRow<T extends DocPane>({
  title,
  items,
  pane,
  onChange,
}: {
  title: string;
  items: readonly { id: T; label: string }[];
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
  ruleFind,
  ruleReplace,
  busy,
  onFlow,
  onChunkSize,
  onChunkOverlap,
  onMaxChunks,
  onRuleFind,
  onRuleReplace,
  onAddRule,
  onRemoveRule,
  onApply,
  quality,
}: {
  pane: FlowPane;
  flow: KbDocFlow;
  chunkSize: string;
  chunkOverlap: string;
  maxChunks: string;
  ruleFind: string;
  ruleReplace: string;
  busy: boolean;
  onFlow: (next: KbDocFlow) => void;
  onChunkSize: (value: string) => void;
  onChunkOverlap: (value: string) => void;
  onMaxChunks: (value: string) => void;
  onRuleFind: (value: string) => void;
  onRuleReplace: (value: string) => void;
  onAddRule: () => void;
  onRemoveRule: (index: number) => void;
  onApply: () => void;
  quality: KbQuality[];
}) {
  return (
    <div className="text-[13px]">
      {pane === "parse" ? (
        <>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">只抽出正文。清洗、切片和向量不会跟着变。</p>
          <select className={inputClass} value={flow.parse} onChange={(e) => onFlow({ ...flow, parse: e.target.value === "head" ? "head" : "standard" })}>
            <option value="standard">标准抽出</option>
            <option value="head">只抽开头（更短）</option>
          </select>
          <StepButton busy={busy} label="只解析这一份" onApply={onApply} />
        </>
      ) : null}
      {pane === "clean" ? (
        <>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">只清洗这一份。可以多选。切片和向量不会跟着变。</p>
          {CLEAN_GROUPS.map((group) => (
            <div key={group.name} className="mb-3">
              <p className="mb-1">
                {group.name}
                <span className="ml-2 text-[12px] text-[var(--muted)]">{group.hint}</span>
              </p>
              <div className="flex flex-wrap gap-x-4 gap-y-2">
                {group.options.map((item) => (
                  <label key={item.id} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={flow.cleans.includes(item.id)}
                      onChange={() => onFlow({ ...flow, cleans: toggleClean(flow.cleans, item.id) })}
                    />
                    {item.label}
                  </label>
                ))}
              </div>
            </div>
          ))}
          <p className="mb-1">自定义规则</p>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">上面的做法做完后，再按你写的字替换。找到的内容会原样换成新的。</p>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <input className={`${inputClass} w-36`} placeholder="找到" value={ruleFind} onChange={(e) => onRuleFind(e.target.value)} />
            <input className={`${inputClass} w-36`} placeholder="换成" value={ruleReplace} onChange={(e) => onRuleReplace(e.target.value)} />
            <button type="button" className={btnClass} onClick={onAddRule}>
              添加
            </button>
          </div>
          {flow.rules.map((rule, index) => (
            <RuleRow key={`${rule.find}-${index}`} rule={rule} onRemove={() => onRemoveRule(index)} />
          ))}
          <StepButton busy={busy} label="只清洗这一份" onApply={onApply} />
          <QualityReport items={quality} />
        </>
      ) : null}
      {pane === "chunk" ? (
        <>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">只按现在的正文重新切片。不算向量。</p>
          <div className="flex flex-wrap items-center gap-2">
            <select className={inputClass} value={flow.chunk} onChange={(e) => onFlow({ ...flow, chunk: e.target.value as KbDocFlow["chunk"] })}>
              <option value="chars">按字数</option>
              <option value="paragraph">按段落</option>
              <option value="whole">整篇一段</option>
            </select>
            {flow.chunk === "chars" ? (
              <>
                <label>
                  长度
                  <input className={`${inputClass} ml-1 w-16`} inputMode="numeric" value={chunkSize} onChange={(e) => onChunkSize(e.target.value)} />
                </label>
                <label>
                  重叠
                  <input className={`${inputClass} ml-1 w-16`} inputMode="numeric" value={chunkOverlap} onChange={(e) => onChunkOverlap(e.target.value)} />
                </label>
                <label>
                  最多段
                  <input className={`${inputClass} ml-1 w-16`} inputMode="numeric" value={maxChunks} onChange={(e) => onMaxChunks(e.target.value)} />
                </label>
              </>
            ) : null}
          </div>
          <StepButton busy={busy} label="只切片这一份" onApply={onApply} />
        </>
      ) : null}
      {pane === "vector" ? (
        <>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">只处理现有切片的向量。不会重新解析或清洗。</p>
          <select className={inputClass} value={flow.vector ? "on" : "off"} onChange={(e) => onFlow({ ...flow, vector: e.target.value !== "off" })}>
            <option value="on">要向量</option>
            <option value="off">只按关键词</option>
          </select>
          <StepButton busy={busy} label="只处理向量" onApply={onApply} />
        </>
      ) : null}
    </div>
  );
}

function QualityReport({ items }: { items: KbQuality[] }) {
  if (!items.length) {
    return <p className="mt-3 text-[12px] leading-5 text-[var(--muted)]">点「只清洗这一份」后，这里列出每一类过了几条、挡了几条。</p>;
  }
  return (
    <div className="mt-3 border border-[var(--line)] px-2 py-2 text-[12px] leading-5">
      <p className="mb-1">质量结果</p>
      {items.map((item) => (
        <p key={item.name}>
          {item.name}：过了 {item.passed} 条，挡了 {item.blocked} 条
        </p>
      ))}
    </div>
  );
}

function StepButton({ busy, label, onApply }: { busy: boolean; label: string; onApply: () => void }) {
  return (
    <button type="button" className={`${btnClass} mt-3`} disabled={busy} onClick={onApply}>
      {busy ? "在处理…" : label}
    </button>
  );
}

function RuleRow({ rule, onRemove }: { rule: KbCleanRule; onRemove: () => void }) {
  return (
    <p className="mb-1 flex flex-wrap items-center gap-2">
      <span>把「{rule.find}」换成「{rule.replace || "空"}」</span>
      <button type="button" className="text-[var(--muted)]" onClick={onRemove}>
        删除
      </button>
    </p>
  );
}

function toggleClean(cleans: string[], id: string) {
  return cleans.includes(id) ? cleans.filter((item) => item !== id) : [...cleans, id];
}
