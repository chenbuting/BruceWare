/** 资料预览里的小模块。点开哪一块只显示那一块，按钮也只做那一块。 */

import type { KbChunk, KbCleanRule, KbDocFlow, KbQuality } from "@/api/types";

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
const RULE_HOWS = [
  { id: "contains", label: "包含这段" },
  { id: "start", label: "开头是" },
  { id: "end", label: "结尾是" },
  { id: "regex", label: "符合正则" },
] as const;

const RULE_ACTIONS = [
  { id: "replace", label: "换成" },
  { id: "cut", label: "删掉这段" },
  { id: "drop_line", label: "删掉整行" },
  { id: "keep_line", label: "只留符合的行" },
] as const;

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
  fileName,
  flow,
  chunkSize,
  chunkOverlap,
  maxChunks,
  ruleHow,
  ruleAction,
  ruleFind,
  ruleReplace,
  busy,
  onFlow,
  onChunkSize,
  onChunkOverlap,
  onMaxChunks,
  onRuleHow,
  onRuleAction,
  onRuleFind,
  onRuleReplace,
  onAddRule,
  onRemoveRule,
  onApply,
  quality,
  parseDraft,
  cleanDraft,
  chunkDrafts,
  onParseDraft,
  onCleanDraft,
  onChunkDraft,
  onSaveReview,
  onSaveChunk,
}: {
  pane: FlowPane;
  fileName: string;
  flow: KbDocFlow;
  chunkSize: string;
  chunkOverlap: string;
  maxChunks: string;
  ruleHow: KbCleanRule["how"];
  ruleAction: KbCleanRule["action"];
  ruleFind: string;
  ruleReplace: string;
  busy: boolean;
  onFlow: (next: KbDocFlow) => void;
  onChunkSize: (value: string) => void;
  onChunkOverlap: (value: string) => void;
  onMaxChunks: (value: string) => void;
  onRuleHow: (value: KbCleanRule["how"]) => void;
  onRuleAction: (value: KbCleanRule["action"]) => void;
  onRuleFind: (value: string) => void;
  onRuleReplace: (value: string) => void;
  onAddRule: () => void;
  onRemoveRule: (index: number) => void;
  onApply: () => void;
  quality: KbQuality[];
  parseDraft: string | null;
  cleanDraft: string | null;
  chunkDrafts: KbChunk[] | null;
  onParseDraft: (value: string) => void;
  onCleanDraft: (value: string) => void;
  onChunkDraft: (id: number, text: string) => void;
  onSaveReview: () => void;
  onSaveChunk: (id: number, text: string) => void;
}) {
  return (
    <div className="text-[13px]">
      {pane === "parse" ? (
        <>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">只抽出正文。清洗、切片和向量不会跟着变。</p>
          <ParseFields fileName={fileName} flow={flow} onFlow={onFlow} />
          <StepButton busy={busy} label="只解析这一份" onApply={onApply} />
          <TextReview
            text={parseDraft}
            busy={busy}
            hint="可以改。点「保存修改」后，清洗会用这段字。没保存就点清洗，仍用刚抽出的结果。"
            onChange={onParseDraft}
            onSave={onSaveReview}
          />
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
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">上面的做法做完后，按你写的规则改。可以多条，从上到下做。</p>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <select className={inputClass} value={ruleHow} onChange={(e) => onRuleHow(e.target.value as KbCleanRule["how"])}>
              {RULE_HOWS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            <select className={inputClass} value={ruleAction} onChange={(e) => onRuleAction(e.target.value as KbCleanRule["action"])}>
              {RULE_ACTIONS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
            <input className={`${inputClass} w-36`} placeholder="要认的内容" value={ruleFind} onChange={(e) => onRuleFind(e.target.value)} />
            {ruleAction === "replace" ? (
              <input className={`${inputClass} w-36`} placeholder="换成" value={ruleReplace} onChange={(e) => onRuleReplace(e.target.value)} />
            ) : null}
            <button type="button" className={btnClass} onClick={onAddRule}>
              添加
            </button>
          </div>
          {flow.rules.map((rule, index) => (
            <RuleRow key={`${rule.how}-${rule.find}-${index}`} rule={rule} onRemove={() => onRemoveRule(index)} />
          ))}
          <p className="mb-1 mt-3">处理脚本</p>
          <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">规则做完后再跑。text 是现在的正文，改完还放回 text。可以用 re。只能改这段字。</p>
          <textarea
            className={`${inputClass} w-full`}
            rows={4}
            placeholder={'text = text.replace("旧", "新")'}
            value={flow.script || ""}
            onChange={(e) => onFlow({ ...flow, script: e.target.value })}
          />
          <StepButton busy={busy} label="只清洗这一份" onApply={onApply} />
          <TextReview
            text={cleanDraft}
            busy={busy}
            hint="可以改。点「保存修改」后，切片会用这段字。没保存就点切片，仍用刚清洗的结果。"
            onChange={onCleanDraft}
            onSave={onSaveReview}
          />
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
          <ChunkReview items={chunkDrafts} busy={busy} onChange={onChunkDraft} onSave={onSaveChunk} />
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

function parseOptions(fileName: string) {
  const suffix = fileName.split(".").pop()?.toLowerCase() || "";
  const head = { id: "head", label: "只抽开头（更短）" };
  if (suffix === "docx") {
    return [
      { id: "standard", label: "标准抽出（只要段落）" },
      head,
      { id: "word_both", label: "段落加表格" },
      { id: "word_table", label: "只要表格" },
    ];
  }
  if (suffix === "pdf") {
    return [{ id: "standard", label: "标准抽出（全部文字）" }, head, { id: "pdf_pages", label: "指定页" }];
  }
  if (suffix === "xlsx" || suffix === "xls") {
    return [
      { id: "standard", label: "标准抽出（全部表）" },
      head,
      { id: "sheet_first", label: "只要第一张表" },
      { id: "sheet_name", label: "指定表名" },
      { id: "sheet_cols", label: "指定列名" },
    ];
  }
  if (suffix === "csv") {
    return [{ id: "standard", label: "标准抽出（全部表）" }, head, { id: "sheet_cols", label: "指定列名" }];
  }
  if (["txt", "md", "log", "json", "yaml", "yml", "ini"].includes(suffix)) {
    return [
      { id: "standard", label: "标准抽出（自动识别编码）" },
      head,
      { id: "text_utf8", label: "强制 UTF-8" },
      { id: "text_gb", label: "强制国标" },
    ];
  }
  return [{ id: "standard", label: "标准抽出" }, head];
}

function ParseFields({ fileName, flow, onFlow }: { fileName: string; flow: KbDocFlow; onFlow: (next: KbDocFlow) => void }) {
  const options = parseOptions(fileName);
  const value = options.some((item) => item.id === flow.parse) ? flow.parse : "standard";
  const hintLabel = value === "pdf_pages" ? "页码，例如 1-3,5" : value === "sheet_name" ? "表名" : value === "sheet_cols" ? "列名，用逗号分开" : "";
  return (
    <>
      <select className={inputClass} value={value} onChange={(e) => onFlow({ ...flow, parse: e.target.value })}>
        {options.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      {hintLabel ? (
        <input
          className={`${inputClass} mt-2 w-full`}
          placeholder={hintLabel}
          value={flow.parse_hint || ""}
          onChange={(e) => onFlow({ ...flow, parse_hint: e.target.value })}
        />
      ) : null}
      <p className="mb-1 mt-3">处理脚本</p>
      <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">抽出后再跑。text 是抽出的正文，改完还放回 text。可以用 re。只能改这段字。</p>
      <textarea
        className={`${inputClass} w-full`}
        rows={4}
        placeholder={'text = text.replace("旧", "新")'}
        value={flow.parse_script || ""}
        onChange={(e) => onFlow({ ...flow, parse_script: e.target.value })}
      />
    </>
  );
}

function TextReview({
  text,
  busy,
  hint,
  onChange,
  onSave,
}: {
  text: string | null;
  busy: boolean;
  hint: string;
  onChange: (value: string) => void;
  onSave: () => void;
}) {
  if (text == null) return null;
  return (
    <div className="mt-3 border border-[var(--line)] px-2 py-2">
      <p className="mb-1">这次的结果</p>
      <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">{hint}</p>
      <textarea className={`${inputClass} min-h-[8rem] w-full`} value={text} onChange={(e) => onChange(e.target.value)} />
      <button type="button" className={`${btnClass} mt-2`} disabled={busy || !text.trim()} onClick={onSave}>
        {busy ? "在保存…" : "保存修改"}
      </button>
    </div>
  );
}

function ChunkReview({
  items,
  busy,
  onChange,
  onSave,
}: {
  items: KbChunk[] | null;
  busy: boolean;
  onChange: (id: number, text: string) => void;
  onSave: (id: number, text: string) => void;
}) {
  if (!items) return null;
  if (!items.length) return <p className="mt-3 text-[12px] text-[var(--muted)]">这次没有切出切片。</p>;
  return (
    <div className="mt-3 border border-[var(--line)] px-2 py-2">
      <p className="mb-1">这次的切片</p>
      <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">可以改每一块。保存后，点「只处理向量」才算确认。</p>
      {items.map((item, index) => (
        <div key={item.id} className="mb-3">
          <p className="mb-1 text-[12px] text-[var(--muted)]">第 {index + 1} 块</p>
          <textarea className={`${inputClass} min-h-[5rem] w-full`} value={item.text} onChange={(e) => onChange(item.id, e.target.value)} />
          <button type="button" className={`${btnClass} mt-1`} disabled={busy || !item.text.trim()} onClick={() => onSave(item.id, item.text)}>
            {busy ? "在保存…" : "保存修改"}
          </button>
        </div>
      ))}
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
  const how = RULE_HOWS.find((item) => item.id === rule.how)?.label || "包含这段";
  const action = RULE_ACTIONS.find((item) => item.id === rule.action)?.label || "换成";
  const text = rule.action === "replace" ? `${how}「${rule.find}」，换成「${rule.replace || "空"}」` : `${how}「${rule.find}」，${action}`;
  return (
    <p className="mb-1 flex flex-wrap items-center gap-2">
      <span>{text}</span>
      <button type="button" className="text-[var(--muted)]" onClick={onRemove}>
        删除
      </button>
    </p>
  );
}

function toggleClean(cleans: string[], id: string) {
  return cleans.includes(id) ? cleans.filter((item) => item !== id) : [...cleans, id];
}
