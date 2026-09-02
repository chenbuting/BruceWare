import { useEffect, useRef, useState } from "react";

import {
  addWardrobeItem,
  addWardrobeStyle,
  analyzeWardrobePhoto,
  createWardrobeLook,
  deleteWardrobeItem,
  deleteWardrobeLook,
  deleteWardrobeStyle,
  fetchWardrobeItems,
  fetchWardrobeLooks,
  fetchWardrobeStatus,
  fetchWardrobeStyles,
  importWardrobeItems,
  saveWardrobeReference,
  remakeWardrobeLook,
  setWardrobeStyleActive,
  varyWardrobeLook,
} from "@/api/client";
import type { WardrobeDetected, WardrobeItem, WardrobeLook, WardrobeStyle } from "@/api/types";
import { Card } from "@/components/Card";
import { ConfirmModal, Modal } from "@/components/Modal";

type Tab = "closet" | "import" | "looks" | "styles";

const PARTS = [
  { id: "", label: "全部" },
  { id: "upperbody", label: "上装" },
  { id: "wholebody_up", label: "外套" },
  { id: "lowerbody", label: "下装" },
  { id: "accessories_up", label: "配饰" },
  { id: "shoes", label: "鞋" },
];
const ITEM_PARTS = PARTS.filter((item) => item.id);

type DirectDraft = { file: File; preview: string; name: string; part: string };
type Preview =
  | { kind: "item"; item: WardrobeItem }
  | { kind: "look"; look: WardrobeLook }
  | { kind: "photo"; src: string; title: string };

/** 搭配放大：效果图、这套衣服、生成时记下的风格图 */
function LookPreview({
  look,
  items,
  focusId,
  styleFocusSrc,
  busy,
  onFocus,
  onFocusStyle,
  onVary,
  onRemake,
}: {
  look: WardrobeLook;
  items: WardrobeItem[];
  focusId: number | null;
  styleFocusSrc: string;
  busy: boolean;
  onFocus: (id: number | null) => void;
  onFocusStyle: (src: string) => void;
  onVary: () => void;
  onRemake: (prompt: string) => void;
}) {
  const [draft, setDraft] = useState(look.prompt || "");
  useEffect(() => {
    setDraft(look.prompt || "");
  }, [look.id, look.prompt]);
  const focusItem = focusId ? items.find((row) => row.id === focusId) : null;
  const styleName = look.style_name || "";
  const styleUrls = look.style_image_urls || [];
  const beforeSrc = look.source_image_url || "";
  const comparing = Boolean(beforeSrc) && !focusItem && !styleFocusSrc;
  const mainSrc = focusItem
    ? focusItem.cutout_url || focusItem.original_url
    : styleFocusSrc || look.image_url;
  const mainAlt = focusItem ? focusItem.name : styleFocusSrc ? styleName || "风格参考" : look.title;

  return (
    <div>
      {comparing ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <div className="mb-1 text-[12px] text-[var(--muted)]">裂变前</div>
            <div className="flex max-h-[48vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
              <img src={beforeSrc} alt="裂变前" className="max-h-[48vh] max-w-full object-contain" />
            </div>
          </div>
          <div>
            <div className="mb-1 text-[12px] text-[var(--muted)]">裂变后</div>
            <div className="flex max-h-[48vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
              {look.image_url ? <img src={look.image_url} alt="裂变后" className="max-h-[48vh] max-w-full object-contain" /> : null}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex max-h-[48vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
          {mainSrc ? <img src={mainSrc} alt={mainAlt} className="max-h-[48vh] max-w-full object-contain" /> : null}
        </div>
      )}
      {focusItem ? (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[13px] text-[var(--muted)]">
          <span>
            {focusItem.name} · {focusItem.part_label}
            {focusItem.color ? ` · ${focusItem.color}` : ""}
          </span>
          <button type="button" className="text-[var(--text)]" onClick={() => onFocus(null)}>
            看整套
          </button>
        </div>
      ) : styleFocusSrc ? (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[13px] text-[var(--muted)]">
          <span>风格参考{styleName ? ` · ${styleName}` : ""}</span>
          <button type="button" className="text-[var(--text)]" onClick={() => onFocusStyle("")}>
            看整套
          </button>
        </div>
      ) : (
        <p className="mt-2 text-[13px] text-[var(--muted)]">
          {comparing ? "左右是裂变前后对比。点下面单件或风格图，看细节。" : "点下面单件或风格图，看细节。"}
        </p>
      )}
      <button type="button" className="mt-3 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50" disabled={busy} onClick={onVary}>
        {busy ? "裂变中…" : "姿势裂变"}
      </button>
      <div className="mt-4">
        <div className="text-[13px] font-medium">提示词</div>
        <p className="mt-1 text-[12px] text-[var(--muted)]">可以改几句再点重做，人、衣服尽量按原图走。</p>
        <textarea
          className="mt-2 min-h-28 w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px] leading-6"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button
          type="button"
          className="mt-2 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50"
          disabled={busy || !draft.trim()}
          onClick={() => onRemake(draft.trim())}
        >
          {busy ? "重做中…" : "按提示词重做"}
        </button>
      </div>
      <div className="mt-4 text-[13px] font-medium">这套用了 {look.item_ids.length} 件</div>
      {look.item_ids.length === 0 ? (
        <p className="mt-2 text-[13px] text-[var(--muted)]">没有记下衣服明细。</p>
      ) : (
        <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-4">
          {look.item_ids.map((id) => {
            const item = items.find((row) => row.id === id);
            if (!item) {
              return (
                <div key={id} className="rounded-md border border-[var(--line)] px-2 py-3 text-center text-[12px] text-[var(--muted)]">
                  已不在衣橱
                </div>
              );
            }
            return (
              <button
                key={id}
                type="button"
                className={`rounded-md border px-2 py-2 text-left ${focusId === id ? "border-[var(--text)] bg-[var(--bg)]" : "border-[var(--line)] bg-[var(--paper)]"}`}
                onClick={() => {
                  onFocusStyle("");
                  onFocus(focusId === id ? null : id);
                }}
              >
                <div className="flex h-20 items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
                  {item.cutout_url || item.original_url ? (
                    <img src={item.cutout_url || item.original_url} alt={item.name} className="max-h-full max-w-full object-contain" />
                  ) : null}
                </div>
                <div className="mt-2 truncate text-[12px]">{item.name}</div>
                <div className="truncate text-[12px] text-[var(--muted)]">{item.part_label}{item.color ? ` · ${item.color}` : ""}</div>
              </button>
            );
          })}
        </div>
      )}
      {styleName || styleUrls.length > 0 ? (
        <>
          <div className="mt-4 text-[13px] font-medium">风格参考{styleName ? ` · ${styleName}` : ""}</div>
          {styleUrls.length === 0 ? (
            <p className="mt-2 text-[13px] text-[var(--muted)]">当时没有存下风格图。</p>
          ) : (
            <div className="mt-2 flex flex-wrap gap-2">
              {styleUrls.map((url) => (
                <button
                  key={url}
                  type="button"
                  className={`h-24 w-24 overflow-hidden rounded-md border bg-[var(--bg)] ${styleFocusSrc === url ? "border-[var(--text)]" : "border-[var(--line)]"}`}
                  onClick={() => {
                    onFocus(null);
                    onFocusStyle(styleFocusSrc === url ? "" : url);
                  }}
                >
                  <img src={url} alt={styleName || "风格参考"} className="h-full w-full object-cover" />
                </button>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

/** 衣橱：识别照片里的衣服，生成单件图、试穿和搭配 */
export function WardrobePage() {
  const [tab, setTab] = useState<Tab>("closet");
  const [items, setItems] = useState<WardrobeItem[]>([]);
  const [looks, setLooks] = useState<WardrobeLook[]>([]);
  const [styles, setStyles] = useState<WardrobeStyle[]>([]);
  const [styleName, setStyleName] = useState("");
  const [styleDrafts, setStyleDrafts] = useState<{ file: File; preview: string }[]>([]);
  const [activeStyleName, setActiveStyleName] = useState("");
  const [part, setPart] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [referenceUrl, setReferenceUrl] = useState("");
  const [uploadId, setUploadId] = useState("");
  const [detected, setDetected] = useState<WardrobeDetected[]>([]);
  const [chosen, setChosen] = useState<boolean[]>([]);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [askId, setAskId] = useState<number | null>(null);
  const [askStyleId, setAskStyleId] = useState<number | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [lookFocusId, setLookFocusId] = useState<number | null>(null);
  const [styleFocusSrc, setStyleFocusSrc] = useState("");
  const [drafts, setDrafts] = useState<DirectDraft[]>([]);
  const importRef = useRef<HTMLInputElement>(null);
  const directRef = useRef<HTMLInputElement>(null);
  const selfRef = useRef<HTMLInputElement>(null);
  const styleRef = useRef<HTMLInputElement>(null);
  const varyRef = useRef<HTMLInputElement>(null);
  const [varyCount, setVaryCount] = useState(2);

  async function reload() {
    const [status, closet, looksData, stylesData] = await Promise.all([
      fetchWardrobeStatus(),
      fetchWardrobeItems(),
      fetchWardrobeLooks(),
      fetchWardrobeStyles(),
    ]);
    setReferenceUrl(status.reference_url);
    setActiveStyleName(status.active_style_name || "");
    setItems(closet.items);
    setLooks(looksData.items);
    setStyles(stylesData.items);
  }

  useEffect(() => {
    reload().catch((err: Error) => setError(err.message));
  }, []);

  async function onSelf(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const data = await saveWardrobeReference(file);
      setReferenceUrl(data.reference_url);
      setHint(activeStyleName ? `已保存你的照片。当前风格：${activeStyleName}` : "已保存你的照片，试穿会用它");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
      if (selfRef.current) selfRef.current.value = "";
    }
  }

  function clearDrafts() {
    drafts.forEach((item) => URL.revokeObjectURL(item.preview));
    setDrafts([]);
  }

  function onPickDirect(files: FileList | null) {
    if (!files?.length) return;
    const next = Array.from(files).map((file) => ({
      file,
      preview: URL.createObjectURL(file),
      name: file.name.replace(/\.[^.]+$/, "") || "衣服",
      part: "upperbody",
    }));
    setDrafts((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.preview));
      return next;
    });
    setError("");
    setHint(`选了 ${next.length} 张，改好名称和分类再加入`);
    if (directRef.current) directRef.current.value = "";
  }

  async function onAddDirect() {
    if (drafts.length === 0) {
      setError("请先选衣服图片");
      return;
    }
    setBusy(true);
    setError("");
    setHint("正在加入衣橱");
    try {
      for (const item of drafts) {
        await addWardrobeItem(item.file, item.name.trim() || "衣服", item.part);
      }
      clearDrafts();
      await reload();
      setTab("closet");
      setHint("已加入衣橱");
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入失败");
    } finally {
      setBusy(false);
    }
  }

  async function onAnalyze(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError("");
    setHint("");
    try {
      const data = await analyzeWardrobePhoto(file);
      setUploadId(data.upload_id);
      setDetected(data.items);
      setChosen(data.items.map(() => true));
      setHint(data.items.length ? `认出 ${data.items.length} 件` : "没认出衣服");
    } catch (err) {
      setError(err instanceof Error ? err.message : "识别失败");
    } finally {
      setBusy(false);
      if (importRef.current) importRef.current.value = "";
    }
  }

  async function onImport() {
    const selected = detected.filter((_, index) => chosen[index]);
    if (!uploadId || selected.length === 0) {
      setError("请先识别并勾选衣服");
      return;
    }
    setBusy(true);
    setError("");
    setHint("正在抠图，可能要等一会儿");
    try {
      await importWardrobeItems(uploadId, selected);
      setUploadId("");
      setDetected([]);
      setChosen([]);
      await reload();
      setTab("closet");
      setHint("已加入衣橱");
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
    }
  }

  function onPickStyle(files: FileList | null) {
    if (!files?.length) return;
    const next = Array.from(files).slice(0, 4).map((file) => ({ file, preview: URL.createObjectURL(file) }));
    setStyleDrafts((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.preview));
      return next;
    });
    if (styleRef.current) styleRef.current.value = "";
  }

  async function onSaveStyle() {
    if (styleDrafts.length === 0) {
      setError("请先选几张品牌图");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await addWardrobeStyle(styleName.trim() || "未命名风格", styleDrafts.map((item) => item.file));
      styleDrafts.forEach((item) => URL.revokeObjectURL(item.preview));
      setStyleDrafts([]);
      setStyleName("");
      await reload();
      setHint("风格已保存，点「使用」就能切换");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function onVary(lookId?: number, file?: File) {
    if (!lookId && !file) {
      setError("请先选一套搭配，或上传一张图");
      return;
    }
    setBusy(true);
    setError("");
    setHint(`正在做姿势裂变，一次 ${varyCount} 张，大约一两分钟，请不要重复点`);
    try {
      const data = await varyWardrobeLook(lookId, file, varyCount);
      await reload();
      setTab("looks");
      setPreview(null);
      setHint(data.items.length >= varyCount ? "姿势裂变好了，新图已放到搭配" : `只做出 ${data.items.length} 张，可以再试一次`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "裂变失败");
    } finally {
      setBusy(false);
      if (varyRef.current) varyRef.current.value = "";
    }
  }

  async function onRemake(lookId: number, prompt: string) {
    if (!prompt.trim()) {
      setError("请先写提示词");
      return;
    }
    setBusy(true);
    setError("");
    setHint("正在按你改过的提示词重做，大约一两分钟");
    try {
      const updated = await remakeWardrobeLook(lookId, prompt.trim());
      setLooks((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setPreview({ kind: "look", look: updated });
      setHint("已按新提示词重做");
    } catch (err) {
      setError(err instanceof Error ? err.message : "重做失败");
    } finally {
      setBusy(false);
    }
  }

  async function onTryOn(ids: number[]) {
    if (ids.length < 1) {
      setError("请先选一件衣服");
      return;
    }
    setBusy(true);
    setError("");
    setHint("正在对照风格图的光线、场景和姿势生成，大约一两分钟，请不要重复点");
    try {
      await createWardrobeLook(ids, "");
      const data = await fetchWardrobeLooks();
      setLooks(data.items);
      setTab("looks");
      setHint("效果图已放到搭配，衣橱里的原衣服还在");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      setBusy(false);
    }
  }

  const shown = items.filter((item) => !part || item.part === part);

  return (
    <>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <Card className="mb-4 px-5 py-4">
        <div className="flex flex-wrap items-center gap-3">
          {referenceUrl ? (
            <img src={referenceUrl} alt="我" className="h-16 w-16 rounded-md object-cover" />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-md border border-[var(--line)] text-[12px] text-[var(--muted)]">无照片</div>
          )}
          <div className="min-w-0 flex-1 text-[13px] text-[var(--muted)]">
            先放一张自己的照片，试穿才会像你。
            {activeStyleName ? ` 当前风格：${activeStyleName}（学光线、场景、姿势）。` : " 去「风格」上传品牌图，试穿会学它的光线、场景和姿势。"}
            单件图可以直接加入。
          </div>
          <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => selfRef.current?.click()}>
            {referenceUrl ? "换我的照片" : "上传我的照片"}
          </button>
          <input ref={selfRef} type="file" accept="image/*" className="hidden" onChange={(e) => void onSelf(e.target.files?.[0])} />
        </div>
      </Card>

      <div className="mb-4 flex flex-wrap gap-1">
        {(
          [
            ["closet", "衣橱"],
            ["import", "导入"],
            ["styles", "风格"],
            ["looks", "搭配"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`rounded-md px-2.5 py-1.5 text-[13px] ${tab === id ? "bg-[var(--paper)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "import" ? (
        <div className="space-y-4">
          <Card title="直接加单件图" className="px-5 py-4">
            <p className="text-[13px] text-[var(--muted)]">商品图、平铺图、已经抠好的衣服，选图就能进衣橱，不用 AI。</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => directRef.current?.click()}>
                选图片
              </button>
              <input ref={directRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => onPickDirect(e.target.files)} />
              {drafts.length > 0 ? (
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onAddDirect()}>
                  {busy ? "加入中…" : "加入衣橱"}
                </button>
              ) : null}
            </div>
            {drafts.length > 0 ? (
              <ul className="mt-4 space-y-3">
                {drafts.map((item, index) => (
                  <li key={item.preview} className="flex flex-wrap items-center gap-3 text-[13px]">
                    <img src={item.preview} alt="" className="h-16 w-16 rounded-md object-contain bg-[var(--bg)]" />
                    <input
                      className="w-40 border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
                      value={item.name}
                      onChange={(e) => setDrafts((prev) => prev.map((row, i) => (i === index ? { ...row, name: e.target.value } : row)))}
                    />
                    <select
                      className="border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5"
                      value={item.part}
                      onChange={(e) => setDrafts((prev) => prev.map((row, i) => (i === index ? { ...row, part: e.target.value } : row)))}
                    >
                      {ITEM_PARTS.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.label}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>
          <Card title="从照片里拆衣服" className="px-5 py-4">
            <p className="text-[13px] text-[var(--muted)]">一张图里有好几件，或人穿着的，先识别再抠图。</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => importRef.current?.click()}>
                {busy ? "处理中…" : "选照片识别"}
              </button>
              <input ref={importRef} type="file" accept="image/*" className="hidden" onChange={(e) => void onAnalyze(e.target.files?.[0])} />
              {detected.length > 0 ? (
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onImport()}>
                  抠图并加入衣橱
                </button>
              ) : null}
            </div>
            {detected.length > 0 ? (
              <ul className="mt-4 space-y-2 text-[13px]">
                {detected.map((item, index) => (
                  <li key={`${item.name}-${index}`} className="flex items-center gap-3">
                    <input type="checkbox" checked={chosen[index] || false} onChange={() => setChosen((prev) => prev.map((on, i) => (i === index ? !on : on)))} />
                    <span>{item.name}</span>
                    <span className="text-[var(--muted)]">{PARTS.find((row) => row.id === item.part)?.label || item.part}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </Card>
        </div>
      ) : null}

      {tab === "styles" ? (
        <div className="space-y-4">
          <Card title="学一个品牌风格" className="px-5 py-4">
            <p className="text-[13px] text-[var(--muted)]">上传 1～4 张品牌图。试穿只学它的光线、场景和类似姿势，衣服还是用你在衣橱里选的。</p>
            <label className="mt-3 block text-[13px]">
              <span className="mb-1 block text-[var(--muted)]">品牌名</span>
              <input className="w-full max-w-xs border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5" value={styleName} onChange={(e) => setStyleName(e.target.value)} placeholder="比如 COS、优衣库" />
            </label>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => styleRef.current?.click()}>
                选品牌图
              </button>
              <input ref={styleRef} type="file" accept="image/*" multiple className="hidden" onChange={(e) => onPickStyle(e.target.files)} />
              {styleDrafts.length > 0 ? (
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onSaveStyle()}>
                  {busy ? "保存中…" : "保存风格"}
                </button>
              ) : null}
            </div>
            {styleDrafts.length > 0 ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {styleDrafts.map((item) => (
                  <img key={item.preview} src={item.preview} alt="" className="h-16 w-16 rounded-md object-cover" />
                ))}
              </div>
            ) : null}
          </Card>
          {styles.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">还没有风格。先保存一套，再点「使用」。</p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {styles.map((item) => (
                <Card key={item.id} className="px-4 py-3">
                  <div className="flex flex-wrap gap-2">
                    {item.image_urls.map((url) => (
                      <button key={url} type="button" onClick={() => setPreview({ kind: "photo", src: url, title: item.name })}>
                        <img src={url} alt="" className="h-20 w-20 rounded-md object-cover" />
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 text-[13px] font-medium">{item.name}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={`border px-2 py-1 text-[13px] ${item.active ? "border-[var(--text)] bg-[var(--bg)]" : "border-[var(--line)] bg-[var(--paper)]"}`}
                      disabled={busy}
                      onClick={() =>
                        setWardrobeStyleActive(item.id, !item.active)
                          .then((data) => {
                            setStyles(data.items);
                            setActiveStyleName(data.items.find((row) => row.active)?.name || "");
                            setHint(data.active_id ? `已改用 ${item.name}` : "已取消风格");
                          })
                          .catch((err: Error) => setError(err.message))
                      }
                    >
                      {item.active ? "使用中" : "使用"}
                    </button>
                    <button type="button" className="text-[13px] text-[var(--muted)]" onClick={() => setAskStyleId(item.id)}>
                      删除
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {tab === "closet" ? (
        <div>
          <div className="mb-3 flex flex-wrap gap-1">
            {PARTS.map((item) => (
              <button
                key={item.id || "all"}
                type="button"
                className={`rounded-md px-2.5 py-1.5 text-[13px] ${part === item.id ? "bg-[var(--paper)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
                onClick={() => setPart(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">还没有衣服。去「导入」，单件图可以直接加。</p>
          ) : (
            <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-4">
              {shown.map((item) => (
                <Card key={item.id} className="px-3 py-3">
                  <button
                    type="button"
                    className="flex h-44 w-full items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]"
                    onClick={() => setPreview({ kind: "item", item })}
                  >
                    {item.cutout_url || item.original_url ? (
                      <img src={item.cutout_url || item.original_url} alt={item.name} className="max-h-full max-w-full object-contain" />
                    ) : null}
                  </button>
                  <div className="mt-3 text-[13px] font-medium">{item.name}</div>
                  <div className="text-[12px] text-[var(--muted)]">{item.part_label}</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-2 py-1 text-[13px] disabled:opacity-50" disabled={busy} onClick={() => void onTryOn([item.id])}>
                      生成试穿
                    </button>
                    <button
                      type="button"
                      className={`border px-2 py-1 text-[13px] ${picked.includes(item.id) ? "border-[var(--text)] bg-[var(--bg)]" : "border-[var(--line)] bg-[var(--paper)]"}`}
                      onClick={() => setPicked((prev) => (prev.includes(item.id) ? prev.filter((id) => id !== item.id) : [...prev, item.id]))}
                    >
                      {picked.includes(item.id) ? "已选" : "选来搭配"}
                    </button>
                    <button type="button" className="text-[13px] text-[var(--muted)]" onClick={() => setAskId(item.id)}>
                      删除
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {tab === "looks" ? (
        <div>
          <Card className="mb-4 px-5 py-4">
            <p className="text-[13px] text-[var(--muted)]">
              在衣橱里点「选来搭配」，一件就能试穿，多件就是整套。点「姿势裂变」会按这张图再出不同姿势，张数自己选，最多 3 张。也可以自己上传一张图来裂变。
              {activeStyleName ? ` 会学「${activeStyleName}」的光线、场景和姿势，衣服用你选的。` : ""}
            </p>
            <div className="mt-3 text-[13px]">已选 {picked.length} 件</div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy || picked.length < 1} onClick={() => void onTryOn(picked)}>
                生成搭配
              </button>
              <label className="flex items-center gap-2 text-[13px] text-[var(--muted)]">
                裂变张数
                <select
                  className="border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[var(--text)]"
                  value={varyCount}
                  disabled={busy}
                  onChange={(e) => setVaryCount(Number(e.target.value))}
                >
                  <option value={1}>1 张</option>
                  <option value={2}>2 张</option>
                  <option value={3}>3 张</option>
                </select>
              </label>
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => varyRef.current?.click()}>
                {busy ? "裂变中…" : "上传图片做姿势裂变"}
              </button>
              <input ref={varyRef} type="file" accept="image/*" className="hidden" onChange={(e) => void onVary(undefined, e.target.files?.[0])} />
            </div>
          </Card>
          {looks.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">还没有搭配图。</p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {looks.map((look) => (
                <Card key={look.id} className="px-3 py-3">
                  {look.image_url ? (
                    <button
                      type="button"
                      className="flex h-52 w-full items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]"
                      onClick={() => {
                        setLookFocusId(null);
                        setStyleFocusSrc("");
                        setPreview({ kind: "look", look });
                      }}
                    >
                      <img src={look.image_url} alt={look.title} className="max-h-full max-w-full object-contain" />
                    </button>
                  ) : null}
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <div className="text-[13px]">{look.title}</div>
                    <div className="flex shrink-0 gap-2">
                      <button type="button" className="text-[13px] text-[var(--muted)] disabled:opacity-50" disabled={busy} onClick={() => void onVary(look.id)}>
                        姿势裂变
                      </button>
                      <button
                        type="button"
                        className="text-[13px] text-[var(--muted)]"
                        onClick={() =>
                          deleteWardrobeLook(look.id)
                            .then(() => setLooks((prev) => prev.filter((item) => item.id !== look.id)))
                            .catch((err: Error) => setError(err.message))
                        }
                      >
                        删除
                      </button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {askId !== null ? (
        <ConfirmModal
          title="删除衣服"
          message="从衣橱里拿掉这件？"
          onConfirm={() => {
            deleteWardrobeItem(askId)
              .then(() => {
                setItems((prev) => prev.filter((item) => item.id !== askId));
                setPicked((prev) => prev.filter((id) => id !== askId));
                setAskId(null);
              })
              .catch((err: Error) => {
                setError(err.message);
                setAskId(null);
              });
          }}
          onClose={() => setAskId(null)}
        />
      ) : null}

      {preview ? (
        <Modal title={preview.kind === "item" ? preview.item.name : preview.kind === "look" ? preview.look.title : preview.title} wide={preview.kind === "look"} onClose={() => setPreview(null)}>
          {preview.kind === "item" ? (
            <div>
              <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
                {preview.item.cutout_url || preview.item.original_url ? (
                  <img src={preview.item.cutout_url || preview.item.original_url} alt={preview.item.name} className="max-h-[70vh] max-w-full object-contain" />
                ) : null}
              </div>
              <p className="mt-3 text-[13px] text-[var(--muted)]">
                {preview.item.part_label}
                {preview.item.color ? ` · ${preview.item.color}` : ""}
                {preview.item.tags.length ? ` · ${preview.item.tags.join("、")}` : ""}
              </p>
            </div>
          ) : null}
          {preview.kind === "look" ? (
            <LookPreview
              look={preview.look}
              items={items}
              focusId={lookFocusId}
              styleFocusSrc={styleFocusSrc}
              busy={busy}
              onFocus={setLookFocusId}
              onFocusStyle={setStyleFocusSrc}
              onVary={() => void onVary(preview.look.id)}
              onRemake={(prompt) => void onRemake(preview.look.id, prompt)}
            />
          ) : null}
          {preview.kind === "photo" ? (
            <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
              <img src={preview.src} alt={preview.title} className="max-h-[70vh] max-w-full object-contain" />
            </div>
          ) : null}
        </Modal>
      ) : null}

      {askStyleId !== null ? (
        <ConfirmModal
          title="删除风格"
          message="删掉这个品牌风格？"
          onConfirm={() => {
            deleteWardrobeStyle(askStyleId)
              .then(() => {
                setStyles((prev) => prev.filter((item) => item.id !== askStyleId));
                setAskStyleId(null);
                return reload();
              })
              .catch((err: Error) => {
                setError(err.message);
                setAskStyleId(null);
              });
          }}
          onClose={() => setAskStyleId(null)}
        />
      ) : null}
    </>
  );
}
