import { File, FileText, Folder, Image as ImageIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  createKbFolder,
  createKbLibrary,
  deleteKbDocument,
  deleteKbFolder,
  deleteKbLibrary,
  fetchKbDocumentText,
  fetchKbDocuments,
  fetchKbFolders,
  fetchKbLibraries,
  kbDocumentFileUrl,
  renameKbFolder,
  updateKbDocument,
  updateKbLibrary,
  uploadKbDocument,
} from "@/api/client";
import type { KbDocument, KbFolder, KbLibrary } from "@/api/types";
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

/** 知识库一期：多库、文件夹、上传、预览 */
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

  function onPickLibrary(id: number) {
    setLibraryId(id);
    setFolderId(null);
    setPreview(null);
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
      {error ? <p className="text-[13px] text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="text-[13px] text-[var(--ok)]">{hint}</p> : null}

      <div className="flex flex-wrap items-center gap-2 text-[13px]">
        <select
          className={inputClass}
          value={libraryId ?? ""}
          onChange={(event) => onPickLibrary(Number(event.target.value))}
        >
          {libraries.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <input className={`${inputClass} w-36`} placeholder="新库名 / 改名" value={libName} onChange={(e) => setLibName(e.target.value)} />
        <button type="button" className={btnClass} disabled={busy} onClick={onCreateLibrary}>
          新建库
        </button>
        <button type="button" className={btnClass} disabled={busy || !library} onClick={onRenameLibrary}>
          改库名
        </button>
        <button type="button" className={btnClass} disabled={busy || !library} onClick={() => setAskDeleteLib(true)}>
          删库
        </button>
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        <aside className="w-52 shrink-0 overflow-auto border border-[var(--line)] bg-[var(--paper)] p-2">
          <button
            type="button"
            className={`mb-1 block w-full px-2 py-1 text-left text-[13px] ${folderId == null ? "bg-[var(--bg)]" : ""}`}
            onClick={() => onOpenFolder(null)}
          >
            全部（库根）
          </button>
          <FolderTree items={folders} parentId={null} currentId={folderId} onOpen={onOpenFolder} />
        </aside>

        <section className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <button type="button" className="text-[var(--muted)]" onClick={() => onOpenFolder(null)}>
              {library?.name || "库"}
            </button>
            {crumbs.map((item) => (
              <span key={item.id} className="flex items-center gap-2">
                <span className="text-[var(--muted)]">/</span>
                <button type="button" onClick={() => onOpenFolder(item.id)}>
                  {item.name}
                </button>
              </span>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <input className={`${inputClass} w-32`} placeholder="新文件夹" value={folderName} onChange={(e) => setFolderName(e.target.value)} />
            <button type="button" className={btnClass} disabled={busy || !library} onClick={onCreateFolder}>
              新建文件夹
            </button>
            <input className={`${inputClass} w-32`} placeholder="搜名称" value={query} onChange={(e) => setQuery(e.target.value)} />
            <input className={`${inputClass} w-28`} placeholder="标签" value={tag} onChange={(e) => setTag(e.target.value)} />
            <button type="button" className={btnClass} disabled={busy || !library} onClick={onSearch}>
              筛选
            </button>
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

          <div className="min-h-0 flex-1 overflow-auto border border-[var(--line)] bg-[var(--paper)]">
            {!searching
              ? hereFolders.map((item) => (
                  <div key={`f-${item.id}`} className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2 text-[13px]">
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
              return (
                <div key={item.id} className="flex items-center justify-between gap-2 border-b border-[var(--line)] px-3 py-2 text-[13px]">
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
              <p className="px-3 py-6 text-[13px] text-[var(--muted)]">{searching ? "没有符合的资料" : "这个文件夹还是空的，可以上传或新建文件夹。"}</p>
            ) : null}
          </div>
        </section>

        <aside className="hidden w-[22rem] shrink-0 overflow-auto border border-[var(--line)] bg-[var(--paper)] p-3 xl:block">
          {preview ? (
            <PreviewPane item={preview} text={previewText} />
          ) : (
            <p className="text-[13px] leading-6 text-[var(--muted)]">点一份资料，右边预览。</p>
          )}
        </aside>
      </div>

      {preview && (
        <div className="xl:hidden">
          <Modal title={preview.title} wide onClose={() => setPreview(null)}>
            <PreviewPane item={preview} text={previewText} />
          </Modal>
        </div>
      )}

      {renameFolder ? (
        <Modal title="重命名文件夹" onClose={() => setRenameFolder(null)}>
          <input className={`${inputClass} w-full`} value={renameFolderTo} onChange={(e) => setRenameFolderTo(e.target.value)} />
          <button
            type="button"
            className="mt-3"
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
            className="mt-3"
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
            className={`block w-full truncate px-2 py-1 text-left text-[13px] ${currentId === item.id ? "bg-[var(--bg)]" : ""}`}
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

function PreviewPane({ item, text }: { item: KbDocument; text: string }) {
  const url = kbDocumentFileUrl(item.id);
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
    </div>
  );
}
