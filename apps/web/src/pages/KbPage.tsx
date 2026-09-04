import { File, FileText, Folder, Image as ImageIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  askKbLibrary,
  createKbFolder,
  createKbLibrary,
  deleteKbDocument,
  deleteKbFolder,
  deleteKbLibrary,
  deleteKbWiki,
  fetchKbDocument,
  fetchKbDocumentText,
  fetchKbDocuments,
  fetchKbFolders,
  fetchKbLibraries,
  fetchKbWikis,
  generateKbWiki,
  kbAssetFileUrl,
  kbDocumentFileUrl,
  renameKbFolder,
  saveKbWiki,
  updateKbDocument,
  updateKbLibrary,
  updateKbLibraryPolicy,
  uploadKbDocument,
} from "@/api/client";
import type { KbAskResult, KbDocument, KbEvidenceMode, KbFolder, KbLibrary, KbWikiList } from "@/api/types";
import { ConfirmModal, Modal } from "@/components/Modal";
import { PdfPreview } from "@/components/PdfPreview";

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

/** 这次回答带上的相关图，用来直接画在回答里。 */
function relatedAskImages(result: KbAskResult) {
  return result.citations.flatMap((hit) => (hit.images || []).map((img) => ({ ...img, docId: hit.id })));
}

function evidenceHint(mode: "" | KbEvidenceMode, libraryMode: KbEvidenceMode = "strict") {
  if (!mode) {
    return `按库规则：这次跟库里设的走，当前是${evidenceLabel(libraryMode)}。`;
  }
  if (mode === "loose") {
    return "宽松概述：可以概括，仍要标明哪份资料；拿不准就回原文。";
  }
  return "严格出处：只根据原文片段回答，摘要不能当证据。";
}

/** 知识库：整理资料，并按当前库提问 */
export function KbPage() {
  const location = useLocation();
  const uploadRef = useRef<HTMLInputElement>(null);
  const [libraries, setLibraries] = useState<KbLibrary[]>([]);
  const [libraryId, setLibraryId] = useState<number | null>(null);
  const [folders, setFolders] = useState<KbFolder[]>([]);
  const [folderId, setFolderId] = useState<number | null>(null);
  const [docs, setDocs] = useState<KbDocument[]>([]);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<KbDocument | null>(null);
  const [previewText, setPreviewText] = useState("");
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
  const [uploadTags, setUploadTags] = useState("");
  const [manageLib, setManageLib] = useState(false);
  const [question, setQuestion] = useState("");
  const [onlyFolder, setOnlyFolder] = useState(false);
  const [askResult, setAskResult] = useState<KbAskResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [askMode, setAskMode] = useState<"" | KbEvidenceMode>("");
  const [wikiEnabled, setWikiEnabled] = useState(false);
  const [wikiLearn, setWikiLearn] = useState(false);
  const [libMode, setLibMode] = useState<KbEvidenceMode>("strict");
  const [libRule, setLibRule] = useState("");
  const [wikiList, setWikiList] = useState<KbWikiList | null>(null);
  const [wikiQ, setWikiQ] = useState("");
  const [wikiStale, setWikiStale] = useState("");
  const [wikiSort, setWikiSort] = useState("updated_at");
  const [wikiOrder, setWikiOrder] = useState("desc");
  const [wikiPage, setWikiPage] = useState(1);

  const library = libraries.find((item) => item.id === libraryId) || null;

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
    if (!preview || preview.preview !== "text") {
      setPreviewText("");
      return;
    }
    fetchKbDocumentText(preview.id)
      .then((data) => setPreviewText(data.text))
      .catch((err: Error) => setPreviewText(err.message));
  }, [preview]);

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

  function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setHint("");
    task()
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }

  function onAsk() {
    if (libraryId == null) return;
    const text = question.trim();
    if (!text) return;
    setAsking(true);
    setError("");
    setHint("");
    askKbLibrary(libraryId, text, folderId, onlyFolder, askMode)
      .then(async (data) => {
        setAskResult(data);
        if (data.wiki_update_hint && preview) {
          applyDoc(await fetchKbDocument(preview.id));
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setAsking(false));
  }

  function onOpenCitation(id: number) {
    const found = docs.find((item) => item.id === id);
    if (found) {
      setPreview(found);
      return;
    }
    fetchKbDocument(id)
      .then((item) => setPreview(item))
      .catch((err: Error) => setError(err.message));
  }

  function onPickLibrary(id: number) {
    setLibraryId(id);
    setFolderId(null);
    setPreview(null);
    setAskResult(null);
    run(async () => {
      await loadFolders(id);
      await loadDocs(id, null);
    });
  }

  function onOpenFolder(id: number | null) {
    setFolderId(id);
    setPreview(null);
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
    if (library) {
      setWikiEnabled(!!library.wiki_enabled);
      setWikiLearn(!!library.wiki_learn);
      setLibMode(library.evidence_mode || "strict");
      setLibRule(library.rule || "");
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

  async function doUpload(file: File, force: boolean) {
    if (libraryId == null) return;
    await uploadKbDocument(libraryId, file, folderId, uploadTags, force);
    setUploadTags("");
    await loadDocs(libraryId, folderId);
    setHint("已上传");
  }

  function onUpload(file: File) {
    run(async () => {
      try {
        await doUpload(file, false);
      } catch (err) {
        const message = err instanceof Error ? err.message : "上传失败";
        if (message.includes("已有相同文件")) {
          setPendingFile(file);
          setError(message);
          return;
        }
        throw err;
      }
    });
  }

  const hereFolders = childFolders(folders, folderId);
  const searching = Boolean(query.trim() || tag.trim());

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h1 className="shrink-0">知识库</h1>
          <select
            className={`${inputClass} min-w-[8rem]`}
            value={libraryId ?? ""}
            onChange={(event) => onPickLibrary(Number(event.target.value))}
          >
            {libraries.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <button type="button" className={btnClass} onClick={openManage}>
            管理库
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <input
            className={`${inputClass} w-40`}
            placeholder="搜名称"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
          />
          <input
            className={`${inputClass} w-28`}
            placeholder="标签"
            value={tag}
            onChange={(e) => setTag(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
          />
          <button type="button" className={btnClass} disabled={busy || !library} onClick={onSearch}>
            筛选
          </button>
        </div>
      </div>

      {error ? <p className="text-[13px] text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="text-[13px] text-[var(--ok)]">{hint}</p> : null}

      {library ? (
        <div className="shrink-0 rounded-lg border border-[var(--line)] bg-[var(--paper)] px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <input
              className={`${inputClass} min-w-[12rem] flex-1`}
              placeholder="问当前库里的资料"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onAsk()}
            />
            <label className="flex items-center gap-1 text-[13px] text-[var(--muted)]">
              <input
                type="checkbox"
                checked={onlyFolder && folderId != null}
                disabled={folderId == null}
                onChange={(e) => setOnlyFolder(e.target.checked)}
              />
              只搜当前文件夹
            </label>
            <select className={inputClass} value={askMode} onChange={(e) => setAskMode(e.target.value as "" | KbEvidenceMode)}>
              <option value="">按库规则（当前：{evidenceLabel(library.evidence_mode || "strict")}）</option>
              <option value="strict">严格出处</option>
              <option value="loose">宽松概述</option>
            </select>
            <button type="button" className={btnClass} disabled={asking || !question.trim()} onClick={onAsk}>
              {asking ? "在找…" : "提问"}
            </button>
          </div>
          <p className="mt-1 text-[12px] leading-5 text-[var(--muted)]">{evidenceHint(askMode, library.evidence_mode || "strict")}</p>
          {askResult ? (
            <div className="mt-2 border-t border-[var(--line)] pt-2 text-[13px] leading-6">
              <p className="whitespace-pre-wrap">{askResult.answer}</p>
              {relatedAskImages(askResult).length ? (
                <div className="mt-2 flex flex-wrap gap-2">
                  {relatedAskImages(askResult).map((img) => (
                    <button
                      key={img.id}
                      type="button"
                      className="max-w-[12rem] text-left text-[12px] text-[var(--muted)]"
                      title={img.alt}
                      onClick={() => onOpenCitation(img.docId)}
                    >
                      <img
                        src={img.url || kbAssetFileUrl(img.id)}
                        alt={img.alt}
                        className="max-h-40 w-auto rounded border border-[var(--line)] object-contain"
                      />
                      {img.alt ? <span className="mt-1 block">{img.alt}</span> : null}
                    </button>
                  ))}
                </div>
              ) : null}
              {askResult.citations.length ? (
                <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[var(--muted)]">
                  <span>出处</span>
                  {askResult.citations.map((hit) => (
                    <button key={hit.id} type="button" className="underline hover:text-[var(--text)]" onClick={() => onOpenCitation(hit.id)}>
                      {hit.title}
                    </button>
                  ))}
                </p>
              ) : null}
              {askResult.used_vector ? <p className="mt-2 text-[12px] text-[var(--muted)]">本次还用了向量检索，换说法也能对上。</p> : null}
              {askResult.wiki_update_hint ? <p className="mt-2 text-[12px] text-[var(--muted)]">{askResult.wiki_update_hint}</p> : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--paper)] md:grid-cols-[220px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)_300px]">
        <aside className="flex min-h-0 flex-col border-b border-[var(--line)] md:border-b-0 md:border-r">
          <div className="border-b border-[var(--line)] px-3 py-2 text-[12px] text-[var(--muted)]">文件夹</div>
          <div className="min-h-0 flex-1 overflow-auto p-2">
            <button
              type="button"
              className={`mb-0.5 block w-full rounded-md px-2 py-1.5 text-left text-[13px] ${folderId == null ? "bg-[var(--bg)]" : "hover:bg-[var(--hover)]"}`}
              onClick={() => onOpenFolder(null)}
            >
              全部（库根）
            </button>
            <FolderTree items={folders} parentId={null} currentId={folderId} onOpen={onOpenFolder} />
          </div>
          <div className="flex gap-2 border-t border-[var(--line)] p-2">
            <input className={`${inputClass} min-w-0 flex-1`} placeholder="新文件夹" value={folderName} onChange={(e) => setFolderName(e.target.value)} />
            <button type="button" className={`${btnClass} shrink-0`} disabled={busy || !library} onClick={onCreateFolder}>
              新建
            </button>
          </div>
        </aside>

        <section className="flex min-h-0 min-w-0 flex-col xl:border-r">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2">
            <div className="flex min-w-0 flex-wrap items-center gap-1 text-[13px]">
              <button type="button" className="text-[var(--muted)] hover:text-[var(--text)]" onClick={() => onOpenFolder(null)}>
                {library?.name || "库"}
              </button>
              {crumbs.map((item) => (
                <span key={item.id} className="flex items-center gap-1">
                  <span className="text-[var(--muted)]">/</span>
                  <button type="button" onClick={() => onOpenFolder(item.id)}>
                    {item.name}
                  </button>
                </span>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input className={`${inputClass} w-28`} placeholder="上传标签" value={uploadTags} onChange={(e) => setUploadTags(e.target.value)} />
              <button type="button" className={btnClass} disabled={busy || !library} onClick={() => uploadRef.current?.click()}>
                上传
              </button>
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
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {!searching
              ? hereFolders.map((item) => (
                  <div key={`f-${item.id}`} className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2.5 text-[13px] hover:bg-[var(--bg)]">
                    <button type="button" className="flex items-center gap-2" onClick={() => onOpenFolder(item.id)}>
                      <Folder className="h-4 w-4 text-amber-500" />
                      {item.name}
                    </button>
                    <span className="flex gap-2 text-[var(--muted)]">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setRenameFolder(item);
                          setRenameFolderTo(item.name);
                        }}
                      >
                        重命名
                      </button>
                      <button type="button" disabled={busy} onClick={() => setAskDeleteFolder(item)}>
                        删除
                      </button>
                    </span>
                  </div>
                ))
              : null}
            {docs.map((item) => {
              const { Icon, color } = docIcon(item);
              const active = preview?.id === item.id;
              return (
                <div
                  key={item.id}
                  className={`flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2.5 text-[13px] ${active ? "bg-[var(--bg)]" : "hover:bg-[var(--bg)]"}`}
                >
                  <button type="button" className="flex min-w-0 items-center gap-2 text-left" onClick={() => setPreview(item)}>
                    <Icon className={`h-4 w-4 shrink-0 ${color}`} />
                    <span className="truncate">{item.title}</span>
                    {item.tags ? <span className="truncate text-[var(--muted)]">{item.tags}</span> : null}
                  </button>
                  <span className="flex shrink-0 gap-2 text-[var(--muted)]">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setEditDoc(item);
                        setEditTitle(item.title);
                        setEditTags(item.tags);
                      }}
                    >
                      编辑
                    </button>
                    <button type="button" disabled={busy} onClick={() => setAskDeleteDoc(item)}>
                      删除
                    </button>
                  </span>
                </div>
              );
            })}
            {!hereFolders.length && !docs.length ? (
              <div className="flex h-full min-h-[12rem] flex-col items-center justify-center gap-3 px-6 text-center">
                <p className="text-[13px] leading-6 text-[var(--muted)]">
                  {searching ? "没有符合的资料。" : "这里还是空的。左边可以建文件夹，右上角可以上传。"}
                </p>
                {!searching ? (
                  <button type="button" className={btnClass} disabled={busy || !library} onClick={() => uploadRef.current?.click()}>
                    上传资料
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        <aside className="hidden min-h-0 flex-col xl:flex">
          <div className="border-b border-[var(--line)] px-3 py-2 text-[12px] text-[var(--muted)]">预览</div>
          <div className="min-h-0 flex-1 overflow-auto p-3">
            {preview ? (
              <PreviewPane
                item={preview}
                text={previewText}
                wikiEnabled={!!library?.wiki_enabled}
                busy={busy}
                onSaved={applyDoc}
                onError={setError}
              />
            ) : (
              <p className="pt-8 text-center text-[13px] leading-6 text-[var(--muted)]">点一份资料，这里预览。</p>
            )}
          </div>
        </aside>
      </div>

      {preview && (
        <div className="xl:hidden">
          <Modal title={preview.title} wide onClose={() => setPreview(null)}>
            <PreviewPane
              item={preview}
              text={previewText}
              wikiEnabled={!!library?.wiki_enabled}
              busy={busy}
              onSaved={applyDoc}
              onError={setError}
            />
          </Modal>
        </div>
      )}

      {manageLib ? (
        <Modal title="管理知识库" wide onClose={() => setManageLib(false)}>
          <p className="mb-2 text-[13px] text-[var(--muted)]">当前：{library?.name || "无"}</p>
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
              className={btnClass}
              disabled={busy || !library}
              onClick={() => {
                setManageLib(false);
                setAskDeleteLib(true);
              }}
            >
              删库
            </button>
          </div>

          <div className="mt-5 border-t border-[var(--line)] pt-4">
            <p className="mb-2 text-[13px] font-medium">库规则</p>
            <label className="mb-2 flex items-center gap-2 text-[13px]">
              <input
                type="checkbox"
                checked={wikiEnabled}
                onChange={(e) => {
                  setWikiEnabled(e.target.checked);
                  if (!e.target.checked) setWikiLearn(false);
                }}
              />
              开启 Wiki
            </label>
            <label className="mb-2 flex items-center gap-2 text-[13px]">
              <input
                type="checkbox"
                checked={wikiLearn && wikiEnabled}
                disabled={!wikiEnabled}
                onChange={(e) => setWikiLearn(e.target.checked)}
              />
              跟着提问更新
            </label>
            <p className="mb-3 text-[12px] leading-5 text-[var(--muted)]">
              Wiki 只是开关，打开后才允许写摘要，不会自动给全库写。
              <br />
              要手写：关掉本框 → 点一份资料 → 右边预览滚到最下面 → 点「写摘要」或自己填。
              <br />
              「跟着提问更新」开着：问完后只改这次出处里最相关的最多 5 份摘要。没出处就不改、也不提示。
              <br />
              关掉 Wiki：已有摘要还在，只是不能新写，提问也不用。改完请点下面的「保存规则」。
            </p>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[13px]">
              <span className="text-[var(--muted)]">回答风格</span>
              <select className={inputClass} value={libMode} onChange={(e) => setLibMode(e.target.value as KbEvidenceMode)}>
                <option value="strict">严格出处</option>
                <option value="loose">宽松概述</option>
              </select>
            </div>
            <p className="mb-2 text-[12px] leading-5 text-[var(--muted)]">
              严格出处：只根据原文片段回答，摘要不能当证据。
              <br />
              宽松概述：可以参考摘要帮忙概括，但仍要标明哪份资料；拿不准就回原文。
              <br />
              提问时选「按库规则」就用这里的设置，也可以临时改成另一种。
            </p>
            <input
              className={`${inputClass} w-full`}
              placeholder="额外规则，可空"
              value={libRule}
              onChange={(e) => setLibRule(e.target.value)}
            />
            <button
              type="button"
              className={`${btnClass} mt-3`}
              disabled={busy || !library}
              onClick={() =>
                run(async () => {
                  if (!library) return;
                  const row = await updateKbLibraryPolicy(library.id, wikiEnabled, libMode, libRule, wikiLearn);
                  setLibraries((items) => items.map((item) => (item.id === row.id ? row : item)));
                  setHint("已保存库规则");
                })
              }
            >
              保存规则
            </button>
          </div>

          <div className="mt-5 border-t border-[var(--line)] pt-4">
            <p className="mb-2 text-[13px] font-medium">摘要</p>
            <p className="mb-2 text-[13px] leading-5 text-[var(--muted)]">
              这里只列出已经写过的摘要。开了 Wiki 但没写过，这里就是空的。
              <br />
              本库已有 {wikiList?.all_count ?? 0} 条，其中 {wikiList?.stale_count ?? 0} 条可能过期。
            </p>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <input
                className={`${inputClass} w-40`}
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
                <div key={item.id} className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-2 py-2 text-[13px]">
                  <button
                    type="button"
                    className="min-w-0 truncate text-left"
                    onClick={() =>
                      run(async () => {
                        const row = await fetchKbDocument(item.id);
                        setPreview(row);
                        setManageLib(false);
                      })
                    }
                  >
                    {item.title}
                    {item.wiki_stale ? <span className="ml-2 text-[var(--muted)]">可能过期</span> : null}
                  </button>
                  <button
                    type="button"
                    className="shrink-0 text-[var(--muted)]"
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
                <p className="px-2 py-6 text-center text-[13px] leading-5 text-[var(--muted)]">
                  还没有摘要。请先保存规则并开启 Wiki，然后关掉本框，点一份资料，在预览最下面写。
                </p>
              ) : null}
            </div>
            {wikiList && wikiList.total > wikiList.page_size ? (
              <div className="mt-2 flex items-center gap-2 text-[13px] text-[var(--muted)]">
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
        </Modal>
      ) : null}

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

      {askDeleteLib ? (
        <ConfirmModal
          title="删除这个库？"
          message="库里的文件夹和文件都会删掉。"
          busy={busy}
          onClose={() => setAskDeleteLib(false)}
          onConfirm={() => {
            if (!library) return;
            run(async () => {
              await deleteKbLibrary(library.id);
              setAskDeleteLib(false);
              setFolderId(null);
              setPreview(null);
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
              if (preview?.id === target.id) setPreview(null);
              if (libraryId) await loadDocs(libraryId, folderId);
            });
          }}
        />
      ) : null}

      {pendingFile ? (
        <ConfirmModal
          title="仍要另存一份？"
          message={error || "库里已有相同文件。"}
          confirmLabel="另存"
          busy={busy}
          onClose={() => setPendingFile(null)}
          onConfirm={() => {
            const file = pendingFile;
            setPendingFile(null);
            run(async () => {
              await doUpload(file, true);
            });
          }}
        />
      ) : null}
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

function PreviewPane({
  item,
  text,
  wikiEnabled,
  busy,
  onSaved,
  onError,
}: {
  item: KbDocument;
  text: string;
  wikiEnabled: boolean;
  busy: boolean;
  onSaved: (row: KbDocument) => void;
  onError: (message: string) => void;
}) {
  const url = kbDocumentFileUrl(item.id);
  const [draft, setDraft] = useState(item.wiki_summary || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setDraft(item.wiki_summary || "");
  }, [item.id, item.wiki_summary]);

  function runWiki(task: () => Promise<void>) {
    setSaving(true);
    task()
      .catch((err: Error) => onError(err.message))
      .finally(() => setSaving(false));
  }

  return (
    <div className="text-[13px]">
      <p className="mb-2 font-medium">{item.title}</p>
      {item.tags ? <p className="mb-2 text-[var(--muted)]">{item.tags}</p> : null}
      {item.preview === "image" ? <img src={url} alt={item.title} className="max-h-[60vh] max-w-full object-contain" /> : null}
      {item.preview === "pdf" ? <PdfPreview url={url} /> : null}
      {item.preview === "text" ? (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap bg-[var(--bg)] px-2 py-2 leading-6">{text || "正在读取…"}</pre>
      ) : null}
      {!item.preview ? <p className="text-[var(--muted)]">这种文件一期先不预览内容，可以下载查看。</p> : null}
      <a className="mt-3 inline-block text-[var(--muted)] underline" href={url} target="_blank" rel="noreferrer">
        打开 / 下载
      </a>

      <div className="mt-4 border-t border-[var(--line)] pt-3">
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
                  })
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
                  })
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
                    })
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
            这个库还没开 Wiki。去「管理库」勾选并保存规则后，再回到这里写摘要。开了也不会自动写。
          </p>
        )}
      </div>
    </div>
  );
}
