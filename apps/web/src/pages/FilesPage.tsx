import { File, FileSpreadsheet, FileText, Folder, Image as ImageIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import {
  deleteFilesEntry,
  downloadFilesEntry,
  fetchFilesList,
  fetchFilesStatus,
  makeFilesDir,
  moveFilesEntry,
  openFilesEntry,
  renameFilesEntry,
  searchFiles,
  uploadFiles,
} from "@/api/client";
import type { FilesEntry, FilesList, FilesStatus } from "@/api/types";
import { Card } from "@/components/Card";
import { ConfirmModal, Modal } from "@/components/Modal";
import { PdfPreview } from "@/components/PdfPreview";

const inputClass = "border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px]";

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function itemIcon(item: FilesEntry) {
  if (item.kind === "dir") return { Icon: Folder, color: "text-amber-500" };
  if (item.preview === "image") return { Icon: ImageIcon, color: "text-sky-500" };
  if (item.preview === "text" || item.preview === "pdf") return { Icon: FileText, color: "text-slate-500" };
  const ext = item.name.split(".").pop()?.toLowerCase() || "";
  if (["xls", "xlsx", "csv"].includes(ext)) return { Icon: FileSpreadsheet, color: "text-emerald-600" };
  return { Icon: File, color: "text-[var(--muted)]" };
}

/** 文件柜：只管理设置里指定的那个文件夹 */
export function FilesPage() {
  const [status, setStatus] = useState<FilesStatus | null>(null);
  const [list, setList] = useState<FilesList | null>(null);
  const [path, setPath] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<FilesEntry[] | null>(null);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [renameFrom, setRenameFrom] = useState<FilesEntry | null>(null);
  const [renameTo, setRenameTo] = useState("");
  const [moveFrom, setMoveFrom] = useState<FilesEntry | null>(null);
  const [moveTo, setMoveTo] = useState("");
  const [ask, setAsk] = useState<FilesEntry | null>(null);
  const [preview, setPreview] = useState<FilesEntry | null>(null);
  const [previewText, setPreviewText] = useState("");
  const uploadRef = useRef<HTMLInputElement>(null);
  const location = useLocation();

  async function load(next = path) {
    const data = await fetchFilesList(next);
    setList(data);
    setPath(data.path);
    setHits(null);
  }

  useEffect(() => {
    if (location.pathname !== "/m/files") return;
    fetchFilesStatus()
      .then((data) => {
        setStatus(data);
        if (data.ready) {
          return load("");
        }
        setList(null);
        return undefined;
      })
      .catch((err: Error) => setError(err.message));
  }, [location.pathname]);

  async function openDir(next: string) {
    setError("");
    setHint("");
    setQuery("");
    try {
      await load(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "打不开");
    }
  }

  async function onSearch() {
    const text = query.trim();
    if (!text) {
      setHits(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await searchFiles(text, path);
      setHits(data.items);
      setHint(data.items.length ? `找到 ${data.items.length} 项` : "没有找到");
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索失败");
    } finally {
      setBusy(false);
    }
  }

  async function onMkdir() {
    const name = folderName.trim();
    if (!name) {
      setError("请填写文件夹名");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await makeFilesDir(path, name);
      setFolderName("");
      await load(path);
      setHint("文件夹已建好");
    } catch (err) {
      setError(err instanceof Error ? err.message : "新建失败");
    } finally {
      setBusy(false);
    }
  }

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    setError("");
    try {
      await uploadFiles(path, Array.from(files));
      await load(path);
      setHint("已上传");
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }

  async function openPreview(item: FilesEntry) {
    setPreview(item);
    setPreviewText("");
    if (item.preview === "text") {
      try {
        const res = await fetch(`/api/v1/files/text?path=${encodeURIComponent(item.path)}`);
        setPreviewText(await res.text());
      } catch {
        setPreviewText("打不开这张文本");
      }
    }
  }

  function clickItem(item: FilesEntry) {
    if (item.kind === "dir") {
      void openDir(item.path);
      return;
    }
    void openPreview(item);
  }

  if (!status) {
    return <p className="text-[13px] text-[var(--muted)]">正在读取…</p>;
  }

  if (!status.ready) {
    return (
      <Card className="px-5 py-4">
        <p className="text-[13px] leading-6 text-[var(--muted)]">
          {status.configured ? status.message || "设置里的文件夹找不到了，请回去改路径。" : "还没有指定根目录。先去设置里填一个电脑上的文件夹，填好才能用。"}
        </p>
        <Link to="/settings" className="mt-4 inline-block border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px]">
          去设置
        </Link>
      </Card>
    );
  }

  const shown = hits ?? list?.items ?? [];
  const searching = hits !== null;

  return (
    <>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <Card className="mb-4 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          {(list?.crumbs || []).map((item, index) => (
            <span key={`${item.path}-${item.name}`} className="flex items-center gap-2">
              {index > 0 ? <span className="text-[var(--muted)]">/</span> : null}
              <button type="button" className="text-[var(--text)]" disabled={busy} onClick={() => void openDir(item.path)}>
                {item.name}
              </button>
            </span>
          ))}
        </div>
        <p className="mt-2 text-[12px] text-[var(--muted)]">{status.root}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            className={`${inputClass} w-48`}
            placeholder="按文件名搜索"
            value={query}
            disabled={busy}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void onSearch();
            }}
          />
          <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50" disabled={busy} onClick={() => void onSearch()}>
            搜索
          </button>
          {searching ? (
            <button
              type="button"
              className="text-[13px] text-[var(--muted)]"
              onClick={() => {
                setHits(null);
                setQuery("");
                setHint("");
              }}
            >
              取消搜索
            </button>
          ) : null}
          <input className={`${inputClass} w-36`} placeholder="新文件夹名" value={folderName} disabled={busy} onChange={(e) => setFolderName(e.target.value)} />
          <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50" disabled={busy} onClick={() => void onMkdir()}>
            新建文件夹
          </button>
          <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50" disabled={busy} onClick={() => uploadRef.current?.click()}>
            上传
          </button>
          <input ref={uploadRef} type="file" multiple className="hidden" onChange={(e) => void onUpload(e.target.files)} />
        </div>
      </Card>

      {shown.length === 0 ? (
        <p className="text-[13px] text-[var(--muted)]">{searching ? "没有找到。" : "这个文件夹是空的。可以上传或新建文件夹。"}</p>
      ) : (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
          {shown.map((item) => {
            const { Icon, color } = itemIcon(item);
            return (
              <div key={item.path} className="group rounded-md border border-transparent px-2 py-3 hover:border-[var(--line)] hover:bg-[var(--paper)]">
                <button type="button" className="flex w-full flex-col items-center text-center" onClick={() => clickItem(item)}>
                  <Icon className={`h-12 w-12 ${color}`} />
                  <div className="mt-2 w-full truncate text-[13px]" title={item.name}>
                    {item.name}
                  </div>
                  <div className="mt-1 w-full truncate text-[12px] text-[var(--muted)]">
                    {item.kind === "dir" ? "文件夹" : formatSize(item.size)}
                    {searching ? ` · ${item.path}` : ""}
                  </div>
                </button>
                <div className="mt-2 flex flex-wrap justify-center gap-2 text-[12px] text-[var(--muted)] opacity-0 group-hover:opacity-100">
                  {item.kind === "file" ? (
                    <button type="button" disabled={busy} onClick={() => void downloadFilesEntry(item.path, item.name).catch((err: Error) => setError(err.message))}>
                      下载
                    </button>
                  ) : null}
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setRenameFrom(item);
                      setRenameTo(item.name);
                    }}
                  >
                    重命名
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setMoveFrom(item);
                      setMoveTo(path);
                    }}
                  >
                    移动
                  </button>
                  <button type="button" disabled={busy} onClick={() => setAsk(item)}>
                    删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {renameFrom ? (
        <Modal title="重命名" onClose={() => setRenameFrom(null)}>
          <input className={`${inputClass} w-full`} value={renameTo} onChange={(e) => setRenameTo(e.target.value)} />
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
              disabled={busy || !renameTo.trim()}
              onClick={() => {
                setBusy(true);
                renameFilesEntry(renameFrom.path, renameTo.trim())
                  .then(() => load(path))
                  .then(() => {
                    setRenameFrom(null);
                    setHint("已改名");
                  })
                  .catch((err: Error) => setError(err.message))
                  .finally(() => setBusy(false));
              }}
            >
              保存
            </button>
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setRenameFrom(null)}>
              取消
            </button>
          </div>
        </Modal>
      ) : null}

      {moveFrom ? (
        <Modal title="移动到" onClose={() => setMoveFrom(null)}>
          <p className="mb-2 text-[13px] text-[var(--muted)]">填目标文件夹路径，根目录留空。比如 工作/2026</p>
          <input className={`${inputClass} w-full`} value={moveTo} onChange={(e) => setMoveTo(e.target.value)} placeholder="根目录留空" />
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                moveFilesEntry(moveFrom.path, moveTo.trim())
                  .then(() => load(path))
                  .then(() => {
                    setMoveFrom(null);
                    setHint("已移动");
                  })
                  .catch((err: Error) => setError(err.message))
                  .finally(() => setBusy(false));
              }}
            >
              移动
            </button>
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setMoveFrom(null)}>
              取消
            </button>
          </div>
        </Modal>
      ) : null}

      {ask ? (
        <ConfirmModal
          title={ask.kind === "dir" ? "删除文件夹" : "删除文件"}
          message={ask.kind === "dir" ? `删除「${ask.name}」？里面的东西也会删掉。` : `删除「${ask.name}」？`}
          onConfirm={() => {
            setBusy(true);
            deleteFilesEntry(ask.path)
              .then(() => load(path))
              .then(() => {
                setAsk(null);
                setHint("已删除");
              })
              .catch((err: Error) => {
                setError(err.message);
                setAsk(null);
              })
              .finally(() => setBusy(false));
          }}
          onClose={() => setAsk(null)}
        />
      ) : null}

      {preview ? (
        <Modal title={preview.name} wide onClose={() => setPreview(null)}>
          {preview.preview === "image" ? (
            <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
              <img src={`/api/v1/files/raw?path=${encodeURIComponent(preview.path)}`} alt={preview.name} className="max-h-[70vh] max-w-full object-contain" />
            </div>
          ) : null}
          {preview.preview === "pdf" ? <PdfPreview path={preview.path} /> : null}
          {preview.preview === "text" ? (
            <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-md bg-[var(--bg)] px-3 py-2 text-[13px] leading-6">{previewText || "正在读取…"}</pre>
          ) : null}
          {!preview.preview ? (
            <p className="text-[13px] leading-6 text-[var(--muted)]">
              这种文件不能在这里直接预览。可以下载，或用电脑默认程序打开。
              <br />
              {formatSize(preview.size)}
              {preview.mtime ? ` · ${preview.mtime.replace("T", " ")}` : ""}
            </p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50"
              disabled={busy}
              onClick={() =>
                openFilesEntry(preview.path)
                  .then(() => setHint("已用电脑打开"))
                  .catch((err: Error) => setError(err.message))
              }
            >
              用电脑打开
            </button>
            <button
              type="button"
              className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px]"
              onClick={() => void downloadFilesEntry(preview.path, preview.name).catch((err: Error) => setError(err.message))}
            >
              下载
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  );
}
