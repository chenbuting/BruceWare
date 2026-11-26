import { File, FileText, Folder, Image as ImageIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { useLocation } from "react-router-dom";

import {
  askKbLibraryStream,
  createKbFolder,
  createKbLibrary,
  deleteKbDocument,
  deleteKbFolder,
  deleteKbLibrary,
  deleteKbSession,
  deleteKbWiki,
  fetchKbDocument,
  fetchKbDocumentAssets,
  fetchKbDocumentChunks,
  fetchKbDocumentText,
  fetchKbReadyText,
  fetchKbDocuments,
  fetchKbFolders,
  fetchKbLibraries,
  fetchKbReadySkill,
  downloadKbReadyDraft,
  fetchKbProgress,
  fetchKbSession,
  fetchKbSessions,
  fetchKbWikis,
  generateKbWiki,
  kbAssetFileUrl,
  kbDocumentFileUrl,
  kbDocumentReadyFileUrl,
  kbDocumentImagesPdfUrl,
  recognizeKbAsset,
  renameKbFolder,
  renameKbSession,
  processKbDocument,
  reindexKbDocument,
  saveKbAssetOcr,
  saveKbAssetsBatch,
  saveKbImageGroups,
  saveKbChunk,
  saveKbStage,
  saveKbWiki,
  updateKbDocument,
  updateKbLibrary,
  updateKbLibraryPolicy,
  uploadKbDocument,
} from "@/api/client";
import type { KbAskKind, KbAskResult, KbChunk, KbCleanRule, KbDocAsset, KbDocFlow, KbDocument, KbEvidenceMode, KbFolder, KbImageGroup, KbLibrary, KbQuality, KbSession, KbVisionEngine, KbWikiList } from "@/api/types";
import { answerHasAsset, KbAnswerContent } from "@/components/KbAnswerContent";
import { Drawer } from "@/components/Drawer";
import { ImageLightbox } from "@/components/ImageLightbox";
import { ConfirmModal, Modal } from "@/components/Modal";
import { PdfPreview } from "@/components/PdfPreview";
import { DocModuleBar, FlowModulePanel, isFlowPane, type DocPane, type FlowPane } from "@/pages/kb/DocModules";

const inputClass = "border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px]";
const btnClass = "border border-[var(--line)] bg-[var(--paper)] px-2.5 py-1.5 text-[13px] disabled:opacity-50";

function docIcon(item: KbDocument) {
  if (item.preview === "image") return { Icon: ImageIcon, color: "text-sky-500" };
  if (item.preview === "pdf" || item.preview === "text") return { Icon: FileText, color: "text-slate-500" };
  return { Icon: File, color: "text-[var(--muted)]" };
}

function childFolders(items: KbFolder[], parentId: number | null) {
  return items.filter((item) => item.parent_id === parentId);
}

function evidenceLabel(mode: KbEvidenceMode) {
  return mode === "loose" ? "宽松概述" : "严格出处";
}

function vectorBadge(state?: KbDocument["vector_state"]) {
  if (state === "ready") return <span className="shrink-0 text-[12px] text-[var(--ok)]">已向量</span>;
  if (state === "stale") return <span className="shrink-0 text-[12px] text-amber-800">待重算</span>;
  return <span className="shrink-0 text-[12px] text-[var(--muted)]">未向量</span>;
}

/** 资料行里的状态：小圆点加文字。 */
function vectorStateBadge(state?: KbDocument["vector_state"]) {
  if (state === "ready") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--ok)]">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)]" />已向量
      </span>
    );
  }
  if (state === "stale") {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11.5px] text-amber-700">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-600" />待重算
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--muted)]">
      <span className="h-1.5 w-1.5 rounded-full bg-[var(--line)]" />未向量
    </span>
  );
}

function shortDate(raw?: string) {
  const text = (raw || "").trim();
  if (text.length >= 10) return text.slice(5, 10);
  return text || "—";
}

function tagList(raw?: string) {
  const text = (raw || "").trim();
  if (!text) return [];
  if (text.startsWith("[")) {
    try {
      const data = JSON.parse(text);
      if (Array.isArray(data)) return data.map((item) => String(item).trim()).filter(Boolean);
    } catch {
      /* 不是合法 JSON，按逗号拆 */
    }
  }
  return text
    .split(/[,，]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

type RowMenuItem = {
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
};

/** 资料 / 提问 的视图切换，放在工作区头部。 */
function ViewSwitch({ tab, onChange }: { tab: "files" | "ask"; onChange: (next: "files" | "ask") => void }) {
  return (
    <div className="flex shrink-0 overflow-hidden rounded-md border border-[var(--line)] text-[13px]">
      <button
        type="button"
        className={`px-3 py-1 ${tab === "files" ? "bg-[var(--bg)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
        onClick={() => onChange("files")}
      >
        资料
      </button>
      <button
        type="button"
        className={`border-l border-[var(--line)] px-3 py-1 ${tab === "ask" ? "bg-[var(--bg)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
        onClick={() => onChange("ask")}
      >
        提问
      </button>
    </div>
  );
}

/** 行末的「⋯」菜单。点空白、滚动或按 Esc 关掉。 */
function RowMenu({ items }: { items: RowMenuItem[] }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopImmediatePropagation();
      close();
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  function toggle(event: ReactMouseEvent) {
    event.stopPropagation();
    const rect = btnRef.current?.getBoundingClientRect();
    if (rect) setPos({ top: rect.bottom + 4, left: Math.max(8, rect.right - 152) });
    setOpen((value) => !value);
  }

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        className="px-1.5 py-0.5 text-[15px] leading-none text-[var(--muted)] hover:text-[var(--text)]"
        aria-label="更多操作"
        onClick={toggle}
      >
        ⋯
      </button>
      {open ? (
        <div
          className="fixed z-[60] w-36 border border-[var(--line)] bg-[var(--paper)] py-1 shadow-lg"
          style={{ top: pos.top, left: pos.left }}
          onClick={(event) => event.stopPropagation()}
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              disabled={item.disabled}
              className={`block w-full px-3 py-1.5 text-left text-[13px] hover:bg-[var(--hover)] disabled:opacity-40 ${item.danger ? "text-[var(--err)]" : ""}`}
              onClick={() => {
                setOpen(false);
                item.onClick();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </>
  );
}

const ASK_TURN_LIMIT = 6;

type AskTurn = {
  question: string;
  result: KbAskResult;
  streaming?: boolean;
};

type SessionDraft = {
  key: string;
  sessionId: number | null;
  turns: AskTurn[];
  asking: boolean;
  question: string;
};

type AskJob = {
  key: string;
  abort: AbortController;
  question: string;
  libraryId: number;
};

function emptyDraft(key: string, sessionId: number | null = null): SessionDraft {
  return { key, sessionId, turns: [], asking: false, question: "" };
}

function draftKey(sessionId: number | null, localId = 0) {
  return sessionId != null ? `s:${sessionId}` : `n:${localId}`;
}

/** 这次回答带上的相关图，用来直接画在回答里。 */
function relatedAskImages(result: KbAskResult) {
  return result.citations.flatMap((hit) => (hit.images || []).map((img) => ({ ...img, docId: hit.id })));
}

/** 一问一答，聊天气泡：问题靠右，回答靠左。 */
function MaterialFiles({
  turn,
  onOpenCitation,
}: {
  turn: AskTurn;
  onOpenCitation: (id: number) => void;
}) {
  const [zoom, setZoom] = useState<{ items: { src: string; alt: string }[]; index: number } | null>(null);
  return (
    <div className="mt-3 space-y-4">
      {turn.result.citations.map((hit) => {
        const pictures = hit.images || [];
        const items = pictures.map((img) => ({ src: img.url || kbAssetFileUrl(img.id), alt: img.alt || hit.title }));
        return (
          <div key={hit.id}>
            <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
              <button type="button" className="underline" onClick={() => onOpenCitation(hit.id)}>
                {hit.title}
              </button>
              <a className="text-[var(--muted)] underline" href={kbDocumentFileUrl(hit.id)} target="_blank" rel="noreferrer">
                打开原件
              </a>
              {pictures.length ? (
                <a className="text-[var(--muted)] underline" href={kbDocumentImagesPdfUrl(hit.id)} target="_blank" rel="noreferrer">
                  合成 PDF
                </a>
              ) : null}
            </div>
            {pictures.length ? (
              <div className="flex flex-wrap gap-2">
                {pictures.map((img, index) => (
                  <button key={img.id} type="button" title={`${img.alt || "图"}，点图放大`} onClick={() => setZoom({ items, index })}>
                    <img src={img.url || kbAssetFileUrl(img.id)} alt={img.alt} className="max-h-28 w-auto cursor-zoom-in rounded border border-[var(--line)] object-contain" />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-[12px] text-[var(--muted)]">这份没有抽出图。</p>
            )}
          </div>
        );
      })}
      {zoom ? <ImageLightbox items={zoom.items} index={zoom.index} onClose={() => setZoom(null)} onIndex={(index) => setZoom({ ...zoom, index })} /> : null}
    </div>
  );
}

function AskTurnView({
  turn,
  isLast,
  onOpenCitation,
  onOpenSources,
}: {
  turn: AskTurn;
  isLast: boolean;
  onOpenCitation: (id: number) => void;
  onOpenSources: () => void;
}) {
  const images = relatedAskImages(turn.result).filter((img) => !answerHasAsset(turn.result.answer, img.id));
  const [zoom, setZoom] = useState<number | null>(null);
  const zoomItems = images.map((img) => ({ src: img.url || kbAssetFileUrl(img.id), alt: img.alt }));
  const searchLabel = turn.result.used_vector ? "关键词 + 向量" : turn.result.used_vector === false ? "关键词" : "";
  const citations = turn.result.citations;
  const shown = citations.slice(0, 4);
  return (
    <div className="mb-7">
      <div className="mb-2 flex gap-3">
        <span className="w-9 shrink-0 pt-0.5 text-[11px] text-[var(--muted)]">你问</span>
        <p className="min-w-0 flex-1 whitespace-pre-wrap text-[13.5px] font-medium leading-6">{turn.question}</p>
      </div>
      <div className="flex gap-3">
        <span className="w-9 shrink-0 pt-0.5 text-[11px] text-[var(--ok)]">对证</span>
        <div className="min-w-0 flex-1">
          {turn.result.ask_kind === "checklist" ? (
            <p className="mb-1 text-[12px] text-[var(--muted)]">核对清单</p>
          ) : null}
          {turn.result.ask_kind === "materials" ? <p className="mb-1 text-[12px] text-[var(--muted)]">拿资料</p> : null}
          <div className="kb-read">
            <KbAnswerContent
              text={turn.result.answer || (turn.streaming ? "在找资料…" : "")}
              onOpenAsset={(assetId) => {
                const hit = citations.find((item) => (item.images || []).some((img) => img.id === assetId));
                if (hit) onOpenCitation(hit.id);
              }}
            />
          </div>
          {turn.streaming ? <span className="mt-1 inline-block animate-pulse text-[var(--muted)]">▍</span> : null}
          {!turn.streaming && turn.result.ask_kind === "materials" ? <MaterialFiles turn={turn} onOpenCitation={onOpenCitation} /> : null}
          {!turn.streaming && turn.result.ask_kind === "materials" && searchLabel ? (
            <p className="mt-2 text-[12px] text-[var(--muted)]">{searchLabel}</p>
          ) : null}
          {!turn.streaming && turn.result.ask_kind !== "materials" && images.length ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {images.map((img, index) => (
                <button key={img.id} type="button" className="block text-left" title="点图放大" onClick={() => setZoom(index)}>
                  <img
                    src={img.url || kbAssetFileUrl(img.id)}
                    alt={img.alt}
                    className="max-h-28 w-auto cursor-zoom-in rounded border border-[var(--line)] object-contain"
                  />
                </button>
              ))}
              {zoom != null ? <ImageLightbox items={zoomItems} index={zoom} onClose={() => setZoom(null)} onIndex={setZoom} /> : null}
            </div>
          ) : null}
          {!turn.streaming && turn.result.ask_kind !== "materials" && (citations.length || searchLabel || turn.result.wiki_update_hint) ? (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-dashed border-[var(--line)] pt-2.5 text-[11.5px] text-[var(--muted)]">
              {citations.length ? <span>本轮用到</span> : null}
              {shown.map((hit, index) => (
                <button
                  key={hit.id}
                  type="button"
                  className="inline-flex h-6 max-w-[240px] items-center gap-1.5 rounded border border-[var(--line)] bg-[var(--paper)] px-2 hover:border-[#bfd2c7] hover:bg-[var(--bg)]"
                  onClick={() => onOpenCitation(hit.id)}
                >
                  <span className="shrink-0 font-mono text-[10px] text-[var(--ok)]">资料{index + 1}</span>
                  <span className="truncate">{hit.title}</span>
                </button>
              ))}
              {isLast && citations.length > shown.length ? (
                <button type="button" className="underline hover:text-[var(--text)]" onClick={onOpenSources}>
                  全部 {citations.length} 条出处
                </button>
              ) : null}
              {searchLabel ? <span>{searchLabel}</span> : null}
              {turn.result.wiki_update_hint ? <span>{turn.result.wiki_update_hint}</span> : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function askKindHint(kind: KbAskKind) {
  if (kind === "checklist") {
    return "资料多、文件很长时 AI 看不全，所以只对证本轮抽到的。核对清单：好几项一条条对照时用，只标本轮命中/未命中，不替你下合不合格的结论。";
  }
  if (kind === "materials") {
    return "拿资料：按语义和向量找。财报这种别的叫法也能对上。问了年份就只给这一年。不看严格或宽松，也不写成回答。";
  }
  return "资料多、文件很长时 AI 看不全，所以只对证本轮抽到的。回答：问有没有、是多少、是什么，或让它说明整理；只根据本轮见到的说。";
}

function linkHint(choice: "" | "on" | "off", libraryOn: boolean, hops: number) {
  const on = choice === "" ? libraryOn : choice === "on";
  if (!on) return "这次不跨文件再查，只搜一轮。";
  return `这次会按原文里的人名、编号再查，最多 ${hops} 跳，够了就停。`;
}

function evidenceHint(mode: "" | KbEvidenceMode, libraryMode: KbEvidenceMode = "strict") {
  if (!mode) {
    return `出处规则跟库走，当前是${evidenceLabel(libraryMode)}。`;
  }
  if (mode === "loose") {
    return "宽松：可以【推断】，须核对原文。【确凿】绿、【推断】黄、【缺失】红、【冲突】紫。";
  }
  return "严格：只标【确凿】或【缺失】，不推断。【确凿】绿、【缺失】红、【冲突】紫。";
}

/** 知识库：整理资料，并按当前库提问 */
export function KbPage() {
  const location = useLocation();
  const uploadRef = useRef<HTMLInputElement>(null);
  const askBottomRef = useRef<HTMLDivElement>(null);
  const jobsRef = useRef<Map<string, AskJob>>(new Map());
  const draftsRef = useRef<Record<string, SessionDraft>>({ "n:0": emptyDraft("n:0") });
  const currentKeyRef = useRef("n:0");
  const libraryIdRef = useRef<number | null>(null);
  const folderIdRef = useRef<number | null>(null);
  const previewRef = useRef<KbDocument | null>(null);
  const newDraftSeq = useRef(0);
  const [drafts, setDrafts] = useState<Record<string, SessionDraft>>({ "n:0": emptyDraft("n:0") });
  const [currentKey, setCurrentKey] = useState("n:0");
  const visionStopRef = useRef(false);
  const visionBusyRef = useRef(false);
  const visionDocRef = useRef<number | null>(null);
  const [libraries, setLibraries] = useState<KbLibrary[]>([]);
  const [libraryId, setLibraryId] = useState<number | null>(null);
  const [folders, setFolders] = useState<KbFolder[]>([]);
  const [folderId, setFolderId] = useState<number | null>(null);
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [meter, setMeter] = useState<{ text: string; current: number; total: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<KbDocument | null>(null);
  const [previewText, setPreviewText] = useState("");
  const [assetTick, setAssetTick] = useState(0);
  const [visionDocId, setVisionDocId] = useState<number | null>(null);
  const [libName, setLibName] = useState("");
  const [folderName, setFolderName] = useState("");
  const [renameFolder, setRenameFolder] = useState<KbFolder | null>(null);
  const [renameFolderTo, setRenameFolderTo] = useState("");
  const [editDoc, setEditDoc] = useState<KbDocument | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editTags, setEditTags] = useState("");
  const [askDeleteLib, setAskDeleteLib] = useState(false);
  const [askDeleteFolder, setAskDeleteFolder] = useState<KbFolder | null>(null);
  const [askDeleteDoc, setAskDeleteDoc] = useState<KbDocument | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingReady, setPendingReady] = useState(false);
  const [pendingDraft, setPendingDraft] = useState<File | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [plainSkill, setPlainSkill] = useState("");
  const [carefulSkill, setCarefulSkill] = useState("");
  const uploadReady = useRef(false);
  const uploadKind = useRef<"plain" | "layout" | "copy">("plain");
  const readyOriginalRef = useRef<HTMLInputElement>(null);
  const readyDraftRef = useRef<HTMLInputElement>(null);
  const [readyOriginalFile, setReadyOriginalFile] = useState<File | null>(null);
  const [readyDraftFile, setReadyDraftFile] = useState<File | null>(null);
  const [uploadTags, setUploadTags] = useState("");
  const [manageLib, setManageLib] = useState(false);
  const [question, setQuestion] = useState("");
  const [onlyFolder, setOnlyFolder] = useState(false);
  const [askTurns, setAskTurns] = useState<AskTurn[]>([]);
  const [sessions, setSessions] = useState<KbSession[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [renameSession, setRenameSession] = useState<KbSession | null>(null);
  const [renameSessionTo, setRenameSessionTo] = useState("");
  const [askDeleteSession, setAskDeleteSession] = useState<KbSession | null>(null);
  const [asking, setAsking] = useState(false);
  const [askMode, setAskMode] = useState<"" | KbEvidenceMode>("");
  const [askLink, setAskLink] = useState<"" | "on" | "off">("");
  const [askKind, setAskKind] = useState<KbAskKind>("answer");
  const [wikiEnabled, setWikiEnabled] = useState(false);
  const [wikiLearn, setWikiLearn] = useState(false);
  const [visionEnabled, setVisionEnabled] = useState(false);
  const [visionEngine, setVisionEngine] = useState<KbVisionEngine>("vision");
  const [libMode, setLibMode] = useState<KbEvidenceMode>("strict");
  const [libRule, setLibRule] = useState("");
  const [linkEnabled, setLinkEnabled] = useState(false);
  const [linkHops, setLinkHops] = useState("3");
  const [wikiList, setWikiList] = useState<KbWikiList | null>(null);
  const [wikiQ, setWikiQ] = useState("");
  const [wikiStale, setWikiStale] = useState("");
  const [wikiSort, setWikiSort] = useState("updated_at");
  const [wikiOrder, setWikiOrder] = useState("desc");
  const [wikiPage, setWikiPage] = useState(1);
  const [pageTab, setPageTab] = useState<"files" | "ask">("files");
  // 右栏：卷宗（预览）或本轮出处。readerBack 控制「返回出处」。
  const [readerSources, setReaderSources] = useState(false);
  const [readerBack, setReaderBack] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"basic" | "answer" | "index" | "vision" | "wiki" | "summary">("basic");
  const [railOpen, setRailOpen] = useState(false);

  const library = libraries.find((item) => item.id === libraryId) || null;
  libraryIdRef.current = libraryId;
  folderIdRef.current = folderId;
  previewRef.current = preview;

  async function loadLibraries(preferId?: number | null) {
    const data = await fetchKbLibraries();
    setLibraries(data.items);
    const next = data.items.find((item) => item.id === preferId) || data.items[0] || null;
    setLibraryId(next ? next.id : null);
    return next;
  }

  async function loadFolders(id: number) {
    const data = await fetchKbFolders(id);
    setFolders(data.items);
  }

  async function loadDocs(id: number, currentFolder: number | null, q = query, tagText = tag) {
    const data = await fetchKbDocuments(id, q.trim() || tagText.trim() ? null : currentFolder, q, tagText);
    setDocs(data.items);
  }

  async function reloadAll(id?: number | null, currentFolder?: number | null) {
    const lib = await loadLibraries(id ?? libraryId);
    if (!lib) {
      setFolders([]);
      setDocs([]);
      return;
    }
    await loadFolders(lib.id);
    await loadDocs(lib.id, currentFolder === undefined ? folderId : currentFolder);
  }

  useEffect(() => {
    if (location.pathname !== "/m/kb") return;
    reloadAll().catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  useEffect(() => {
    if (libraryId == null) {
      setSessions([]);
      return;
    }
    fetchKbSessions(libraryId)
      .then((data) => setSessions(data.items))
      .catch((err: Error) => setError(err.message));
  }, [libraryId]);

  useEffect(() => {
    if (!preview || preview.preview !== "text") {
      setPreviewText("");
      return;
    }
    fetchKbDocumentText(preview.id)
      .then((data) => setPreviewText(data.text))
      .catch((err: Error) => setPreviewText(err.message));
  }, [preview]);

  // 右栏打开时按 Esc 收起；上面压着弹窗或抽屉时先交给它们处理。
  const overlayOpen =
    manageLib ||
    importOpen ||
    renameFolder != null ||
    editDoc != null ||
    renameSession != null ||
    askDeleteSession != null ||
    askDeleteLib ||
    askDeleteFolder != null ||
    askDeleteDoc != null ||
    pendingFile != null;

  useEffect(() => {
    if ((!preview && !readerSources) || overlayOpen || optionsOpen) return;
    if (document.querySelector('[data-overlay="modal"], [data-overlay="drawer"]')) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") closeReader();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview, readerSources, overlayOpen, optionsOpen]);

  // 点空白或按 Esc 收起提问选项。
  useEffect(() => {
    if (!optionsOpen) return;
    const close = () => setOptionsOpen(false);
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopImmediatePropagation();
      close();
    };
    window.addEventListener("click", close);
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("keydown", onKey, true);
    };
  }, [optionsOpen]);

  const crumbs = useMemo(() => {
    const chain: KbFolder[] = [];
    let current = folderId;
    while (current != null) {
      const found = folders.find((item) => item.id === current);
      if (!found) break;
      chain.unshift(found);
      current = found.parent_id;
    }
    return chain;
  }, [folderId, folders]);

  async function recognizeAll(item: KbDocument) {
    if (visionBusyRef.current) {
      if (visionDocRef.current === item.id) {
        visionStopRef.current = true;
        setHint("正在停止，等这张认完…");
      }
      return;
    }
    visionBusyRef.current = true;
    visionDocRef.current = item.id;
    visionStopRef.current = false;
    setVisionDocId(item.id);
    setError("");
    setHint("正在列出图片…");
    try {
      const data = await fetchKbDocumentAssets(item.id);
      const pending = data.items.filter((one) => !one.caption?.trim() && !one.keywords?.trim() && !one.ocr_text?.trim());
      if (!data.items.length) {
        setError("这份资料没有可认的图");
        return;
      }
      if (!pending.length) {
        setHint("这些图都认过了");
        return;
      }
      let done = 0;
      const total = pending.length;
      setHint(`识图 ${done} / ${total}`);
      setAssetTick((n) => n + 1);
      for (const asset of pending) {
        if (visionStopRef.current) {
          setHint(`已停止，已认 ${done} / ${total}`);
          return;
        }
        const row = await recognizeKbAsset(asset.id);
        done += 1;
        setHint(row.vector_hint ? `识图 ${done} / ${total}。${row.vector_hint}` : `识图 ${done} / ${total}`);
        setAssetTick((n) => n + 1);
      }
      setHint(`已认完 ${done} 张`);
      try {
        applyDoc(await fetchKbDocument(item.id));
      } catch {
        /* 徽章刷新失败不影响识图结果 */
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "识图失败");
    } finally {
      visionStopRef.current = false;
      visionBusyRef.current = false;
      visionDocRef.current = null;
      setVisionDocId(null);
    }
  }

  function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setHint("");
    task()
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }

  useEffect(() => {
    askBottomRef.current?.scrollIntoView({ block: "end" });
  }, [askTurns, asking]);

  function isAskAborted(err: unknown) {
    return err instanceof DOMException
      ? err.name === "AbortError"
      : err instanceof Error && (err.name === "AbortError" || /aborted|abort/i.test(err.message));
  }

  function publishDrafts() {
    setDrafts({ ...draftsRef.current });
  }

  function updateDraft(key: string, updater: (draft: SessionDraft) => SessionDraft) {
    const prev = draftsRef.current[key] || emptyDraft(key);
    const next = updater(prev);
    draftsRef.current = { ...draftsRef.current, [key]: next };
    publishDrafts();
    if (currentKeyRef.current === key) {
      setAskTurns(next.turns);
      setAsking(next.asking);
      setSessionId(next.sessionId);
    }
  }

  function persistView() {
    const key = currentKeyRef.current;
    const prev = draftsRef.current[key] || emptyDraft(key, sessionId);
    draftsRef.current[key] = {
      ...prev,
      question,
      sessionId,
      turns: prev.asking ? prev.turns : askTurns,
      asking: prev.asking,
    };
  }

  function showDraft(key: string) {
    const draft = draftsRef.current[key] || emptyDraft(key);
    currentKeyRef.current = key;
    setCurrentKey(key);
    setSessionId(draft.sessionId);
    setAskTurns(draft.turns);
    setAsking(draft.asking);
    setQuestion(draft.question);
  }

  function abortJob(key: string, restoreQuestion: boolean) {
    const job = jobsRef.current.get(key);
    jobsRef.current.delete(key);
    job?.abort.abort();
    updateDraft(key, (draft) => ({
      ...draft,
      asking: false,
      turns: draft.turns.filter((item) => !item.streaming),
    }));
    if (restoreQuestion && job && currentKeyRef.current === key) {
      setQuestion((current) => (current.trim() ? current : job.question));
    }
  }

  function stopAllAsks() {
    for (const job of jobsRef.current.values()) {
      job.abort.abort();
    }
    jobsRef.current.clear();
    draftsRef.current = { "n:0": emptyDraft("n:0") };
    publishDrafts();
    currentKeyRef.current = "n:0";
    setCurrentKey("n:0");
  }

  function adoptSession(oldKey: string, nextSessionId: number) {
    const newKey = draftKey(nextSessionId);
    const draft = draftsRef.current[oldKey];
    if (!draft) return newKey;
    const copy = { ...draftsRef.current };
    delete copy[oldKey];
    copy[newKey] = { ...draft, key: newKey, sessionId: nextSessionId };
    draftsRef.current = copy;
    const job = jobsRef.current.get(oldKey);
    jobsRef.current.delete(oldKey);
    if (job) {
      job.key = newKey;
      jobsRef.current.set(newKey, job);
    }
    publishDrafts();
    if (currentKeyRef.current === oldKey) {
      currentKeyRef.current = newKey;
      setCurrentKey(newKey);
      setSessionId(nextSessionId);
    }
    return newKey;
  }

  function onStopAsk() {
    abortJob(currentKeyRef.current, true);
    setError("");
    setHint("已停止提问");
  }

  function onAsk() {
    if (libraryId == null || asking) return;
    const text = question.trim();
    if (!text) return;
    const key = currentKeyRef.current;
    const history = askTurns.slice(-(ASK_TURN_LIMIT - 1)).map((turn) => ({
      question: turn.question,
      answer: turn.result.answer,
    }));
    const ctrl = new AbortController();
    const route = { key };
    jobsRef.current.set(key, { key, abort: ctrl, question: text, libraryId });
    setError("");
    setHint("");
    setQuestion("");
    updateDraft(key, (draft) => ({
      ...draft,
      asking: true,
      question: "",
      sessionId,
      turns: [
        ...draft.turns,
        {
          question: text,
          streaming: true,
          result: { answer: "", citations: [], used_llm: true, ask_kind: askKind },
        },
      ],
    }));
    askKbLibraryStream(
      libraryId,
      text,
      folderId,
      onlyFolder,
      askMode,
      history,
      sessionId,
      askKind,
      (event) => {
        if (!jobsRef.current.has(route.key)) return;
        updateDraft(route.key, (draft) => {
          const turns = [...draft.turns];
          let index = -1;
          for (let i = turns.length - 1; i >= 0; i -= 1) {
            if (turns[i].streaming && turns[i].question === text) {
              index = i;
              break;
            }
          }
          if (index < 0) return draft;
          const last = turns[index];
          turns[index] =
            event.type === "start"
              ? {
                  ...last,
                  result: {
                    ...last.result,
                    citations: event.citations,
                    used_vector: event.used_vector,
                    ask_kind: event.ask_kind || last.result.ask_kind,
                    evidence_mode: event.evidence_mode,
                  },
                }
              : { ...last, result: { ...last.result, answer: last.result.answer + event.text } };
          return { ...draft, turns };
        });
      },
      ctrl.signal,
      askLink,
    )
      .then(async (data) => {
        if (ctrl.signal.aborted || !jobsRef.current.has(route.key)) return;
        if (data.session_id && route.key.startsWith("n:")) {
          route.key = adoptSession(route.key, data.session_id);
        }
        updateDraft(route.key, (draft) => {
          const turns = [...draft.turns];
          let index = -1;
          for (let i = turns.length - 1; i >= 0; i -= 1) {
            if (turns[i].question === text) {
              index = i;
              break;
            }
          }
          const done = { question: text, result: data };
          if (index >= 0) turns[index] = done;
          else turns.push(done);
          return { ...draft, asking: false, sessionId: data.session_id ?? draft.sessionId, turns };
        });
        jobsRef.current.delete(route.key);
        if (libraryIdRef.current === libraryId) {
          const listed = await fetchKbSessions(libraryId);
          if (libraryIdRef.current === libraryId) setSessions(listed.items);
          try {
            await loadDocs(libraryId, folderIdRef.current);
            const open = previewRef.current;
            if (open) applyDoc(await fetchKbDocument(open.id));
          } catch {
            /* 徽章刷新失败不影响回答 */
          }
        }
      })
      .catch((err: Error) => {
        if (ctrl.signal.aborted || !jobsRef.current.has(route.key)) {
          if (currentKeyRef.current === route.key && isAskAborted(err)) {
            setQuestion((current) => (current.trim() ? current : text));
            setHint("已停止提问");
          }
          return;
        }
        jobsRef.current.delete(route.key);
        updateDraft(route.key, (draft) => ({
          ...draft,
          asking: false,
          turns: draft.turns.filter((item) => !item.streaming),
        }));
        if (isAskAborted(err)) {
          if (currentKeyRef.current === route.key) {
            setQuestion((current) => (current.trim() ? current : text));
            setHint("已停止提问");
          }
          return;
        }
        if (currentKeyRef.current === route.key) setError(err.message);
      });
  }

  function onNewAsk() {
    persistView();
    const cur = draftsRef.current[currentKeyRef.current];
    if (cur && cur.sessionId == null && !cur.asking && cur.turns.length === 0) {
      setQuestion("");
      setError("");
      setHint("");
      return;
    }
    newDraftSeq.current += 1;
    const key = draftKey(null, newDraftSeq.current);
    draftsRef.current[key] = emptyDraft(key);
    publishDrafts();
    showDraft(key);
    setError("");
    setHint("");
  }

  function onOpenSession(id: number) {
    persistView();
    const key = draftKey(id);
    const existing = draftsRef.current[key];
    currentKeyRef.current = key;
    setCurrentKey(key);
    setError("");
    if (existing) {
      setSessionId(id);
      setAskTurns(existing.turns);
      setAsking(existing.asking);
      setQuestion(existing.question);
      if (existing.asking) return;
    } else {
      setSessionId(id);
      setAsking(false);
    }
    fetchKbSession(id)
      .then((data) => {
        if (draftsRef.current[key]?.asking) return;
        updateDraft(key, (draft) => ({
          ...draft,
          sessionId: id,
          asking: false,
          turns: data.turns.map((item) => ({ question: item.question, result: item.result })),
        }));
        if (currentKeyRef.current === key) {
          setQuestion(draftsRef.current[key]?.question || "");
        }
      })
      .catch((err: Error) => {
        if (currentKeyRef.current === key) setError(err.message);
      });
  }

  function onOpenCitation(id: number) {
    setReaderSources(false);
    setReaderBack(true);
    const found = docs.find((item) => item.id === id);
    if (found) {
      setPreview(found);
      return;
    }
    fetchKbDocument(id)
      .then((item) => setPreview(item))
      .catch((err: Error) => setError(err.message));
  }

  function openDocFromRow(item: KbDocument) {
    setReaderSources(false);
    setReaderBack(false);
    setPreview(item);
  }

  function openSources() {
    const hits = askTurns[askTurns.length - 1]?.result.citations || [];
    if (!hits.length) return;
    setPreview(null);
    setReaderBack(false);
    setReaderSources(true);
  }

  function closeReader() {
    setPreview(null);
    setReaderSources(false);
    setReaderBack(false);
  }

  function onPickLibrary(id: number) {
    stopAllAsks();
    setLibraryId(id);
    setFolderId(null);
    setPreview(null);
    setReaderSources(false);
    setReaderBack(false);
    setAskTurns([]);
    setSessionId(null);
    setAsking(false);
    setQuestion("");
    run(async () => {
      await loadFolders(id);
      await loadDocs(id, null);
    });
  }

  function onOpenFolder(id: number | null) {
    setFolderId(id);
    setPreview(null);
    setReaderSources(false);
    setReaderBack(false);
    if (libraryId == null) return;
    run(async () => {
      await loadDocs(libraryId, id, "", "");
      setQuery("");
      setTag("");
    });
  }

  function onSearch() {
    if (libraryId == null) return;
    run(async () => {
      await loadDocs(libraryId, folderId);
    });
  }

  function onCreateLibrary() {
    const name = libName.trim() || "未命名库";
    run(async () => {
      const row = await createKbLibrary(name);
      setLibName("");
      setFolderId(null);
      await reloadAll(row.id, null);
      setHint("已建库");
    });
  }

  function onRenameLibrary() {
    if (!library) return;
    const name = libName.trim();
    if (!name) return;
    run(async () => {
      await updateKbLibrary(library.id, name, library.description);
      setLibName("");
      await loadLibraries(library.id);
      setHint("已改库名");
    });
  }

  function applyDoc(row: KbDocument) {
    setDocs((items) => items.map((item) => (item.id === row.id ? row : item)));
    setPreview((current) => (current?.id === row.id ? row : current));
  }

  async function loadWikis(page = wikiPage) {
    if (libraryId == null) return;
    const data = await fetchKbWikis(libraryId, { q: wikiQ, stale: wikiStale, sort: wikiSort, order: wikiOrder, page });
    setWikiList(data);
    setWikiPage(page);
  }

  function openManage() {
    setManageLib(true);
    setSettingsTab("basic");
    if (library) {
      setWikiEnabled(!!library.wiki_enabled);
      setWikiLearn(!!library.wiki_learn);
      setVisionEnabled(!!library.vision_enabled);
      setVisionEngine(library.vision_engine === "ocr" ? "ocr" : "vision");
      setLibMode(library.evidence_mode || "strict");
      setLibRule(library.rule || "");
      setLinkEnabled(!!library.link_enabled);
      setLinkHops(String(library.link_hops || 3));
    }
    setWikiPage(1);
    if (libraryId != null) {
      fetchKbWikis(libraryId, { q: wikiQ, stale: wikiStale, sort: wikiSort, order: wikiOrder, page: 1 })
        .then((data) => {
          setWikiList(data);
          setWikiPage(1);
        })
        .catch((err: Error) => setError(err.message));
    }
  }

  function onCreateFolder() {
    if (libraryId == null) return;
    const name = folderName.trim();
    if (!name) return;
    run(async () => {
      await createKbFolder(libraryId, name, folderId);
      setFolderName("");
      await loadFolders(libraryId);
      setHint("已建文件夹");
    });
  }

  function openImport() {
    uploadKind.current = "plain";
    setImportOpen(true);
    if (plainSkill && carefulSkill) return;
    Promise.all([fetchKbReadySkill("plain"), fetchKbReadySkill("careful")])
      .then(([plain, careful]) => {
        setPlainSkill(plain.text || "");
        setCarefulSkill(careful.text || "");
      })
      .catch((err: Error) => setError(err.message));
  }

  function copySkill(text: string) {
    if (!text) return;
    navigator.clipboard.writeText(text).then(() => setHint("规则已复制，可以贴给别的 AI。")).catch(() => setError("复制失败"));
  }

  function downloadSkill(text: string, name: string) {
    if (!text) return;
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
  }

  function pickUpload(ready: boolean) {
    uploadKind.current = "plain";
    uploadReady.current = ready;
    setImportOpen(false);
    uploadRef.current?.click();
  }

  function pickLayout(copy: boolean) {
    uploadKind.current = copy ? "copy" : "layout";
    setImportOpen(false);
    uploadRef.current?.click();
  }

  function startReadyImport() {
    const original = readyOriginalFile;
    const draft = readyDraftFile;
    if (!original || !draft) return;
    if (!draft.name.toLowerCase().endsWith(".docx")) {
      setError("改好的稿要是 Word");
      return;
    }
    setReadyOriginalFile(null);
    setReadyDraftFile(null);
    setImportOpen(false);
    run(async () => {
      try {
        await doUpload(original, false, true, draft);
      } catch (err) {
        const message = err instanceof Error ? err.message : "上传失败";
        if (message.includes("已有相同文件")) {
          setPendingFile(original);
          setPendingDraft(draft);
          setPendingReady(true);
          setError(message);
          return;
        }
        throw err;
      }
    });
  }

  function trackJob<T>(work: (job: string) => Promise<T>) {
    const job = newKbJob();
    setMeter({ text: "正在开始", current: 0, total: 0 });
    const started = Date.now();
    let stopped = false;
    let pending = false;
    const timer = window.setInterval(() => {
      if (pending || stopped) return;
      pending = true;
      fetchKbProgress(job)
        .then((row) => {
          if (!stopped) setMeter(row);
        })
        .catch(() => undefined)
        .finally(() => {
          pending = false;
        });
    }, 400);
    return work(job).finally(async () => {
      stopped = true;
      window.clearInterval(timer);
      const wait = 700 - (Date.now() - started);
      if (wait > 0) await new Promise((resolve) => window.setTimeout(resolve, wait));
      setMeter(null);
    });
  }

  async function doUpload(file: File, force: boolean, ready: boolean, draft: File | null = null) {
    if (libraryId == null) return;
    const row = await trackJob((job) => uploadKbDocument(libraryId, file, folderId, uploadTags, force, ready, job, draft));
    setUploadTags("");
    await loadDocs(libraryId, folderId);
    setHint(row.vector_hint || (ready ? "已按整理稿导入。打开原件仍是原来的文件。" : "已上传"));
  }

  function onUpload(file: File) {
    const kind = uploadKind.current;
    if (kind === "layout" || kind === "copy") {
      uploadKind.current = "plain";
      const copy = kind === "copy";
      run(async () => {
        const note = await trackJob((job) => downloadKbReadyDraft(file, job, copy));
        setHint(
          copy
            ? `稿已下载。${note} 图上的字是本机抄的。回到导入抽屉，原件和这份稿各选一次。`
            : `稿已下载。${note} 图下是空的，字由你补。回到导入抽屉，原件和这份稿各选一次。`,
        );
      });
      return;
    }
    const ready = uploadReady.current;
    run(async () => {
      try {
        await doUpload(file, false, ready);
      } catch (err) {
        const message = err instanceof Error ? err.message : "上传失败";
        if (message.includes("已有相同文件")) {
          setPendingFile(file);
          setPendingDraft(null);
          setPendingReady(ready);
          setError(message);
          return;
        }
        throw err;
      }
    });
  }

  const hereFolders = childFolders(folders, folderId);
  const searching = Boolean(query.trim() || tag.trim());
  const sourceHits = askTurns[askTurns.length - 1]?.result.citations || [];
  const askTitle = sessions.find((item) => item.id === sessionId)?.title || askTurns[0]?.question || "新对话";

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col bg-[var(--bg)]">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-[var(--line)] bg-[var(--paper)] px-4 py-2">
        <h1 className="shrink-0 text-[16px]">知识库</h1>
        <select
          className="h-[30px] min-w-[8rem] border border-[var(--line)] bg-[var(--paper)] px-2 text-[13px]"
          value={libraryId ?? ""}
          onChange={(event) => onPickLibrary(Number(event.target.value))}
        >
          {libraries.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <button type="button" className={`${btnClass} md:hidden`} onClick={() => setRailOpen(true)}>
          范围
        </button>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            className="h-[30px] border border-[var(--ok)] bg-[var(--ok)] px-3 text-[13px] text-white disabled:opacity-50"
            disabled={busy || !library}
            onClick={openImport}
          >
            导入
          </button>
          <button type="button" className={btnClass} onClick={openManage}>
            库设置
          </button>
        </div>
        <input
          ref={uploadRef}
          type="file"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) onUpload(file);
          }}
        />
      </header>

      {error || meter || hint ? (
        <div className="shrink-0 space-y-0.5 px-4 py-1 text-[12.5px]">
          {error ? <p className="text-[var(--err)]">{error}</p> : null}
          {meter ? <ProgressMeter text={meter.text} current={meter.current} total={meter.total} /> : null}
          {hint ? <p className="text-[var(--ok)]">{hint}</p> : null}
        </div>
      ) : null}

      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {railOpen ? <div className="fixed inset-0 z-30 bg-black/10 md:hidden" onClick={() => setRailOpen(false)} /> : null}
        <aside
          className={`${railOpen ? "flex" : "hidden"} fixed inset-y-0 left-0 z-40 w-[272px] flex-col border-r border-[var(--line)] bg-[var(--bg)] md:static md:z-auto md:flex md:w-[248px] md:shrink-0`}
        >
          <div className="flex items-center justify-between border-b border-[var(--line)] px-3 py-2 md:hidden">
            <span className="text-[12px] font-medium">范围与对话</span>
            <button type="button" className="text-[12px] text-[var(--muted)]" onClick={() => setRailOpen(false)}>
              关闭
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
            <section className="mb-5">
              <div className="mb-2 flex items-center justify-between px-1 text-[11px] tracking-[0.08em] text-[var(--muted)]">
                <span>范围</span>
                <span>当前 {docs.length} 份</span>
              </div>
              <div className="mb-2 border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[12px] text-[var(--muted)]">
                当前：<strong className="font-medium text-[var(--text)]">{library?.name || "无"}</strong>
                {crumbs.length ? ` / ${crumbs.map((item) => item.name).join(" / ")}` : ""}
              </div>
              <button
                type="button"
                className={`mb-0.5 block w-full rounded px-2 py-1.5 text-left text-[13px] ${folderId == null ? "bg-[var(--paper)] shadow-[inset_2px_0_0_var(--ok)]" : "hover:bg-[var(--hover)]"}`}
                onClick={() => {
                  onOpenFolder(null);
                  setRailOpen(false);
                }}
              >
                全部（库根）
              </button>
              <FolderTree
                items={folders}
                parentId={null}
                currentId={folderId}
                onOpen={(id) => {
                  onOpenFolder(id);
                  setRailOpen(false);
                }}
              />
            </section>

            <section className="mb-5">
              <div className="mb-2 px-1 text-[11px] tracking-[0.08em] text-[var(--muted)]">标签</div>
              <div className="flex gap-2">
                <input
                  className={`${inputClass} min-w-0 flex-1`}
                  placeholder="例如：2025"
                  value={tag}
                  onChange={(e) => setTag(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && onSearch()}
                />
                <button type="button" className={`${btnClass} shrink-0`} disabled={busy || !library} onClick={onSearch}>
                  筛选
                </button>
              </div>
            </section>

            <section>
              <div className="mb-2 flex items-center justify-between px-1 text-[11px] tracking-[0.08em] text-[var(--muted)]">
                <span>对话</span>
                <button
                  type="button"
                  className="text-[11px] text-[var(--muted)] hover:text-[var(--text)]"
                  onClick={() => {
                    onNewAsk();
                    setPageTab("ask");
                    setRailOpen(false);
                  }}
                >
                  新对话
                </button>
              </div>
              {Object.values(drafts)
                .filter((draft) => draft.sessionId == null && (draft.asking || draft.turns.length > 0))
                .map((draft) => (
                  <button
                    key={draft.key}
                    type="button"
                    className={`mb-0.5 block w-full rounded px-2 py-1.5 text-left ${currentKey === draft.key ? "bg-[var(--paper)] shadow-[inset_2px_0_0_var(--ok)]" : "hover:bg-[var(--hover)]"}`}
                    onClick={() => {
                      persistView();
                      showDraft(draft.key);
                      setPageTab("ask");
                      setRailOpen(false);
                    }}
                  >
                    <span className="block truncate text-[12.5px]">{(draft.turns[0]?.question || "新对话").slice(0, 24)}</span>
                    <span className="block text-[11px] text-[var(--muted)]">{draft.asking ? "在找…" : "未保存到对话"}</span>
                  </button>
                ))}
              {sessions.map((item) => (
                <div key={item.id} className={`mb-0.5 flex items-center gap-1 rounded ${sessionId === item.id ? "bg-[var(--paper)] shadow-[inset_2px_0_0_var(--ok)]" : "hover:bg-[var(--hover)]"}`}>
                  <button
                    type="button"
                    className="min-w-0 flex-1 px-2 py-1.5 text-left"
                    onClick={() => {
                      onOpenSession(item.id);
                      setPageTab("ask");
                      setRailOpen(false);
                    }}
                  >
                    <span className="block truncate text-[12.5px]">{item.title || "新对话"}</span>
                    <span className="block text-[11px] text-[var(--muted)]">{drafts[`s:${item.id}`]?.asking ? "在找…" : shortDate(item.updated_at)}</span>
                  </button>
                  <RowMenu
                    items={[
                      {
                        label: "改名",
                        onClick: () => {
                          setRenameSession(item);
                          setRenameSessionTo(item.title);
                        },
                      },
                      { label: "删除", danger: true, onClick: () => setAskDeleteSession(item) },
                    ]}
                  />
                </div>
              ))}
              {!sessions.length && !Object.values(drafts).some((draft) => draft.sessionId == null && (draft.asking || draft.turns.length > 0)) ? (
                <p className="px-2 py-2 text-[11.5px] text-[var(--muted)]">还没有留下的对话。</p>
              ) : null}
            </section>
          </div>
          <div className="flex gap-2 border-t border-[var(--line)] p-2">
            <input className={`${inputClass} min-w-0 flex-1`} placeholder="新文件夹" value={folderName} onChange={(e) => setFolderName(e.target.value)} />
            <button type="button" className={`${btnClass} shrink-0`} disabled={busy || !library} onClick={onCreateFolder}>
              新建
            </button>
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col bg-[var(--paper)]">
          <div className="flex min-h-[46px] shrink-0 flex-wrap items-center gap-3 border-b border-[var(--line)] px-4 py-1.5">
            <ViewSwitch
              tab={pageTab}
              onChange={(next) => {
                setPageTab(next);
                if (next === "files") {
                  setReaderSources(false);
                  setReaderBack(false);
                }
              }}
            />
            <div className="flex min-w-0 items-center gap-1 text-[12.5px] text-[var(--muted)]">
              {pageTab === "files" ? (
                <>
                  <button type="button" className="hover:text-[var(--text)]" onClick={() => onOpenFolder(null)}>
                    {library?.name || "库"}
                  </button>
                  {crumbs.map((item) => (
                    <span key={item.id} className="flex items-center gap-1">
                      <span className="text-[var(--line)]">/</span>
                      <button type="button" className="hover:text-[var(--text)]" onClick={() => onOpenFolder(item.id)}>
                        {item.name}
                      </button>
                    </span>
                  ))}
                </>
              ) : (
                <span className="max-w-[360px] truncate font-medium text-[var(--text)]">{askTitle}</span>
              )}
            </div>
            <div className="ml-auto flex items-center gap-2">
              {pageTab === "ask" && sourceHits.length ? (
                <button type="button" className={btnClass} onClick={openSources}>
                  本轮出处 {sourceHits.length}
                </button>
              ) : null}
              {pageTab === "files" ? (
                <>
                  <input
                    className={`${inputClass} w-40`}
                    placeholder="搜名称"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && onSearch()}
                  />
                  <button type="button" className={btnClass} disabled={busy || !library} onClick={onSearch}>
                    筛选
                  </button>
                </>
              ) : null}
            </div>
          </div>

          {pageTab === "files" ? (
            <section className="flex min-h-0 flex-1 flex-col">
              <div className="flex shrink-0 items-center gap-3 border-b border-[var(--line)] px-4 py-1.5 text-[12px] text-[var(--muted)]">
                <span>
                  共 <b className="font-medium text-[var(--text)]">{docs.length}</b> 份
                </span>
                {tag ? (
                  <button
                    type="button"
                    className="rounded border border-[var(--line)] px-2 py-0.5 text-[11px] text-[var(--muted)] hover:text-[var(--text)]"
                    onClick={() => {
                      setTag("");
                      if (libraryId != null) run(async () => loadDocs(libraryId, folderId, query, ""));
                    }}
                  >
                    标签：{tag} ×
                  </button>
                ) : null}
                <span className="ml-auto">选中一份在右侧查看</span>
              </div>
              <div className="min-h-0 flex-1 overflow-auto">
                {!searching && hereFolders.length ? (
                  <div>
                    {hereFolders.map((item) => (
                      <div key={`f-${item.id}`} className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-4 py-2 text-[13px] hover:bg-[var(--bg)]">
                        <button type="button" className="flex items-center gap-2" onClick={() => onOpenFolder(item.id)}>
                          <Folder className="h-4 w-4 text-amber-500" />
                          {item.name}
                        </button>
                        <RowMenu
                          items={[
                            {
                              label: "重命名",
                              disabled: busy,
                              onClick: () => {
                                setRenameFolder(item);
                                setRenameFolderTo(item.name);
                              },
                            },
                            { label: "删除", danger: true, disabled: busy, onClick: () => setAskDeleteFolder(item) },
                          ]}
                        />
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="sticky top-0 z-10 hidden grid-cols-[minmax(0,1fr)_120px_120px_84px_32px] items-center gap-3 border-b border-[var(--line)] bg-[var(--paper)] px-4 py-1.5 text-[11px] tracking-[0.06em] text-[var(--muted)] sm:grid">
                  <span>名称</span>
                  <span>标签</span>
                  <span>状态</span>
                  <span>更新</span>
                  <span />
                </div>
                {docs.map((item) => {
                  const { Icon, color } = docIcon(item);
                  const active = preview?.id === item.id;
                  const recognizing = visionDocId === item.id;
                  const rowBusy = busy || (visionDocId != null && !recognizing);
                  return (
                    <div
                      key={item.id}
                      className={`grid grid-cols-[minmax(0,1fr)_32px] items-center gap-3 border-b border-[var(--line)] px-4 py-2 text-[13px] sm:grid-cols-[minmax(0,1fr)_120px_120px_84px_32px] ${active ? "bg-[var(--bg)] shadow-[inset_3px_0_0_var(--ok)]" : "hover:bg-[var(--bg)]"}`}
                    >
                      <button type="button" className="flex min-w-0 items-center gap-2 text-left" onClick={() => openDocFromRow(item)}>
                        <Icon className={`h-4 w-4 shrink-0 ${color}`} />
                        <span className="min-w-0">
                          <span className={`block truncate font-medium ${item.disabled ? "text-[var(--muted)] line-through" : ""}`}>{item.title}</span>
                          <span className="block truncate text-[11px] text-[var(--muted)]">
                            {item.file_name}
                            {item.has_ready_draft ? " · 含整理稿" : ""}
                            {item.disabled ? " · 已停用" : ""}
                          </span>
                        </span>
                      </button>
                      <div className="hidden min-w-0 gap-1 sm:flex">
                        {tagList(item.tags).slice(0, 2).map((name) => (
                          <span key={name} className="truncate rounded bg-[var(--bg)] px-1.5 py-0.5 text-[11px] text-[var(--muted)]">
                            {name}
                          </span>
                        ))}
                      </div>
                      <div className="hidden sm:block">{vectorStateBadge(item.vector_state)}</div>
                      <div className="hidden text-[12px] text-[var(--muted)] sm:block">{shortDate(item.updated_at)}</div>
                      <RowMenu
                        items={[
                          {
                            label: "编辑",
                            disabled: rowBusy,
                            onClick: () => {
                              setEditDoc(item);
                              setEditTitle(item.title);
                              setEditTags(item.tags);
                            },
                          },
                          {
                            label: item.disabled ? "恢复" : "停用",
                            disabled: rowBusy,
                            onClick: () =>
                              run(async () => {
                                const row = await updateKbDocument(item.id, { disabled: !item.disabled });
                                applyDoc(row);
                                setHint(row.disabled ? "已停用，提问会跳过这份" : "已恢复，提问可以再找到");
                              }),
                          },
                          { label: "删除", danger: true, disabled: rowBusy, onClick: () => setAskDeleteDoc(item) },
                        ]}
                      />
                    </div>
                  );
                })}
                {(searching ? !docs.length : !hereFolders.length && !docs.length) ? (
                  <div className="flex min-h-[14rem] flex-col items-center justify-center gap-3 px-6 text-center">
                    <p className="text-[12.5px] leading-6 text-[var(--muted)]">
                      {searching ? "没有符合的资料。" : "这里还是空的。左边可以建文件夹，右上角导入。"}
                    </p>
                    {!searching ? (
                      <button type="button" className={btnClass} disabled={busy || !library} onClick={openImport}>
                        导入资料
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </section>
          ) : (
            <section className="flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
                <div className="mx-auto max-w-[760px]">
                  {askTurns.length ? (
                    <>
                      {askTurns.map((turn, index) => (
                        <AskTurnView
                          key={`${index}-${turn.question}`}
                          turn={turn}
                          isLast={index === askTurns.length - 1}
                          onOpenCitation={onOpenCitation}
                          onOpenSources={openSources}
                        />
                      ))}
                      <div ref={askBottomRef} />
                    </>
                  ) : (
                    <div className="mx-auto max-w-[560px] pt-12 text-[12.5px] leading-6 text-[var(--muted)]">
                      <p className="text-center text-[13px] text-[var(--text)]">对证本轮抽到的资料，不当成已经读完全库。</p>
                      <p className="mt-5">
                        <span className="text-[var(--text)]">回答</span>：问有没有、是多少、是什么，或让它说明、整理。
                      </p>
                      <p className="mt-2">
                        <span className="text-[var(--text)]">核对清单</span>：好几项一条条对照，只标本轮命中 / 未命中，不下合不合格的结论。
                      </p>
                      <p className="mt-2">
                        <span className="text-[var(--text)]">拿资料</span>：要原件和图，按语义和向量找，问了年份就只给这一年。
                      </p>
                      <p className="mt-5 border-t border-[var(--line)] pt-3">点回答里的出处，右侧打开卷宗；「本轮出处」列出这次真正用到的资料。</p>
                    </div>
                  )}
                </div>
              </div>
              <div className="shrink-0 border-t border-[var(--line)] px-6 py-3">
                <div className="mx-auto max-w-[760px]">
                  <div className="rounded-md border border-[var(--line)] bg-[var(--paper)] p-2.5 focus-within:border-[var(--ok)]">
                    <textarea
                      className="min-h-[58px] w-full resize-y border-0 bg-transparent px-0.5 py-0.5 text-[13.5px] leading-7 outline-none"
                      rows={2}
                      placeholder={
                        askKind === "checklist"
                          ? "对照好几项，例如：把名称、份数、编号分别标命中或未命中。Ctrl+Enter 提问"
                          : askKind === "materials"
                            ? "要原件或图，例如：把 2024 年的财务报告给我。Ctrl+Enter 提问"
                            : "问有没有、是多少，例如：这份证书的有效期到哪天？Ctrl+Enter 提问"
                      }
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                          e.preventDefault();
                          onAsk();
                        }
                      }}
                    />
                    <div className="mt-2 flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-2">
                      <div className="flex overflow-hidden rounded border border-[var(--line)]">
                        <button
                          type="button"
                          title={askKindHint("answer")}
                          className={`px-2.5 py-1 text-[12px] ${askKind === "answer" ? "bg-[var(--bg)] font-medium" : "text-[var(--muted)]"}`}
                          onClick={() => setAskKind("answer")}
                        >
                          回答
                        </button>
                        <button
                          type="button"
                          title={askKindHint("checklist")}
                          className={`border-l border-[var(--line)] px-2.5 py-1 text-[12px] ${askKind === "checklist" ? "bg-[var(--bg)] font-medium" : "text-[var(--muted)]"}`}
                          onClick={() => setAskKind("checklist")}
                        >
                          核对清单
                        </button>
                        <button
                          type="button"
                          title={askKindHint("materials")}
                          className={`border-l border-[var(--line)] px-2.5 py-1 text-[12px] ${askKind === "materials" ? "bg-[var(--bg)] font-medium" : "text-[var(--muted)]"}`}
                          onClick={() => setAskKind("materials")}
                        >
                          拿资料
                        </button>
                      </div>
                      <button
                        type="button"
                        className={`inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 text-[11.5px] disabled:opacity-50 ${
                          folderId != null && onlyFolder
                            ? "border-[var(--ok)] text-[var(--ok)]"
                            : "border-[var(--line)] text-[var(--muted)]"
                        }`}
                        disabled={folderId == null}
                        title={folderId == null ? "先在左边选一个子文件夹" : "只搜这个文件夹和它里面的资料"}
                        onClick={() => setOnlyFolder((value) => !value)}
                      >
                        范围{" "}
                        <b className="font-medium">
                          {folderId != null && onlyFolder ? crumbs[crumbs.length - 1]?.name || "当前文件夹" : "整库"}
                        </b>
                      </button>
                      {askKind === "materials" ? null : (
                        <div className="relative">
                          <button
                            type="button"
                            className="inline-flex h-6 items-center gap-1.5 rounded-full border border-[var(--line)] px-2.5 text-[11.5px] text-[var(--muted)]"
                            onClick={(event) => {
                              event.stopPropagation();
                              setOptionsOpen((value) => !value);
                            }}
                          >
                            {askMode ? evidenceLabel(askMode) : `按库规则（${evidenceLabel(library?.evidence_mode || "strict")}）`} · 补查
                            {askLink === "on" ? "开" : askLink === "off" ? "关" : library?.link_enabled ? "开" : "关"}
                          </button>
                          {optionsOpen ? (
                            <div
                              className="absolute bottom-full left-0 z-30 mb-2 w-64 border border-[var(--line)] bg-[var(--paper)] p-3 shadow-lg"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <label className="block text-[11px] text-[var(--muted)]">
                                回答口径
                                <select
                                  className={`${inputClass} mt-1 w-full`}
                                  title={evidenceHint(askMode, library?.evidence_mode || "strict")}
                                  value={askMode}
                                  onChange={(e) => setAskMode(e.target.value as "" | KbEvidenceMode)}
                                >
                                  <option value="">按库规则（{evidenceLabel(library?.evidence_mode || "strict")}）</option>
                                  <option value="strict">严格出处</option>
                                  <option value="loose">宽松概述</option>
                                </select>
                              </label>
                              <label className="mt-3 block text-[11px] text-[var(--muted)]">
                                关联补查
                                <select
                                  className={`${inputClass} mt-1 w-full`}
                                  title={linkHint(askLink, !!library?.link_enabled, library?.link_hops || 3)}
                                  value={askLink}
                                  onChange={(e) => setAskLink(e.target.value as "" | "on" | "off")}
                                >
                                  <option value="">按库规则（{library?.link_enabled ? "开" : "关"}）</option>
                                  <option value="on">这次开</option>
                                  <option value="off">这次关</option>
                                </select>
                              </label>
                            </div>
                          ) : null}
                        </div>
                      )}
                      {asking ? (
                        <button type="button" className={`${btnClass} ml-auto`} onClick={onStopAsk}>
                          终止
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="ml-auto h-[30px] border border-[var(--ok)] bg-[var(--ok)] px-3 text-[12.5px] text-white disabled:opacity-40"
                          disabled={!question.trim()}
                          onClick={onAsk}
                        >
                          提问
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </section>
          )}
        </main>

        {readerSources ? (
          <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[440px] flex-col border-l border-[var(--line)] bg-[var(--paper)] shadow-xl xl:static xl:z-auto xl:w-[440px] xl:max-w-none xl:shrink-0 xl:shadow-none">
            <div className="flex items-center justify-between gap-3 border-b border-[var(--line)] px-4 py-2">
              <div>
                <p className="text-[13px] font-medium">本轮出处</p>
                <p className="text-[11px] text-[var(--muted)]">{sourceHits.length} 份 · 关键词 + 向量</p>
              </div>
              <button type="button" className="text-[12px] text-[var(--muted)] hover:text-[var(--text)]" onClick={closeReader}>
                关闭
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-4">
              {sourceHits.length ? (
                sourceHits.map((hit, index) => (
                  <div key={hit.id} className="mb-3 border border-[var(--line)] bg-[var(--paper)] p-3">
                    <div className="flex items-center gap-2">
                      <span className="shrink-0 rounded bg-[var(--bg)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--ok)]">资料{index + 1}</span>
                      <span className="min-w-0 truncate text-[12.5px] font-medium">{hit.title}</span>
                      <button type="button" className="ml-auto shrink-0 text-[11.5px] text-[var(--muted)] underline hover:text-[var(--text)]" onClick={() => onOpenCitation(hit.id)}>
                        打开卷宗
                      </button>
                    </div>
                    {hit.images?.length ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {hit.images.slice(0, 3).map((img) => (
                          <button key={img.id} type="button" title={img.alt || "打开卷宗"} onClick={() => onOpenCitation(hit.id)}>
                            <img
                              src={img.url || kbAssetFileUrl(img.id)}
                              alt={img.alt}
                              className="max-h-20 w-auto border border-[var(--line)] object-contain"
                            />
                          </button>
                        ))}
                      </div>
                    ) : null}
                    <p className="mt-1.5 text-[10.5px] text-[var(--muted)]">相关度 {Math.round((hit.score || 0) * 100)}%</p>
                  </div>
                ))
              ) : (
                <p className="text-[12.5px] leading-6 text-[var(--muted)]">这一轮还没有出处。先提一个问题。</p>
              )}
              <p className="mt-3 border-t border-[var(--line)] pt-3 text-[11px] leading-5 text-[var(--muted)]">只列出本轮真正用到的资料。没命中的资料不等于「库里没有」。</p>
            </div>
          </aside>
        ) : preview ? (
          <aside className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[440px] flex-col border-l border-[var(--line)] bg-[var(--paper)] shadow-xl xl:static xl:z-auto xl:w-[440px] xl:max-w-none xl:shrink-0 xl:shadow-none">
            {readerBack ? (
              <div className="flex shrink-0 items-center border-b border-[var(--line)] px-4 py-1.5">
                <button
                  type="button"
                  className="text-[11.5px] text-[var(--muted)] hover:text-[var(--text)]"
                  onClick={() => {
                    setPreview(null);
                    setReaderBack(false);
                    setReaderSources(true);
                  }}
                >
                  ← 返回出处
                </button>
              </div>
            ) : null}
            <PreviewPane
              item={preview}
              text={previewText}
              wikiEnabled={!!library?.wiki_enabled}
              visionEnabled={!!library?.vision_enabled}
              busy={busy}
              assetTick={assetTick}
              visionLocked={visionDocId != null}
              recognizing={visionDocId === preview.id}
              onRecognizeAll={() => void recognizeAll(preview)}
              onSaved={applyDoc}
              onHint={setHint}
              onError={setError}
              onClose={closeReader}
            />
          </aside>
        ) : null}
      </div>

      {renameFolder ? (
        <Modal title="重命名文件夹" onClose={() => setRenameFolder(null)}>
          <input className={`${inputClass} w-full`} value={renameFolderTo} onChange={(e) => setRenameFolderTo(e.target.value)} />
          <button
            type="button"
            className={`${btnClass} mt-3`}
            disabled={busy}
            onClick={() =>
              run(async () => {
                await renameKbFolder(renameFolder.id, renameFolderTo.trim());
                setRenameFolder(null);
                if (libraryId) await loadFolders(libraryId);
              })
            }
          >
            保存
          </button>
        </Modal>
      ) : null}

      {editDoc ? (
        <Modal title="编辑资料" onClose={() => setEditDoc(null)}>
          <label className="mb-2 block text-[13px] text-[var(--muted)]">名称</label>
          <input className={`${inputClass} mb-3 w-full`} value={editTitle} onChange={(e) => setEditTitle(e.target.value)} />
          <label className="mb-2 block text-[13px] text-[var(--muted)]">标签</label>
          <input className={`${inputClass} w-full`} value={editTags} onChange={(e) => setEditTags(e.target.value)} placeholder="逗号分隔" />
          <button
            type="button"
            className={`${btnClass} mt-3`}
            disabled={busy}
            onClick={() =>
              run(async () => {
                await updateKbDocument(editDoc.id, { title: editTitle, tags: editTags });
                setEditDoc(null);
                if (libraryId) await loadDocs(libraryId, folderId);
              })
            }
          >
            保存
          </button>
        </Modal>
      ) : null}

      {renameSession ? (
        <Modal title="改对话名" onClose={() => setRenameSession(null)}>
          <input className={`${inputClass} w-full`} value={renameSessionTo} onChange={(e) => setRenameSessionTo(e.target.value)} />
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              className={btnClass}
              disabled={busy || !renameSessionTo.trim()}
              onClick={() =>
                run(async () => {
                  await renameKbSession(renameSession.id, renameSessionTo.trim());
                  setRenameSession(null);
                  if (libraryId != null) {
                    const listed = await fetchKbSessions(libraryId);
                    setSessions(listed.items);
                  }
                })
              }
            >
              保存
            </button>
            <button type="button" className={btnClass} onClick={() => setRenameSession(null)}>
              取消
            </button>
          </div>
        </Modal>
      ) : null}

      {askDeleteSession ? (
        <ConfirmModal
          title="删除这段对话？"
          message="删了就打不开了。"
          busy={busy}
          onClose={() => setAskDeleteSession(null)}
          onConfirm={() => {
            const target = askDeleteSession;
            run(async () => {
              abortJob(`s:${target.id}`, false);
              const copy = { ...draftsRef.current };
              delete copy[`s:${target.id}`];
              if (currentKeyRef.current === `s:${target.id}`) {
                newDraftSeq.current += 1;
                const key = draftKey(null, newDraftSeq.current);
                copy[key] = emptyDraft(key);
                draftsRef.current = copy;
                publishDrafts();
                showDraft(key);
              } else {
                draftsRef.current = copy;
                publishDrafts();
              }
              await deleteKbSession(target.id);
              setAskDeleteSession(null);
              if (libraryId != null) {
                const listed = await fetchKbSessions(libraryId);
                setSessions(listed.items);
              }
            });
          }}
        />
      ) : null}

      {askDeleteLib ? (
        <ConfirmModal
          title="删除这个库？"
          message="库里的文件夹、文件和对话都会删掉。"
          busy={busy}
          onClose={() => setAskDeleteLib(false)}
          onConfirm={() => {
            if (!library) return;
            run(async () => {
              await deleteKbLibrary(library.id);
              setAskDeleteLib(false);
              setFolderId(null);
              setPreview(null);
              setReaderSources(false);
              await reloadAll(null, null);
            });
          }}
        />
      ) : null}

      {askDeleteFolder ? (
        <ConfirmModal
          title="删除这个文件夹？"
          message="只能删空文件夹。"
          busy={busy}
          onClose={() => setAskDeleteFolder(null)}
          onConfirm={() => {
            const target = askDeleteFolder;
            run(async () => {
              await deleteKbFolder(target.id);
              setAskDeleteFolder(null);
              if (folderId === target.id) setFolderId(target.parent_id);
              if (libraryId) {
                await loadFolders(libraryId);
                await loadDocs(libraryId, folderId === target.id ? target.parent_id : folderId);
              }
            });
          }}
        />
      ) : null}

      {askDeleteDoc ? (
        <ConfirmModal
          title="删除这份资料？"
          message="原件也会从知识库目录里删掉。"
          busy={busy}
          onClose={() => setAskDeleteDoc(null)}
          onConfirm={() => {
            const target = askDeleteDoc;
            run(async () => {
              await deleteKbDocument(target.id);
              setAskDeleteDoc(null);
              if (preview?.id === target.id) closeReader();
              if (libraryId) await loadDocs(libraryId, folderId);
            });
          }}
        />
      ) : null}

      {manageLib ? (
        <Drawer title="知识库设置" wide onClose={() => setManageLib(false)}>
          <div className="flex min-h-[60vh] w-full gap-4">
            <nav className="w-[124px] shrink-0 space-y-0.5">
              {(
                [
                  ["basic", "基本"],
                  ["answer", "回答规则"],
                  ["index", "检索与索引"],
                  ["vision", "识图"],
                  ["wiki", "Wiki"],
                  ["summary", "摘要管理"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`block w-full rounded px-2 py-1.5 text-left text-[12.5px] ${settingsTab === key ? "bg-[var(--bg)] font-medium shadow-[inset_2px_0_0_var(--ok)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"}`}
                  onClick={() => setSettingsTab(key)}
                >
                  {label}
                </button>
              ))}
            </nav>
            <div className="min-w-0 flex-1">
              {settingsTab === "basic" ? (
                <div>
                  <p className="mb-2 text-[12px] font-medium">基本</p>
                  <p className="mb-2 text-[12.5px] text-[var(--muted)]">当前：{library?.name || "无"}</p>
                  <input className={`${inputClass} w-full`} placeholder="新库名 / 改名" value={libName} onChange={(e) => setLibName(e.target.value)} />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className={btnClass}
                      disabled={busy}
                      onClick={() => {
                        onCreateLibrary();
                        setManageLib(false);
                      }}
                    >
                      新建库
                    </button>
                    <button
                      type="button"
                      className={btnClass}
                      disabled={busy || !library}
                      onClick={() => {
                        onRenameLibrary();
                        setManageLib(false);
                      }}
                    >
                      改库名
                    </button>
                    <button
                      type="button"
                      className={`${btnClass} text-[var(--err)]`}
                      disabled={busy || !library}
                      onClick={() => {
                        setManageLib(false);
                        setAskDeleteLib(true);
                      }}
                    >
                      删库
                    </button>
                  </div>
                  <p className="mt-3 text-[11px] leading-5 text-[var(--muted)]">删库会同时删掉文件夹、资料和对话，需要二次确认。</p>
                </div>
              ) : null}

              {settingsTab === "answer" ? (
                <div>
                  <p className="mb-2 text-[12px] font-medium">回答规则</p>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
                    <span className="text-[var(--muted)]">回答风格</span>
                    <select className={inputClass} value={libMode} onChange={(e) => setLibMode(e.target.value as KbEvidenceMode)}>
                      <option value="strict">严格出处</option>
                      <option value="loose">宽松概述</option>
                    </select>
                  </div>
                  <p className="mb-2 text-[11px] leading-5 text-[var(--muted)]">
                    严格：只根据原文片段回答，摘要不能当证据。宽松：可以参考摘要帮忙概括，但仍要标明哪份资料。提问时可以临时改。
                  </p>
                  <input
                    className={`${inputClass} w-full`}
                    placeholder="额外规则，可空"
                    value={libRule}
                    onChange={(e) => setLibRule(e.target.value)}
                  />
                  <p className="mt-2 text-[11px] leading-5 text-[var(--muted)]">例如「金额一律以大写为准」。只影响这个库的回答。</p>
                </div>
              ) : null}

              {settingsTab === "index" ? (
                <div>
                  <p className="mb-2 text-[12px] font-medium">检索与索引</p>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
                    <span className="text-[var(--muted)]">关联补查</span>
                    <button
                      type="button"
                      className="kb-toggle"
                      aria-pressed={linkEnabled}
                      aria-label="开启关联补查"
                      onClick={() => setLinkEnabled((value) => !value)}
                    />
                    {linkEnabled ? (
                      <>
                        <span className="text-[var(--muted)]">最多跳数</span>
                        <input
                          className={`${inputClass} w-16`}
                          inputMode="numeric"
                          value={linkHops}
                          onChange={(e) => setLinkHops(e.target.value.replace(/[^\d]/g, "").slice(0, 1))}
                        />
                      </>
                    ) : null}
                  </div>
                  <p className="mb-2 text-[11px] leading-5 text-[var(--muted)]">
                    默认关。开了以后，一次没搜全时，会用原文里新出现的人名、编号再查，够了就停。最多跳数 1 到 8，是上限。
                  </p>
                  <p className="text-[11px] leading-5 text-[var(--muted)]">切片长度、正文上限等参数在每份资料的「处理」里单独设置；改完只影响这一份。</p>
                </div>
              ) : null}

              {settingsTab === "vision" ? (
                <div>
                  <p className="mb-2 text-[12px] font-medium">识图</p>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
                    <span className="text-[var(--muted)]">允许识图</span>
                    <button
                      type="button"
                      className="kb-toggle"
                      aria-pressed={visionEnabled}
                      aria-label="开启识图"
                      onClick={() => setVisionEnabled((value) => !value)}
                    />
                  </div>
                  {visionEnabled ? (
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
                      <span className="text-[var(--muted)]">识别方式</span>
                      <select className={inputClass} value={visionEngine} onChange={(e) => setVisionEngine(e.target.value === "ocr" ? "ocr" : "vision")}>
                        <option value="vision">看图（准，慢，要 Key）</option>
                        <option value="ocr">OCR（快，不要 Key）</option>
                      </select>
                    </div>
                  ) : null}
                  <p className="text-[11px] leading-5 text-[var(--muted)]">
                    开了才允许认图上的字。上传不会自动认，要在卷宗里点「全部识图」或单张识图。
                  </p>
                </div>
              ) : null}

              {settingsTab === "wiki" ? (
                <div>
                  <p className="mb-2 text-[12px] font-medium">Wiki</p>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
                    <span className="text-[var(--muted)]">开启 Wiki</span>
                    <button
                      type="button"
                      className="kb-toggle"
                      aria-pressed={wikiEnabled}
                      aria-label="开启 Wiki"
                      onClick={(event) => {
                        const next = !wikiEnabled;
                        setWikiEnabled(next);
                        if (!next) setWikiLearn(false);
                        event.stopPropagation();
                      }}
                    />
                  </div>
                  <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
                    <span className="text-[var(--muted)]">跟着提问更新</span>
                    <button
                      type="button"
                      className="kb-toggle"
                      aria-pressed={wikiLearn && wikiEnabled}
                      disabled={!wikiEnabled}
                      aria-label="跟着提问更新"
                      onClick={() => setWikiLearn((value) => !value)}
                    />
                  </div>
                  <p className="text-[11px] leading-5 text-[var(--muted)]">
                    默认关。开了才允许写摘要，不会自动给全库写。问完只改本轮出处里最相关的最多 5 份。关掉后已有摘要还在，只是不再新写。
                  </p>
                </div>
              ) : null}

              {settingsTab === "summary" ? (
                <div>
                  <p className="mb-2 text-[12px] font-medium">摘要管理</p>
                  <p className="mb-2 text-[11px] leading-5 text-[var(--muted)]">
                    本库已有 {wikiList?.all_count ?? 0} 条，其中 {wikiList?.stale_count ?? 0} 条可能过期。
                  </p>
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <input
                      className={`${inputClass} w-36`}
                      placeholder="搜资料名"
                      value={wikiQ}
                      onChange={(e) => setWikiQ(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && run(async () => loadWikis(1))}
                    />
                    <select className={inputClass} value={wikiStale} onChange={(e) => setWikiStale(e.target.value)}>
                      <option value="">全部</option>
                      <option value="stale">可能过期</option>
                      <option value="fresh">未过期</option>
                    </select>
                    <select className={inputClass} value={wikiSort} onChange={(e) => setWikiSort(e.target.value)}>
                      <option value="updated_at">更新时间</option>
                      <option value="title">资料名</option>
                      <option value="stale">是否过期</option>
                    </select>
                    <select className={inputClass} value={wikiOrder} onChange={(e) => setWikiOrder(e.target.value)}>
                      <option value="desc">从新到旧</option>
                      <option value="asc">从旧到新</option>
                    </select>
                    <button type="button" className={btnClass} disabled={busy || !library} onClick={() => run(async () => loadWikis(1))}>
                      筛选
                    </button>
                  </div>
                  <div className="max-h-64 overflow-auto border border-[var(--line)]">
                    {(wikiList?.items || []).map((item) => (
                      <div key={item.id} className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-2 py-2 text-[12.5px]">
                        <button
                          type="button"
                          className="min-w-0 truncate text-left"
                          onClick={() =>
                            run(async () => {
                              const row = await fetchKbDocument(item.id);
                              setManageLib(false);
                              openDocFromRow(row);
                            })
                          }
                        >
                          {item.title}
                          {item.wiki_stale ? <span className="ml-2 text-[var(--muted)]">可能过期</span> : null}
                        </button>
                        <button
                          type="button"
                          className="shrink-0 text-[var(--muted)] hover:text-[var(--err)]"
                          disabled={busy}
                          onClick={() =>
                            run(async () => {
                              const row = await deleteKbWiki(item.id);
                              applyDoc(row);
                              await loadWikis(wikiPage);
                            })
                          }
                        >
                          删除
                        </button>
                      </div>
                    ))}
                    {!wikiList?.items.length ? (
                      <p className="px-2 py-6 text-center text-[12px] leading-5 text-[var(--muted)]">
                        还没有摘要。先开启 Wiki 并保存规则，再点一份资料，在右栏写摘要。
                      </p>
                    ) : null}
                  </div>
                  {wikiList && wikiList.total > wikiList.page_size ? (
                    <div className="mt-2 flex items-center gap-2 text-[12px] text-[var(--muted)]">
                      <button type="button" className={btnClass} disabled={wikiPage <= 1 || busy} onClick={() => run(async () => loadWikis(wikiPage - 1))}>
                        上一页
                      </button>
                      <span>
                        {wikiPage} / {Math.max(1, Math.ceil(wikiList.total / wikiList.page_size))}
                      </span>
                      <button
                        type="button"
                        className={btnClass}
                        disabled={wikiPage >= Math.ceil(wikiList.total / wikiList.page_size) || busy}
                        onClick={() => run(async () => loadWikis(wikiPage + 1))}
                      >
                        下一页
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {settingsTab !== "basic" && settingsTab !== "summary" ? (
                <div className="mt-4 border-t border-[var(--line)] pt-3">
                  <button
                    type="button"
                    className="h-[30px] border border-[var(--ok)] bg-[var(--ok)] px-3 text-[12.5px] text-white disabled:opacity-50"
                    disabled={busy || !library}
                    onClick={() =>
                      run(async () => {
                        if (!library) return;
                        const hops = Math.min(8, Math.max(1, Number(linkHops) || 3));
                        const row = await updateKbLibraryPolicy(
                          library.id,
                          wikiEnabled,
                          libMode,
                          libRule,
                          wikiLearn,
                          visionEnabled,
                          visionEngine,
                          {
                            textLimit: library.text_limit,
                            sheetLimit: library.sheet_limit,
                            sheetRows: library.sheet_rows,
                            cleanCollapse: library.clean_collapse,
                            chunkSize: library.chunk_size,
                            chunkOverlap: library.chunk_overlap,
                            maxChunks: library.max_chunks,
                            vectorEnabled: library.vector_enabled,
                          },
                          linkEnabled,
                          hops,
                        );
                        setLinkHops(String(row.link_hops || hops));
                        setLibraries((items) => items.map((item) => (item.id === row.id ? row : item)));
                        setHint("已保存库规则");
                      })
                    }
                  >
                    保存规则
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </Drawer>
      ) : null}

      {importOpen ? (
        <Drawer title="导入资料" onClose={() => setImportOpen(false)}>
          <div className="mb-3">
            <label className="mb-1 block text-[12px] text-[var(--muted)]">这次导入的标签（可空，逗号分隔）</label>
            <input
              className={`${inputClass} w-full`}
              placeholder="例如：合同, 2025"
              value={uploadTags}
              onChange={(e) => setUploadTags(e.target.value)}
            />
          </div>
          <div
            className="mb-3 border border-dashed border-[var(--line)] bg-[var(--paper)] px-4 py-6 text-center text-[12.5px] text-[var(--muted)]"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const file = event.dataTransfer.files?.[0];
              if (!file) return;
              uploadKind.current = "plain";
              uploadReady.current = false;
              setImportOpen(false);
              onUpload(file);
            }}
          >
            <b className="mb-1 block text-[13px] text-[var(--text)]">把文件拖到这里</b>
            或点下面的按钮选择。一次一份，原件原样保存。
          </div>
          <div className="space-y-2 text-[13px] leading-6">
            <div className="border border-[var(--line)] p-3">
              <p className="mb-1 font-medium">普通导入</p>
              <p className="mb-3 text-[12px] text-[var(--muted)]">正文清楚的 Word、PDF、表格和文本。图只记成图1、图2，图上的字不会自动认。</p>
              <button type="button" className={btnClass} disabled={busy} onClick={() => pickUpload(false)}>
                选原文件
              </button>
            </div>
            <div className="border border-[var(--line)] p-3">
              <p className="mb-1 font-medium">整理稿导入</p>
              <p className="mb-3 text-[12px] text-[var(--muted)]">
                先得到一份改好的 Word，检查后再导入。打开原件仍是原版式，整理稿只用来切片和提问。
              </p>
              <div className="flex flex-wrap gap-2">
                <button type="button" className={btnClass} disabled={busy} onClick={() => pickLayout(false)}>
                  只摆格式
                </button>
                <button type="button" className={btnClass} disabled={busy} onClick={() => pickLayout(true)}>
                  本机抄字
                </button>
                <button type="button" className={btnClass} disabled={busy || !plainSkill} onClick={() => copySkill(plainSkill)}>
                  复制普通看图
                </button>
                <button type="button" className={btnClass} disabled={busy || !plainSkill} onClick={() => downloadSkill(plainSkill, "普通看图规则.md")}>
                  下载普通看图
                </button>
                <button type="button" className={btnClass} disabled={busy || !carefulSkill} onClick={() => copySkill(carefulSkill)}>
                  复制仔细看图
                </button>
                <button type="button" className={btnClass} disabled={busy || !carefulSkill} onClick={() => downloadSkill(carefulSkill, "知识库整理稿规则.md")}>
                  下载仔细看图
                </button>
              </div>
              <div className="mt-3 grid gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className={btnClass} disabled={busy} onClick={() => readyOriginalRef.current?.click()}>
                    选原件
                  </button>
                  <span className="text-[11.5px] text-[var(--muted)]">{readyOriginalFile ? readyOriginalFile.name : "还没选"}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className={btnClass} disabled={busy} onClick={() => readyDraftRef.current?.click()}>
                    选改好的稿
                  </button>
                  <span className="text-[11.5px] text-[var(--muted)]">{readyDraftFile ? readyDraftFile.name : "还没选，要是 Word"}</span>
                </div>
                <div>
                  <button type="button" className={btnClass} disabled={busy || !readyOriginalFile || !readyDraftFile} onClick={startReadyImport}>
                    导入这两份
                  </button>
                </div>
                <input
                  ref={readyOriginalRef}
                  type="file"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    event.target.value = "";
                    if (file) setReadyOriginalFile(file);
                  }}
                />
                <input
                  ref={readyDraftRef}
                  type="file"
                  accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0] ?? null;
                    event.target.value = "";
                    if (file) setReadyDraftFile(file);
                  }}
                />
              </div>
            </div>
          </div>
          <p className="mt-3 text-[11px] leading-5 text-[var(--muted)]">导入后会在后台抽正文、切片、算向量，进度显示在页面顶部，可以继续做别的事。</p>
        </Drawer>
      ) : null}

      {pendingFile ? (
        <ConfirmModal
          title="仍要另存一份？"
          message={error || "库里已有相同文件。"}
          confirmLabel="另存"
          busy={busy}
          onClose={() => {
            setPendingFile(null);
            setPendingDraft(null);
            setPendingReady(false);
          }}
          onConfirm={() => {
            const file = pendingFile;
            const ready = pendingReady;
            const draft = pendingDraft;
            setPendingFile(null);
            setPendingDraft(null);
            setPendingReady(false);
            run(async () => {
              await doUpload(file, true, ready, draft);
            });
          }}
        />
      ) : null}
    </div>
  );
}

function newKbJob() {
  const alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let out = "";
  for (const item of bytes) out += alphabet[item % alphabet.length];
  return out;
}

/** 出稿和导入时停在页面上方的进度条。 */
function ProgressMeter({ text, current, total }: { text: string; current: number; total: number }) {
  const ratio = total > 0 ? current / total : 0;
  const pct = total > 0 ? Math.max(8, Math.min(100, Math.round(ratio * 100))) : 12;
  return (
    <div className="max-w-lg">
      <div className="mb-1 flex items-center justify-between gap-3 text-[13px] text-[var(--ok)]">
        <span>{text}</span>
        {total > 0 ? <span>{Math.min(100, Math.round(ratio * 100))}%</span> : null}
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-[var(--line)]">
        <div className="h-full rounded-full bg-[var(--ok)] transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function FolderTree({
  items,
  parentId,
  currentId,
  onOpen,
  depth = 0,
}: {
  items: KbFolder[];
  parentId: number | null;
  currentId: number | null;
  onOpen: (id: number) => void;
  depth?: number;
}) {
  return (
    <>
      {childFolders(items, parentId).map((item) => (
        <div key={item.id}>
          <button
            type="button"
            className={`block w-full truncate rounded-md px-2 py-1.5 text-left text-[13px] ${currentId === item.id ? "bg-[var(--bg)]" : "hover:bg-[var(--hover)]"}`}
            style={{ paddingLeft: 8 + depth * 12 }}
            onClick={() => onOpen(item.id)}
          >
            {item.name}
          </button>
          <FolderTree items={items} parentId={item.id} currentId={currentId} onOpen={onOpen} depth={depth + 1} />
        </div>
      ))}
    </>
  );
}

/** 预览里看图上的字，认错了可以改。 */
function AssetWords({
  docId,
  refreshTick,
  visionLocked,
  onHint,
  onError,
  onDocChange,
}: {
  docId: number;
  refreshTick: number;
  visionLocked: boolean;
  onHint: (message: string, ok: boolean) => void;
  onError: (message: string) => void;
  onDocChange: () => void;
}) {
  const [items, setItems] = useState<KbDocAsset[]>([]);
  const [groups, setGroups] = useState<KbImageGroup[]>([]);
  const [groupFrom, setGroupFrom] = useState("");
  const [groupTo, setGroupTo] = useState("");
  const [groupName, setGroupName] = useState("");
  const [picking, setPicking] = useState(false);
  const [savingGroups, setSavingGroups] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, { caption: string; keywords: string; words: string }>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [seeingId, setSeeingId] = useState<number | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAll, setShowAll] = useState(false);
  const [zoom, setZoom] = useState<number | null>(null);
  const [editHint, setEditHint] = useState<{ text: string; ok: boolean } | null>(null);
  const [savingAll, setSavingAll] = useState(false);
  const closeEditRef = useRef<() => void>(() => setOpenId(null));

  function noteOf(row: KbDocAsset) {
    return { caption: row.caption || "", keywords: row.keywords || "", words: row.ocr_text || "" };
  }

  useEffect(() => {
    let alive = true;
    setOpenId(null);
    setShowAll(false);
    setZoom(null);
    setPicking(false);
    setGroupFrom("");
    setGroupTo("");
    setGroupName("");
    setLoading(true);
    fetchKbDocumentAssets(docId)
      .then((data) => {
        if (!alive) return;
        setItems(data.items);
        setGroups(data.groups || []);
        setDrafts(Object.fromEntries(data.items.map((item) => [item.id, noteOf(item)])));
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [docId, refreshTick, onError]);

  useEffect(() => {
    setEditHint(null);
  }, [openId]);

  useEffect(() => {
    if (openId == null || zoom != null) return;
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.stopImmediatePropagation();
      closeEditRef.current();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [openId, zoom]);

  if (loading) {
    return (
      <div className="mt-4 border-t border-[var(--line)] pt-3">
        <p className="font-medium">图的说明</p>
        <p className="text-[12px] text-[var(--muted)]">正在列出…</p>
      </div>
    );
  }
  if (!items.length) return null;

  const limit = 8;
  const visible = showAll ? items : items.slice(0, limit);

  function applyAsset(row: KbDocAsset) {
    setItems((list) => list.map((one) => (one.id === row.id ? row : one)));
    setDrafts((map) => ({ ...map, [row.id]: noteOf(row) }));
  }

  function isDirty(item: KbDocAsset) {
    const draft = drafts[item.id] || noteOf(item);
    const saved = noteOf(item);
    return draft.caption !== saved.caption || draft.keywords !== saved.keywords || draft.words !== saved.words;
  }

  function save(item: KbDocAsset) {
    const note = drafts[item.id] || noteOf(item);
    setSavingId(item.id);
    return saveKbAssetOcr(item.id, { caption: note.caption, keywords: note.keywords, ocr_text: note.words })
      .then((row) => {
        applyAsset(row);
        const text = row.vector_hint || "字已保存。改完后点「重算向量」。";
        onHint(text, true);
        setEditHint({ text, ok: true });
        onDocChange();
        return row;
      })
      .catch((err: Error) => {
        onError(err.message);
        return null;
      })
      .finally(() => setSavingId(null));
  }

  function saveAll() {
    const dirty = items.filter(isDirty);
    if (!dirty.length) {
      onHint("没有改过的字", true);
      return;
    }
    setSavingAll(true);
    saveKbAssetsBatch(
      docId,
      dirty.map((item) => {
        const note = drafts[item.id] || noteOf(item);
        return { id: item.id, caption: note.caption, keywords: note.keywords, ocr_text: note.words };
      }),
    )
      .then((data) => {
        setItems(data.items);
        setDrafts(Object.fromEntries(data.items.map((item) => [item.id, noteOf(item)])));
        const text = data.vector_hint || `已保存 ${dirty.length} 张。改完后点「重算向量」。`;
        onHint(text, true);
        setEditHint({ text, ok: true });
        onDocChange();
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setSavingAll(false));
  }

  function goNear(delta: number) {
    const idx = items.findIndex((row) => row.id === openId);
    const next = items[idx + delta];
    if (!next || savingId != null || savingAll) return;
    const current = items[idx];
    if (current && isDirty(current)) {
      void save(current).then((row) => {
        if (row) setOpenId(next.id);
      });
      return;
    }
    setOpenId(next.id);
  }

  function writeGroups(next: KbImageGroup[]) {
    setSavingGroups(true);
    return saveKbImageGroups(docId, next)
      .then((data) => {
        setGroups(data.groups || []);
        onHint("分组已保存，只在拿资料时用", true);
        return true;
      })
      .catch((err: Error) => {
        onError(err.message);
        return false;
      })
      .finally(() => setSavingGroups(false));
  }

  function figureNo(item: KbDocAsset) {
    const match = (item.alt || "").match(/图\s*(\d+)/);
    if (match) return Number(match[1]);
    const index = items.findIndex((row) => row.id === item.id);
    return index >= 0 ? index + 1 : 0;
  }

  function beginPick() {
    setGroupFrom("");
    setGroupTo("");
    setPicking((on) => !on);
    setShowAll(true);
  }

  function onThumb(item: KbDocAsset, zoomIndex: number) {
    if (!picking) {
      setZoom(zoomIndex);
      return;
    }
    const number = figureNo(item);
    if (!number) return;
    if (!groupFrom || groupTo) {
      setGroupFrom(String(number));
      setGroupTo("");
      return;
    }
    const from = Number(groupFrom);
    setGroupFrom(String(Math.min(from, number)));
    setGroupTo(String(Math.max(from, number)));
    setPicking(false);
  }

  function addGroup() {
    const start = Number(groupFrom);
    const end = Number(groupTo);
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start) {
      onError("请写成从第几张到第几张");
      return;
    }
    void writeGroups([...groups, { name: groupName.trim(), start, end }]).then((saved) => {
      if (!saved) return;
      setGroupFrom("");
      setGroupTo("");
      setGroupName("");
      setPicking(false);
    });
  }

  function seeOne(item: KbDocAsset) {
    setSeeingId(item.id);
    recognizeKbAsset(item.id)
      .then((row) => {
        applyAsset(row);
        const text = row.vector_hint || (row.vector_ok ? "已识图，向量已更新。" : "已识图，向量没更新。");
        onHint(text, !!row.vector_ok);
        setEditHint({ text, ok: !!row.vector_ok });
        onDocChange();
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setSeeingId(null));
  }

  function patchDraft(id: number, key: "caption" | "keywords" | "words", value: string) {
    setDrafts((map) => {
      const current = map[id] || { caption: "", keywords: "", words: "" };
      return { ...map, [id]: { ...current, [key]: value } };
    });
  }

  const editing = items.find((row) => row.id === openId);
  const editDraft = editing ? drafts[editing.id] || noteOf(editing) : null;
  const editIndex = editing ? items.findIndex((row) => row.id === editing.id) : -1;
  const dirtyCount = items.filter(isDirty).length;
  const zoomItems = items.map((row) => ({ src: row.url || kbAssetFileUrl(row.id), alt: row.alt || row.caption || "图" }));

  function closeEdit() {
    if (editing && isDirty(editing) && savingId == null && !savingAll) {
      void save(editing).then((row) => {
        if (row) setOpenId(null);
      });
      return;
    }
    setOpenId(null);
  }
  closeEditRef.current = closeEdit;

  return (
    <div className="mt-4 border-t border-[var(--line)] pt-3">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">图的说明</p>
        <button type="button" className={btnClass} disabled={savingAll || savingId != null || !dirtyCount} onClick={saveAll}>
          {savingAll ? "在存…" : dirtyCount ? `保存已改 ${dirtyCount} 张` : "没有改过"}
        </button>
      </div>
      <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">
        点「改说明」连着改，上一张/下一张会自动存字。改完点资料标题旁的「重算向量」。
      </p>
      <div className="mb-3 rounded-md border border-[var(--line)] px-2 py-2">
        <p className="text-[13px] font-medium">拿资料分组</p>
        <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">
          {picking ? (groupFrom ? "再点结尾的那张图。" : "先点开头的那张图。") : "点「圈一组」，再在图上点两下。没圈的时候，点图仍然放大。"}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={btnClass} disabled={savingGroups} onClick={beginPick}>
            {picking ? "取消圈选" : "圈一组"}
          </button>
          {groupFrom && groupTo ? <span className="text-[12px]">图{groupFrom}–图{groupTo}</span> : null}
          <input className={`${inputClass} w-40`} maxLength={40} value={groupName} placeholder="组名，可以不填" onChange={(e) => setGroupName(e.target.value)} />
          <button type="button" className={btnClass} disabled={savingGroups || !groupFrom || !groupTo} onClick={addGroup}>
            {savingGroups ? "在存…" : "确定这一组"}
          </button>
        </div>
        {groups.length ? (
          <ul className="mt-2 space-y-1 text-[12px]">
            {groups.map((group, index) => (
              <li key={`${group.start}-${group.end}-${index}`} className="flex items-center gap-2">
                <span>
                  图{group.start}–图{group.end}
                  {group.name ? ` ${group.name}` : ""}
                </span>
                <button type="button" className="text-[var(--muted)] underline" disabled={savingGroups} onClick={() => writeGroups(groups.filter((_, at) => at !== index))}>
                  删除
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
        {visible.map((item) => {
          const draft = drafts[item.id] || noteOf(item);
          const open = openId === item.id;
          const zoomIndex = items.findIndex((row) => row.id === item.id);
          const number = figureNo(item);
          const fromNo = Number(groupFrom);
          const toNo = Number(groupTo);
          const inPick = Number.isInteger(fromNo) && Number.isInteger(toNo) && fromNo >= 1 && toNo >= fromNo && number >= fromNo && number <= toNo;
          return (
            <div key={item.id} className={`rounded-md border px-2 py-2 ${inPick ? "border-[var(--text)] bg-[rgb(31_30_27_/_0.06)]" : open ? "border-[var(--text)]" : "border-[var(--line)]"}`}>
              <button type="button" className="block w-full" title={picking ? "点这张，定这一组" : "点图放大"} onClick={() => onThumb(item, zoomIndex)}>
                <img
                  src={item.url || kbAssetFileUrl(item.id)}
                  alt={item.alt}
                  loading="lazy"
                  decoding="async"
                  className={`mx-auto h-28 w-full object-contain ${picking ? "cursor-pointer" : "cursor-zoom-in"}`}
                />
              </button>
              <p className="mt-1 truncate text-[12px] text-[var(--muted)]">{item.alt || "图"}</p>
              <p className="truncate">{draft.caption || "还没写图意"}</p>
              <div className="mt-1 flex flex-wrap gap-2 text-[12px]">
                <button type="button" className="text-[var(--muted)] underline" onClick={() => setOpenId(item.id)}>
                  改说明
                </button>
                <button type="button" className="text-[var(--muted)] underline disabled:opacity-50" disabled={visionLocked || seeingId != null} onClick={() => seeOne(item)}>
                  {seeingId === item.id ? "在认…" : "识图"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
      {!showAll && items.length > limit ? (
        <button type="button" className={`${btnClass} mt-2`} onClick={() => setShowAll(true)}>
          还有 {items.length - limit} 张，展开
        </button>
      ) : null}
      {editing && editDraft ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-[rgb(31_30_27_/_0.4)] px-4" onClick={closeEdit}>
          <div className="card max-h-[90vh] w-full max-w-xl overflow-y-auto px-5 py-4" onClick={(event) => event.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="font-medium">
                {editing.alt || "图"} · 改说明
                {items.length > 1 ? <span className="ml-2 font-normal text-[var(--muted)]">{editIndex + 1} / {items.length}</span> : null}
              </p>
              <button type="button" className="text-[13px] text-[var(--muted)]" disabled={savingId != null} onClick={closeEdit}>
                关闭
              </button>
            </div>
            <button
              type="button"
              className="mb-3 block"
              title="点图放大"
              onClick={() => setZoom(items.findIndex((row) => row.id === editing.id))}
            >
              <img
                src={editing.url || kbAssetFileUrl(editing.id)}
                alt={editing.alt}
                className="max-h-40 max-w-full cursor-zoom-in object-contain"
              />
            </button>
            {editHint ? <p className={`mb-2 text-[13px] ${editHint.ok ? "text-[var(--ok)]" : "text-amber-800"}`}>{editHint.text}</p> : null}
            <input
              className={`${inputClass} mb-1 w-full`}
              value={editDraft.caption}
              maxLength={200}
              onChange={(e) => patchDraft(editing.id, "caption", e.target.value)}
              placeholder={seeingId === editing.id ? "正在认这张…" : "图意，没字的图也写是什么"}
            />
            <input
              className={`${inputClass} mb-1 w-full`}
              value={editDraft.keywords}
              maxLength={200}
              onChange={(e) => patchDraft(editing.id, "keywords", e.target.value)}
              placeholder="关键词，逗号分隔"
            />
            <textarea
              className={`${inputClass} min-h-[4.5rem] w-full`}
              value={editDraft.words}
              maxLength={1500}
              onChange={(e) => patchDraft(editing.id, "words", e.target.value)}
              placeholder="图上的字，没有就留空"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className={btnClass} disabled={editIndex <= 0 || savingId != null || savingAll} onClick={() => goNear(-1)}>
                上一张
              </button>
              <button type="button" className={btnClass} disabled={editIndex < 0 || editIndex >= items.length - 1 || savingId != null || savingAll} onClick={() => goNear(1)}>
                {savingId != null ? "在存…" : "下一张"}
              </button>
              <button type="button" className={btnClass} disabled={visionLocked || seeingId != null} onClick={() => seeOne(editing)}>
                {seeingId === editing.id ? "在认…" : "识图"}
              </button>
              <button type="button" className={btnClass} disabled={savingId === editing.id || savingAll || !isDirty(editing)} onClick={() => void save(editing)}>
                {savingId === editing.id ? "在存…" : "保存这张"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {zoom != null ? <ImageLightbox items={zoomItems} index={zoom} onClose={() => setZoom(null)} onIndex={setZoom} /> : null}
    </div>
  );
}

/** 预览里看切片、改字。提问会尽量用这些块。 */
function ChunkWords({
  docId,
  onHint,
  onError,
  onDocChange,
}: {
  docId: number;
  onHint: (message: string, ok: boolean) => void;
  onError: (message: string) => void;
  onDocChange: () => void;
}) {
  const [items, setItems] = useState<KbChunk[]>([]);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [openId, setOpenId] = useState<number | null>(null);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setOpenId(null);
    setLoading(true);
    fetchKbDocumentChunks(docId)
      .then((data) => {
        if (!alive) return;
        setItems(data.items);
        setDrafts(Object.fromEntries(data.items.map((item) => [item.id, item.text])));
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [docId, onError]);

  if (loading) {
    return (
      <div className="mt-4 border-t border-[var(--line)] pt-3">
        <p className="font-medium">切片</p>
        <p className="text-[12px] text-[var(--muted)]">正在列出…</p>
      </div>
    );
  }
  if (!items.length) return null;

  function save(item: KbChunk) {
    const text = (drafts[item.id] ?? item.text).trim();
    if (!text) return;
    setSavingId(item.id);
    saveKbChunk(item.id, text)
      .then((row) => {
        setItems((list) => list.map((one) => (one.id === row.id ? row : one)));
        setDrafts((map) => ({ ...map, [row.id]: row.text }));
        onHint(row.vector_hint || (row.vector_ok ? "字已保存，这一块的向量已更新。" : "字已保存，向量没更新。"), !!row.vector_ok);
        onDocChange();
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setSavingId(null));
  }

  return (
    <div className="mt-4 border-t border-[var(--line)] pt-3">
      <p className="mb-1 font-medium">切片</p>
      <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">提问时尽量用这些块。点开一块能改，改完会按这一块重新找。</p>
      <div className="max-h-64 overflow-auto pr-1">
      {items.map((item, order) => {
        const open = openId === item.id;
        const draft = drafts[item.id] ?? item.text;
        return (
          <div key={item.id} className="mb-2 border-b border-[var(--line)] pb-2">
            <button type="button" className="flex w-full items-start gap-2 text-left" onClick={() => setOpenId(open ? null : item.id)}>
              <span className="shrink-0 text-[12px] text-[var(--muted)]">第{order + 1}块</span>
              <span className="min-w-0 flex-1 truncate">{item.preview || draft.slice(0, 80)}</span>
              {item.edited ? <span className="shrink-0 text-[12px] text-[var(--muted)]">已改</span> : null}
              <span className="shrink-0 text-[12px] text-[var(--muted)]">{open ? "收起" : "改"}</span>
            </button>
            {open ? (
              <div className="mt-2">
                <textarea
                  className={`${inputClass} min-h-[6rem] w-full`}
                  value={draft}
                  maxLength={8000}
                  onChange={(e) => setDrafts((map) => ({ ...map, [item.id]: e.target.value }))}
                />
                <button type="button" className={`${btnClass} mt-1`} disabled={savingId === item.id || !draft.trim()} onClick={() => save(item)}>
                  {savingId === item.id ? "在存…" : "保存"}
                </button>
              </div>
            ) : null}
          </div>
        );
      })}
      </div>
    </div>
  );
}

function ruleChoice(rule: Partial<KbCleanRule>): KbCleanRule {
  const how = rule.how === "start" || rule.how === "end" || rule.how === "regex" ? rule.how : "contains";
  const action = rule.action === "cut" || rule.action === "drop_line" || rule.action === "keep_line" ? rule.action : "replace";
  return { how, action, find: rule.find || "", replace: rule.replace || "" };
}

function flowChoice(item: KbDocument): KbDocFlow {
  const flow = item.flow;
  const chunk = flow?.chunk;
  const cleans = Array.isArray(flow?.cleans) ? flow.cleans : ["collapse"];
  return {
    parse: flow?.parse || "standard",
    parse_hint: flow?.parse_hint || "",
    parse_script: flow?.parse_script || "",
    cleans,
    rules: Array.isArray(flow?.rules) ? flow.rules.map(ruleChoice) : [],
    script: flow?.script || "",
    chunk: chunk === "paragraph" || chunk === "whole" ? chunk : "chars",
    vector: flow?.vector !== false,
    chunk_size: flow?.chunk_size || 400,
    chunk_overlap: flow?.chunk_overlap ?? 60,
    max_chunks: flow?.max_chunks || 40,
  };
}

function PreviewPane({
  item,
  text,
  wikiEnabled,
  visionEnabled,
  busy,
  assetTick,
  visionLocked,
  recognizing,
  onRecognizeAll,
  onSaved,
  onHint,
  onError,
  onClose,
}: {
  item: KbDocument;
  text: string;
  wikiEnabled: boolean;
  visionEnabled: boolean;
  busy: boolean;
  assetTick: number;
  visionLocked: boolean;
  recognizing: boolean;
  onRecognizeAll: () => void;
  onSaved: (row: KbDocument) => void;
  onHint: (message: string) => void;
  onError: (message: string) => void;
  onClose: () => void;
}) {
  const url = kbDocumentFileUrl(item.id);
  const readyUrl = kbDocumentReadyFileUrl(item.id);
  const [readyText, setReadyText] = useState("");
  const [draft, setDraft] = useState(item.wiki_summary || "");
  const [saving, setSaving] = useState(false);
  const [showExtras, setShowExtras] = useState(false);
  const [zoomFile, setZoomFile] = useState(false);
  const [vectorNote, setVectorNote] = useState<{ text: string; ok: boolean } | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [flow, setFlow] = useState<KbDocFlow>(() => flowChoice(item));
  const [chunkSize, setChunkSize] = useState(() => String(item.flow?.chunk_size || 400));
  const [chunkOverlap, setChunkOverlap] = useState(() => String(item.flow?.chunk_overlap ?? 60));
  const [maxChunks, setMaxChunks] = useState(() => String(item.flow?.max_chunks || 40));
  const [pane, setPane] = useState<DocPane>("file");
  const [ruleHow, setRuleHow] = useState<KbCleanRule["how"]>("contains");
  const [ruleAction, setRuleAction] = useState<KbCleanRule["action"]>("replace");
  const [ruleFind, setRuleFind] = useState("");
  const [ruleReplace, setRuleReplace] = useState("");
  const [quality, setQuality] = useState<KbQuality[]>([]);
  const [parseDraft, setParseDraft] = useState<string | null>(null);
  const [cleanDraft, setCleanDraft] = useState<string | null>(null);
  const [chunkDrafts, setChunkDrafts] = useState<KbChunk[] | null>(null);

  function tellVector(message: string, ok: boolean) {
    setVectorNote({ text: message, ok });
    onHint(message);
  }

  function rebuildVector() {
    setReindexing(true);
    reindexKbDocument(item.id)
      .then((row) => {
        tellVector(row.vector_hint || "这份资料的向量已重算。", !!row.vector_ok || row.vector_state === "ready");
        onSaved(row);
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setReindexing(false));
  }
  useEffect(() => {
    setDraft(item.wiki_summary || "");
  }, [item.id, item.wiki_summary]);
  useEffect(() => {
    setShowExtras(false);
    setZoomFile(false);
    setVectorNote(null);
    setPane("file");
    setRuleFind("");
    setRuleReplace("");
    setQuality([]);
    setParseDraft(null);
    setCleanDraft(null);
    setChunkDrafts(null);
    setFlow(flowChoice(item));
    setChunkSize(String(item.flow?.chunk_size || 400));
    setChunkOverlap(String(item.flow?.chunk_overlap ?? 60));
    setMaxChunks(String(item.flow?.max_chunks || 40));
    const timer = window.setTimeout(() => setShowExtras(true), 0);
    return () => window.clearTimeout(timer);
  }, [item.id]);
  useEffect(() => {
    if (!item.has_ready_draft) {
      setReadyText("");
      return;
    }
    let stop = false;
    fetchKbReadyText(item.id)
      .then((row) => {
        if (!stop) setReadyText(row.text || "");
      })
      .catch((err: Error) => onError(err.message));
    return () => {
      stop = true;
    };
  }, [item.id, item.has_ready_draft]);

  function applyFlow() {
    if (!isFlowPane(pane)) return;
    const num = (raw: string, fallback: number) => {
      const value = Number(raw);
      return Number.isFinite(value) ? value : fallback;
    };
    const step: FlowPane = pane;
    setProcessing(true);
    processKbDocument(item.id, step, {
      parse: flow.parse,
      parseHint: flow.parse_hint,
      parseScript: flow.parse_script,
      cleans: flow.cleans,
      rules: flow.rules,
      script: flow.script,
      chunk: flow.chunk,
      vector: flow.vector,
      chunkSize: num(chunkSize, 400),
      chunkOverlap: num(chunkOverlap, 60),
      maxChunks: num(maxChunks, 40),
    })
      .then((row) => {
        const message = row.message || row.vector_hint || "已按你选的方式处理这一份。";
        if (step === "clean") setQuality(row.quality || []);
        if ((step === "parse" || step === "clean") && row.result_text != null) {
          if (step === "parse") setParseDraft(row.result_text);
          else setCleanDraft(row.result_text);
        }
        if (step === "chunk" && row.chunks) setChunkDrafts(row.chunks);
        tellVector(message, !!row.vector_ok || row.vector_state === "ready");
        onSaved(row);
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setProcessing(false));
  }

  function saveReview() {
    if (pane !== "parse" && pane !== "clean") return;
    const text = pane === "parse" ? parseDraft : cleanDraft;
    if (text == null) return;
    setProcessing(true);
    saveKbStage(item.id, pane, text)
      .then((row) => {
        const saved = row.result_text || text;
        if (pane === "parse") setParseDraft(saved);
        else setCleanDraft(saved);
        tellVector(row.message || "已保存修改。下一步会用这段字。", true);
        onSaved(row);
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setProcessing(false));
  }

  function saveChunkDraft(id: number, text: string) {
    setProcessing(true);
    saveKbChunk(id, text, false)
      .then((row) => {
        setChunkDrafts((list) => (list ? list.map((one) => (one.id === row.id ? row : one)) : list));
        tellVector(row.vector_hint || "已保存这块。点「只处理向量」才算确认。", false);
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setProcessing(false));
  }

  function runAll() {
    const num = (raw: string, fallback: number) => {
      const value = Number(raw);
      return Number.isFinite(value) ? value : fallback;
    };
    setProcessing(true);
    processKbDocument(item.id, "all", {
      parse: flow.parse,
      parseHint: flow.parse_hint,
      parseScript: flow.parse_script,
      cleans: flow.cleans,
      rules: flow.rules,
      script: flow.script,
      chunk: flow.chunk,
      vector: flow.vector,
      chunkSize: num(chunkSize, 400),
      chunkOverlap: num(chunkOverlap, 60),
      maxChunks: num(maxChunks, 40),
    })
      .then((row) => {
        if (row.quality) setQuality(row.quality);
        if (row.result_text != null) setCleanDraft(row.result_text);
        if (row.chunks) setChunkDrafts(row.chunks);
        tellVector(row.message || row.vector_hint || "已按设置做完。", !!row.vector_ok || row.vector_state === "ready");
        onSaved(row);
      })
      .catch((err: Error) => onError(err.message))
      .finally(() => setProcessing(false));
  }

  function runWiki(task: () => Promise<void>, hint: string) {
    setSaving(true);
    task()
      .then(() => tellVector(hint, false))
      .catch((err: Error) => onError(err.message))
      .finally(() => setSaving(false));
  }

  return (
    <div className="flex h-full min-h-0 flex-col p-4 text-[13px]">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="flex min-w-0 flex-wrap items-center gap-2 font-medium">
          <span className="truncate">{item.title}</span>
          {vectorBadge(item.vector_state)}
        </p>
        <div className="flex flex-wrap items-center justify-end gap-2">
          <button type="button" className={btnClass} disabled={reindexing || busy || processing} onClick={runAll}>
            {processing ? "在处理…" : "按设置一次做完"}
          </button>
          <button type="button" className={btnClass} disabled={reindexing || busy || processing} onClick={rebuildVector}>
            {reindexing ? "在算…" : "重算向量"}
          </button>
          {visionEnabled ? (
            <button type="button" className={btnClass} disabled={busy || (visionLocked && !recognizing)} onClick={onRecognizeAll}>
              {recognizing ? "停止" : "全部识图"}
            </button>
          ) : null}
          <button type="button" className={btnClass} onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
      {item.tags ? <p className="mb-2 text-[var(--muted)]">{item.tags}</p> : null}
      <DocModuleBar pane={pane} onChange={setPane} />
      {vectorNote ? <p className={`mb-2 ${vectorNote.ok ? "text-[var(--ok)]" : "text-amber-800"}`}>{vectorNote.text}</p> : null}
      <div className="min-h-0 flex-1 overflow-auto">
      {isFlowPane(pane) ? (
        <FlowModulePanel
          pane={pane}
          fileName={item.file_name}
          flow={flow}
          chunkSize={chunkSize}
          chunkOverlap={chunkOverlap}
          maxChunks={maxChunks}
          ruleHow={ruleHow}
          ruleAction={ruleAction}
          ruleFind={ruleFind}
          ruleReplace={ruleReplace}
          busy={busy || processing || reindexing}
          onFlow={setFlow}
          onChunkSize={setChunkSize}
          onChunkOverlap={setChunkOverlap}
          onMaxChunks={setMaxChunks}
          onRuleHow={setRuleHow}
          onRuleAction={setRuleAction}
          onRuleFind={setRuleFind}
          onRuleReplace={setRuleReplace}
          onAddRule={() => {
            const find = ruleFind.trim();
            if (!find) return;
            setFlow({
              ...flow,
              rules: [...flow.rules, { how: ruleHow, action: ruleAction, find, replace: ruleAction === "replace" ? ruleReplace : "" }],
            });
            setRuleFind("");
            setRuleReplace("");
          }}
          onRemoveRule={(index) => setFlow({ ...flow, rules: flow.rules.filter((_, item) => item !== index) })}
          onApply={applyFlow}
          quality={quality}
          parseDraft={parseDraft}
          cleanDraft={cleanDraft}
          chunkDrafts={chunkDrafts}
          onParseDraft={setParseDraft}
          onCleanDraft={setCleanDraft}
          onChunkDraft={(id, text) => setChunkDrafts((list) => (list ? list.map((one) => (one.id === id ? { ...one, text } : one)) : list))}
          onSaveReview={saveReview}
          onSaveChunk={saveChunkDraft}
        />
      ) : null}
      <div className={pane === "file" ? "" : "hidden"}>
        {item.preview === "image" ? (
          <button type="button" className="block max-w-full" title="点图放大" onClick={() => setZoomFile(true)}>
            <img src={url} alt={item.title} className="max-h-[40vh] max-w-full cursor-zoom-in object-contain" />
          </button>
        ) : null}
        {item.preview === "pdf" ? <PdfPreview url={url} /> : null}
        {item.preview === "text" ? (
          <pre className="whitespace-pre-wrap bg-[var(--bg)] px-2 py-2 leading-6">{text || "正在读取…"}</pre>
        ) : null}
        {!item.preview && !item.has_ready_draft ? <p className="text-[var(--muted)]">这种文件一期先不预览内容，可以下载查看。</p> : null}
        {item.has_ready_draft ? (
          <div className="mt-3">
            <div className="flex flex-wrap gap-3">
              <a className="text-[var(--muted)] underline" href={url} target="_blank" rel="noreferrer">
                打开原件
              </a>
              <a className="text-[var(--muted)] underline" href={readyUrl} target="_blank" rel="noreferrer">
                打开整理稿
              </a>
              <button type="button" className="text-[var(--muted)] underline" onClick={() => setPane("images")}>
                看图片
              </button>
              <button type="button" className="text-[var(--muted)] underline" onClick={() => setPane("chunks")}>
                看切片
              </button>
            </div>
            <p className="mt-3 text-[12px] leading-5 text-[var(--muted)]">下面是整理稿里的正文，切片用的是这些字。图片仍是从原件抽出的。</p>
            <pre className="mt-2 whitespace-pre-wrap bg-[var(--bg)] px-2 py-2 leading-6">{readyText || "正在读取整理稿…"}</pre>
          </div>
        ) : (
          <a className="mt-3 inline-block text-[var(--muted)] underline" href={url} target="_blank" rel="noreferrer">
            打开 / 下载
          </a>
        )}
      </div>

      <div className={pane === "images" ? "" : "hidden"}>
        {showExtras ? (
          <AssetWords
            docId={item.id}
            refreshTick={assetTick}
            visionLocked={visionLocked}
            onHint={tellVector}
            onError={onError}
            onDocChange={() => {
              void fetchKbDocument(item.id).then(onSaved);
            }}
          />
        ) : (
          <p className="text-[12px] text-[var(--muted)]">正在加载图…</p>
        )}
      </div>
      <div className={pane === "chunks" ? "" : "hidden"}>
        {showExtras ? (
          <ChunkWords
            docId={item.id}
            onHint={tellVector}
            onError={onError}
            onDocChange={() => {
              void fetchKbDocument(item.id).then(onSaved);
            }}
          />
        ) : (
          <p className="text-[12px] text-[var(--muted)]">正在加载切片…</p>
        )}
      </div>

      <div className={pane === "wiki" ? "border-t border-[var(--line)] pt-3" : "hidden"}>
        <p className="mb-1 font-medium">
          摘要
          {item.wiki_stale ? <span className="ml-2 font-normal text-[var(--muted)]">可能过期</span> : null}
        </p>
        {wikiEnabled ? (
          <>
            <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">
              开 Wiki 不会自动写。点「写摘要」让 AI 写，或自己填再保存。只给这一份资料写。
            </p>
            <textarea
              className={`${inputClass} min-h-[6rem] w-full`}
              value={draft}
              maxLength={400}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="这份资料是什么、关键看哪"
            />
            <p className="mt-1 text-[12px] text-[var(--muted)]">已写 {draft.length} / 400</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                className={btnClass}
                disabled={saving || busy}
                onClick={() =>
                  runWiki(async () => {
                    onSaved(await generateKbWiki(item.id));
                  }, "摘要已保存。摘要不进向量，提问不靠它。")
                }
              >
                {item.has_wiki ? "更新" : "写摘要"}
              </button>
              <button
                type="button"
                className={btnClass}
                disabled={saving || busy || !draft.trim()}
                onClick={() =>
                  runWiki(async () => {
                    onSaved(await saveKbWiki(item.id, draft));
                  }, "摘要已保存。摘要不进向量，提问不靠它。")
                }
              >
                保存
              </button>
              {item.has_wiki ? (
                <button
                  type="button"
                  className={btnClass}
                  disabled={saving || busy}
                  onClick={() =>
                    runWiki(async () => {
                      onSaved(await deleteKbWiki(item.id));
                    }, "摘要已删。摘要不进向量，提问不靠它。")
                  }
                >
                  删除
                </button>
              ) : null}
            </div>
          </>
        ) : item.wiki_summary ? (
          <p className="whitespace-pre-wrap leading-6 text-[var(--muted)]">{item.wiki_summary}</p>
        ) : (
          <p className="leading-5 text-[var(--muted)]">
            这个库还没开 Wiki。去「库设置」勾选并保存规则后，再回到这里写摘要。开了也不会自动写。
          </p>
        )}
      </div>
      </div>
      {zoomFile ? <ImageLightbox items={[{ src: url, alt: item.title }]} index={0} onClose={() => setZoomFile(false)} /> : null}
    </div>
  );
}
