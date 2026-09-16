import { File, FileSpreadsheet, FileText, Folder, Image as ImageIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import {
  createDriveAccount,
  deleteDriveAccount,
  deleteDriveEntry,
  downloadDriveEntry,
  fetchDriveAccounts,
  fetchDriveKinds,
  fetchDriveList,
  fetchDriveQuota,
  makeDriveDir,
  moveDriveEntry,
  pollDriveAuth,
  renameDriveEntry,
  searchDrive,
  startDriveAuth,
  updateDriveAccount,
  uploadDriveFiles,
} from "@/api/client";
import type { DriveAccount, DriveAuthStart, DriveEntry, DriveKind, DriveList, DriveQuota, DriveUploadProgress } from "@/api/types";
import { Card } from "@/components/Card";
import { ConfirmModal, Modal } from "@/components/Modal";
import { PdfPreview } from "@/components/PdfPreview";

const inputClass = "border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5 text-[13px]";
const btnClass = "border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px] disabled:opacity-50";

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size < 1024 * 1024 * 1024 * 1024) return `${(size / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  return `${(size / (1024 * 1024 * 1024 * 1024)).toFixed(1)} TB`;
}

function driveRawUrl(accountId: string, item: DriveEntry) {
  return `/api/v1/drive/accounts/${accountId}/raw?path=${encodeURIComponent(item.path)}&fsid=${encodeURIComponent(String(item.fsid))}`;
}

function itemThumb(accountId: string, item: DriveEntry) {
  if (item.kind !== "file" || item.preview !== "image") return "";
  return item.thumb || driveRawUrl(accountId, item);
}

function itemIcon(item: DriveEntry) {
  if (item.kind === "dir") return { Icon: Folder, color: "text-amber-500" };
  if (item.preview === "image") return { Icon: ImageIcon, color: "text-sky-500" };
  if (item.preview === "text" || item.preview === "pdf") return { Icon: FileText, color: "text-slate-500" };
  const ext = item.name.split(".").pop()?.toLowerCase() || "";
  if (["xls", "xlsx", "csv"].includes(ext)) return { Icon: FileSpreadsheet, color: "text-emerald-600" };
  return { Icon: File, color: "text-[var(--muted)]" };
}

/** 网盘：先接百度，账号和文件都在这一页管。 */
export function DrivePage() {
  const [kinds, setKinds] = useState<DriveKind[]>([]);
  const [accounts, setAccounts] = useState<DriveAccount[]>([]);
  const [accountId, setAccountId] = useState("");
  const [list, setList] = useState<DriveList | null>(null);
  const [path, setPath] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DriveEntry[] | null>(null);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<DriveAccount | null>(null);
  const [form, setForm] = useState({ name: "百度网盘", app_key: "", secret_key: "", app_name: "" });
  const [auth, setAuth] = useState<DriveAuthStart | null>(null);
  const [renameFrom, setRenameFrom] = useState<DriveEntry | null>(null);
  const [renameTo, setRenameTo] = useState("");
  const [moveFrom, setMoveFrom] = useState<DriveEntry | null>(null);
  const [moveList, setMoveList] = useState<DriveList | null>(null);
  const [ask, setAsk] = useState<DriveEntry | null>(null);
  const [askAccount, setAskAccount] = useState<DriveAccount | null>(null);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [quota, setQuota] = useState<DriveQuota | null>(null);
  const [upload, setUpload] = useState<DriveUploadProgress | null>(null);
  const [preview, setPreview] = useState<DriveEntry | null>(null);
  const [previewText, setPreviewText] = useState("");
  const uploadRef = useRef<HTMLInputElement>(null);
  const location = useLocation();
  const current = accounts.find((item) => item.id === accountId) || null;

  async function loadQuota(id: string) {
    try {
      setQuota(await fetchDriveQuota(id));
    } catch {
      setQuota(null);
    }
  }

  async function reloadAccounts(prefer = accountId) {
    const data = await fetchDriveAccounts();
    setAccounts(data.items);
    const next = data.items.find((item) => item.id === prefer) || data.items[0];
    setAccountId(next?.id || "");
    return next || null;
  }

  async function loadList(id: string, nextPath = path) {
    if (!id) {
      setList(null);
      return;
    }
    const data = await fetchDriveList(id, nextPath);
    setList(data);
    setPath(data.path);
    setHits(null);
  }

  useEffect(() => {
    if (location.pathname !== "/m/drive") return;
    fetchDriveKinds()
      .then((data) => setKinds(data.items))
      .catch((err: Error) => setError(err.message));
    reloadAccounts()
      .then((row) => {
        if (!row?.ready) return;
        void loadQuota(row.id);
        return loadList(row.id, "");
      })
      .catch((err: Error) => setError(err.message));
  }, [location.pathname]);

  useEffect(() => {
    if (!auth || !accountId) return;
    let alive = true;
    const timer = window.setInterval(() => {
      pollDriveAuth(accountId)
        .then((row) => {
          if (!alive || !row.done) return;
          setAuth(null);
          setHint("授权成功。");
          void reloadAccounts(accountId).then((item) => {
            if (!item?.ready) return;
            void loadQuota(item.id);
            return loadList(item.id, "");
          });
        })
        .catch((err: Error) => {
          if (alive) setError(err.message);
        });
    }, Math.max(3, auth.interval) * 1000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [auth, accountId]);

  function run(task: () => Promise<void>, okText = "") {
    setBusy(true);
    setError("");
    setHint("");
    task()
      .then(() => {
        if (okText) setHint(okText);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  }

  function openDir(next: string) {
    if (!accountId) return;
    run(() => loadList(accountId, next));
  }

  function clickItem(item: DriveEntry) {
    if (item.kind === "dir") {
      openDir(item.path);
      return;
    }
    setPreview(item);
    setPreviewText("");
    if (item.preview === "text") {
      if (item.size > 512 * 1024) {
        setPreviewText("文件太大，请下载后查看。");
        return;
      }
      fetch(driveRawUrl(accountId, item))
        .then((res) => (res.ok ? res.text() : Promise.reject()))
        .then(setPreviewText)
        .catch(() => setPreviewText("打不开这个文本"));
    }
  }

  const shown = hits ?? list?.items ?? [];
  const searching = hits !== null;

  return (
    <>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <Card className="mb-4 px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {accounts.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`border px-3 py-1.5 text-[13px] ${accountId === item.id ? "border-[var(--text)] bg-[var(--paper)]" : "border-[var(--line)] bg-[var(--paper)] text-[var(--muted)]"}`}
                disabled={busy}
                onClick={() => {
                  setAccountId(item.id);
                  if (item.ready) {
                    void loadQuota(item.id);
                    run(() => loadList(item.id, ""));
                  } else {
                    setQuota(null);
                    setList(null);
                    setPath("");
                  }
                }}
              >
                {item.name}
                {item.authorized ? "" : "（未授权）"}
              </button>
            ))}
            <button
              type="button"
              className={btnClass}
              onClick={() => {
                setEditing(null);
                setForm({ name: "百度网盘", app_key: "", secret_key: "", app_name: "" });
                setFormOpen(true);
              }}
            >
              添加账号
            </button>
          </div>
          {current ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={btnClass}
                disabled={busy}
                onClick={() => {
                  setEditing(current);
                  setForm({ name: current.name, app_key: "", secret_key: "", app_name: current.app_name });
                  setFormOpen(true);
                }}
              >
                改资料
              </button>
              <button
                type="button"
                className={btnClass}
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    const data = await startDriveAuth(current.id);
                    setAuth(data);
                  })
                }
              >
                授权
              </button>
              <button type="button" className={btnClass} disabled={busy} onClick={() => setAskAccount(current)}>
                删除账号
              </button>
            </div>
          ) : null}
        </div>
        <p className="mt-3 text-[12px] leading-5 text-[var(--muted)]">
          先接百度网盘。个人应用一般只能进 /apps/应用名称/ 。
          {kinds.filter((item) => !item.ready).length
            ? `以后还能加：${kinds.filter((item) => !item.ready).map((item) => item.label).join("、")}。`
            : ""}
        </p>
        {current?.message ? <p className="mt-2 text-[13px] text-amber-800">{current.message}</p> : null}
        {current?.user_label ? <p className="mt-2 text-[13px] text-[var(--muted)]">已授权：{current.user_label}</p> : null}
        {quota?.total_text ? (
          <p className={`mt-2 text-[13px] ${quota.over ? "text-[var(--err)]" : "text-[var(--muted)]"}`}>
            容量：已用 {quota.used_text} / {quota.total_text}
            {quota.over ? "。空间不足，删文件或开通会员后才能上传。" : ""}
          </p>
        ) : null}

        {current?.ready ? (
          <>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 flex-wrap items-center gap-2 text-[13px]">
                {(list?.crumbs || []).map((item, index) => (
                  <span key={`${item.path}-${item.name}`} className="flex items-center gap-2">
                    {index > 0 ? <span className="text-[var(--muted)]">/</span> : null}
                    <button type="button" className="text-[var(--text)]" disabled={busy} onClick={() => openDir(item.path)}>
                      {item.name}
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <input className={`${inputClass} w-44`} placeholder="按文件名搜索" value={query} disabled={busy} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run(async () => setHits((await searchDrive(accountId, query, path)).items))} />
                <button type="button" className={btnClass} disabled={busy} onClick={() => run(async () => setHits((await searchDrive(accountId, query, path)).items))}>
                  搜索
                </button>
                {searching ? (
                  <button type="button" className="text-[13px] text-[var(--muted)]" onClick={() => { setHits(null); setQuery(""); }}>
                    取消搜索
                  </button>
                ) : null}
                <button type="button" className={`${btnClass} ${view === "grid" ? "border-[var(--text)]" : "text-[var(--muted)]"}`} onClick={() => setView("grid")}>
                  格子
                </button>
                <button type="button" className={`${btnClass} ${view === "list" ? "border-[var(--text)]" : "text-[var(--muted)]"}`} onClick={() => setView("list")}>
                  列表
                </button>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <input className={`${inputClass} w-36`} placeholder="新文件夹名" value={folderName} disabled={busy} onChange={(e) => setFolderName(e.target.value)} />
              <button
                type="button"
                className={btnClass}
                disabled={busy}
                onClick={() =>
                  run(async () => {
                    await makeDriveDir(accountId, path, folderName.trim());
                    setFolderName("");
                    await loadList(accountId, path);
                  }, "已新建文件夹")
                }
              >
                新建文件夹
              </button>
              <label className={`${btnClass} ${busy || quota?.over ? "pointer-events-none opacity-50" : ""}`}>
                {upload ? `${upload.percent}%` : busy ? "在传…" : "上传"}
                <input
                  ref={uploadRef}
                  type="file"
                  multiple
                  className="hidden"
                  disabled={busy || Boolean(quota?.over)}
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    e.target.value = "";
                    if (!files.length) return;
                    run(async () => {
                      try {
                        await uploadDriveFiles(accountId, path, files, setUpload);
                        await loadList(accountId, path);
                        await loadQuota(accountId);
                      } finally {
                        setUpload(null);
                      }
                    }, "已上传");
                  }}
                />
              </label>
            </div>
            {upload ? (
              <div className="mt-3">
                <p className="text-[12px] text-[var(--muted)]">
                  正在上传 {upload.index + 1}/{upload.total}：{upload.name}
                  {upload.stage === "save" ? "（正在写入网盘）" : ""}
                </p>
                <div className="mt-1 h-1.5 overflow-hidden rounded-sm bg-[var(--line)]">
                  <div className="h-full bg-[var(--text)]" style={{ width: `${Math.max(2, upload.percent)}%` }} />
                </div>
              </div>
            ) : null}
            {list?.root ? <p className="mt-2 text-[12px] text-[var(--muted)]">应用目录：{list.root}</p> : null}
          </>
        ) : null}
      </Card>

      {!accounts.length ? (
        <p className="text-[13px] text-[var(--muted)]">还没有账号。点「添加账号」，填开放平台的 AppKey 和 SecretKey。</p>
      ) : current?.ready && shown.length === 0 ? (
        <p className="text-[13px] text-[var(--muted)]">{searching ? "没有找到。" : "这个文件夹是空的。可以上传或新建文件夹。"}</p>
      ) : current?.ready && view === "list" ? (
        <div className="divide-y divide-[var(--line)] border border-[var(--line)]">
          {shown.map((item) => {
            const { Icon, color } = itemIcon(item);
            return (
              <div key={`${item.path}-${item.fsid}`} className="flex flex-wrap items-center gap-3 px-3 py-2 hover:bg-[var(--paper)]">
                <button type="button" className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => clickItem(item)}>
                  {itemThumb(accountId, item) ? (
                    <img src={itemThumb(accountId, item)} alt="" referrerPolicy="no-referrer" className="h-10 w-10 shrink-0 rounded-sm object-cover" />
                  ) : (
                    <Icon className={`h-5 w-5 shrink-0 ${color}`} />
                  )}
                  <span className="min-w-0 flex-1 break-all text-[13px]">{item.name}</span>
                  <span className="shrink-0 text-[12px] text-[var(--muted)]">{item.kind === "dir" ? "文件夹" : formatSize(item.size)}</span>
                </button>
                  <ItemActions item={item} busy={busy} onDownload={() => run(() => downloadDriveEntry(accountId, item.path, item.name, item.fsid))} onRename={() => { setRenameFrom(item); setRenameTo(item.name); }} onMove={() => { setMoveFrom(item); run(async () => setMoveList(await fetchDriveList(accountId, path))); }} onDelete={() => setAsk(item)} />
              </div>
            );
          })}
        </div>
      ) : current?.ready ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
          {shown.map((item) => {
            const { Icon, color } = itemIcon(item);
            return (
              <div key={`${item.path}-${item.fsid}`} className="rounded-md border border-[var(--line)] bg-[var(--paper)] px-3 py-3">
                <button type="button" className="flex w-full flex-col items-center text-center" onClick={() => clickItem(item)}>
                  {itemThumb(accountId, item) ? (
                    <img src={itemThumb(accountId, item)} alt={item.name} referrerPolicy="no-referrer" className="h-24 w-full rounded-sm object-contain" />
                  ) : (
                    <Icon className={`h-10 w-10 ${color}`} />
                  )}
                  <div className="mt-2 line-clamp-2 w-full break-all text-[13px] leading-5">{item.name}</div>
                  <div className="mt-1 text-[12px] text-[var(--muted)]">{item.kind === "dir" ? "文件夹" : formatSize(item.size)}</div>
                </button>
                <div className="mt-2 flex justify-center">
                  <ItemActions item={item} busy={busy} onDownload={() => run(() => downloadDriveEntry(accountId, item.path, item.name, item.fsid))} onRename={() => { setRenameFrom(item); setRenameTo(item.name); }} onMove={() => { setMoveFrom(item); run(async () => setMoveList(await fetchDriveList(accountId, path))); }} onDelete={() => setAsk(item)} />
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {preview ? (
        <Modal title={preview.name} wide onClose={() => setPreview(null)}>
          {preview.preview === "image" ? (
            <div className="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-md bg-[var(--bg)]">
              <img src={driveRawUrl(accountId, preview)} alt={preview.name} className="max-h-[70vh] max-w-full object-contain" />
            </div>
          ) : null}
          {preview.preview === "pdf" ? <PdfPreview url={driveRawUrl(accountId, preview)} /> : null}
          {preview.preview === "text" ? (
            <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-md bg-[var(--bg)] px-3 py-2 text-[13px] leading-6">{previewText || "正在读取…"}</pre>
          ) : null}
          {!preview.preview ? (
            <p className="text-[13px] leading-6 text-[var(--muted)]">
              这种文件不能在这里直接预览，请下载查看。
              <br />
              {formatSize(preview.size)}
              {preview.mtime ? ` · ${preview.mtime.replace("T", " ")}` : ""}
            </p>
          ) : null}
          <div className="mt-3">
            <button
              type="button"
              className={btnClass}
              disabled={busy}
              onClick={() => run(() => downloadDriveEntry(accountId, preview.path, preview.name, preview.fsid), "已开始下载")}
            >
              下载
            </button>
          </div>
        </Modal>
      ) : null}

      {formOpen ? (
      <Modal title={editing ? "改账号" : "添加百度网盘"} onClose={() => setFormOpen(false)}>
        <div className="space-y-2 text-[13px]">
          <input className={`${inputClass} w-full`} placeholder="显示名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className={`${inputClass} w-full`} placeholder="AppKey" value={form.app_key} onChange={(e) => setForm({ ...form, app_key: e.target.value })} />
          <input className={`${inputClass} w-full`} placeholder={editing ? "SecretKey，不改就留空" : "SecretKey"} value={form.secret_key} onChange={(e) => setForm({ ...form, secret_key: e.target.value })} />
          <input className={`${inputClass} w-full`} placeholder="开放平台上的应用名称" value={form.app_name} onChange={(e) => setForm({ ...form, app_name: e.target.value })} />
          <p className="text-[12px] text-[var(--muted)]">应用名称要和百度开放平台上的一致，个人应用才能进 /apps/这个名字/。</p>
          <button
            type="button"
            className={btnClass}
            disabled={busy}
            onClick={() =>
              run(async () => {
                if (editing) {
                  await updateDriveAccount(editing.id, form);
                  await reloadAccounts(editing.id);
                } else {
                  const row = await createDriveAccount({ kind: "baidu", ...form });
                  await reloadAccounts(row.id);
                }
                setFormOpen(false);
              }, "已保存")
            }
          >
            保存
          </button>
        </div>
      </Modal>
      ) : null}

      {auth ? (
      <Modal title="去百度授权" onClose={() => setAuth(null)}>
        {auth ? (
          <div className="space-y-2 text-[13px]">
            <p>在百度页输入这个码，或点链接登录授权。</p>
            <p className="text-[20px] tracking-widest">{auth.user_code}</p>
            <a className="text-[var(--text)] underline" href={auth.verify_url} target="_blank" rel="noreferrer">
              打开授权页
            </a>
            <span className="mx-2 text-[var(--muted)]">或</span>
            <a className="text-[var(--text)] underline" href={auth.auth_url} target="_blank" rel="noreferrer">
              用网页登录授权
            </a>
            {auth.qrcode_url ? <img src={auth.qrcode_url} alt="授权二维码" className="mt-2 h-40 w-40" /> : null}
            <p className="text-[12px] text-[var(--muted)]">授完权后会自动连上，不用关这个框。</p>
          </div>
        ) : null}
      </Modal>
      ) : null}

      {renameFrom ? (
      <Modal title="重命名" onClose={() => setRenameFrom(null)}>
        <input className={`${inputClass} mb-3 w-full`} value={renameTo} onChange={(e) => setRenameTo(e.target.value)} />
        <button
          type="button"
          className={btnClass}
          onClick={() => {
            if (!renameFrom) return;
            run(async () => {
              await renameDriveEntry(accountId, renameFrom.path, renameTo.trim());
              setRenameFrom(null);
              await loadList(accountId, path);
            }, "已改名");
          }}
        >
          保存
        </button>
      </Modal>
      ) : null}

      {moveFrom ? (
      <Modal title={`移动「${moveFrom.name}」`} onClose={() => { setMoveFrom(null); setMoveList(null); }}>
        <p className="mb-2 text-[12px] text-[var(--muted)]">点文件夹进去，然后点「移到这里」。</p>
        <div className="mb-3 flex min-w-0 flex-wrap items-center gap-2 text-[13px]">
          {(moveList?.crumbs || []).map((item, index) => (
            <span key={`${item.path}-${item.name}`} className="flex items-center gap-2">
              {index > 0 ? <span className="text-[var(--muted)]">/</span> : null}
              <button type="button" className="text-[var(--text)]" disabled={busy} onClick={() => run(async () => setMoveList(await fetchDriveList(accountId, item.path)))}>
                {item.name}
              </button>
            </span>
          ))}
        </div>
        <div className="mb-3 max-h-56 overflow-auto border border-[var(--line)]">
          {!moveList ? (
            <p className="px-3 py-2 text-[13px] text-[var(--muted)]">正在读取…</p>
          ) : (moveList.items || []).filter((item) => item.kind === "dir" && item.path !== moveFrom.path).length ? (
            moveList.items
              .filter((item) => item.kind === "dir" && item.path !== moveFrom.path)
              .map((item) => (
                <button
                  key={item.path}
                  type="button"
                  className="flex w-full items-center gap-2 border-b border-[var(--line)] px-3 py-2 text-left last:border-b-0 hover:bg-[var(--paper)]"
                  disabled={busy}
                  onClick={() => run(async () => setMoveList(await fetchDriveList(accountId, item.path)))}
                >
                  <Folder className="h-4 w-4 shrink-0 text-amber-500" />
                  <span className="break-all text-[13px]">{item.name}</span>
                </button>
              ))
          ) : (
            <p className="px-3 py-2 text-[13px] text-[var(--muted)]">这里没有子文件夹。</p>
          )}
        </div>
        <button
          type="button"
          className={btnClass}
          disabled={busy || !moveList || (moveFrom.kind === "dir" && (moveList.path === moveFrom.path || moveList.path.startsWith(`${moveFrom.path}/`)))}
          onClick={() => {
            if (!moveFrom || !moveList) return;
            run(async () => {
              await moveDriveEntry(accountId, moveFrom.path, moveList.path);
              setMoveFrom(null);
              setMoveList(null);
              await loadList(accountId, path);
            }, "已移动");
          }}
        >
          移到这里
        </button>
      </Modal>
      ) : null}

      {ask ? (
      <ConfirmModal
        title="删除这个文件？"
        message={`确定删除「${ask.name}」？网盘里也会删掉。`}
        onClose={() => setAsk(null)}
        onConfirm={() => {
          if (!ask) return;
          run(async () => {
            await deleteDriveEntry(accountId, ask.path);
            setAsk(null);
            await loadList(accountId, path);
          }, "已删除");
        }}
      />
      ) : null}
      {askAccount ? (
      <ConfirmModal
        title="删除这个账号？"
        message="只是从本机去掉账号，不会删网盘里的文件。"
        onClose={() => setAskAccount(null)}
        onConfirm={() => {
          if (!askAccount) return;
          run(async () => {
            await deleteDriveAccount(askAccount.id);
            setAskAccount(null);
            setList(null);
            const next = await reloadAccounts("");
            if (next?.ready) await loadList(next.id, "");
          }, "已删除账号");
        }}
      />
      ) : null}
    </>
  );
}

function ItemActions({
  item,
  busy,
  onDownload,
  onRename,
  onMove,
  onDelete,
}: {
  item: DriveEntry;
  busy: boolean;
  onDownload: () => void;
  onRename: () => void;
  onMove: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1 text-[12px] text-[var(--muted)]">
      {item.kind === "file" ? (
        <button type="button" disabled={busy} onClick={onDownload}>
          下载
        </button>
      ) : null}
      <button type="button" disabled={busy} onClick={onRename}>
        重命名
      </button>
      <button type="button" disabled={busy} onClick={onMove}>
        移动
      </button>
      <button type="button" disabled={busy} onClick={onDelete}>
        删除
      </button>
    </div>
  );
}
