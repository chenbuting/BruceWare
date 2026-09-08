import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  createDataRow,
  deleteDataRow,
  fetchDataRow,
  fetchDataRows,
  fetchDataTables,
  updateDataRow,
} from "@/api/client";
import type { DataColumn, DataRow, DataTableInfo } from "@/api/types";
import { ConfirmModal, Modal } from "@/components/Modal";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";
const areaClass = `${inputClass} min-h-[96px]`;

function rowId(row: DataRow, columns: DataColumn[]) {
  const pk = columns.find((col) => col.primary) || columns.find((col) => col.name === "id");
  return pk ? String(row[pk.name] ?? "") : "";
}

function cellText(value: DataRow[string]) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function emptyForm(columns: DataColumn[]): DataRow {
  const next: DataRow = {};
  for (const col of columns) next[col.name] = "";
  return next;
}

/** 数据：左边选表，右边看行。表从库里自动扫。 */
export function DataPage() {
  const [tables, setTables] = useState<DataTableInfo[]>([]);
  const [tableName, setTableName] = useState("");
  const [rows, setRows] = useState<DataRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<DataRow | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formError, setFormError] = useState("");
  const [deleteId, setDeleteId] = useState<string | null>(null);

  const current = tables.find((item) => item.name === tableName) || null;
  const pageCount = Math.max(1, Math.ceil(total / 30));

  const previewCols = useMemo(() => {
    if (!current) return [];
    const prefer = current.columns.filter((col) => !col.readonly || col.primary).slice(0, 5);
    return prefer.length ? prefer : current.columns.slice(0, 5);
  }, [current]);

  async function reloadTables() {
    const data = await fetchDataTables();
    setTables(data.items);
    setTableName((prev) => prev || data.items[0]?.name || "");
  }

  async function reloadRows(name: string, nextPage: number, q: string) {
    if (!name) {
      setRows([]);
      setTotal(0);
      return;
    }
    const data = await fetchDataRows(name, nextPage, q);
    setRows(data.items);
    setTotal(data.total);
    setPage(data.page);
  }

  useEffect(() => {
    reloadTables().catch((err: Error) => setNotice(err.message));
  }, []);

  useEffect(() => {
    if (!tableName) return;
    reloadRows(tableName, 1, "").catch((err: Error) => setNotice(err.message));
  }, [tableName]);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setNotice("");
    try {
      await reloadRows(tableName, 1, query);
    } catch (err) {
      setNotice((err as Error).message);
    }
  }

  async function openCreate() {
    if (!current) return;
    setFormError("");
    setEditingId(null);
    setForm(emptyForm(current.columns));
  }

  async function openEdit(id: string) {
    if (!current) return;
    setFormError("");
    setBusy(true);
    try {
      const row = await fetchDataRow(current.name, id);
      setEditingId(id);
      setForm(row);
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!current || !form) return;
    setBusy(true);
    setFormError("");
    try {
      if (editingId) await updateDataRow(current.name, editingId, form);
      else await createDataRow(current.name, form);
      setForm(null);
      setEditingId(null);
      await reloadRows(current.name, page, query);
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onDelete() {
    if (!current || !deleteId) return;
    setBusy(true);
    try {
      await deleteDataRow(current.name, deleteId);
      setDeleteId(null);
      await reloadRows(current.name, page, query);
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 gap-6">
      <aside className="w-52 shrink-0 overflow-auto">
        <div className="mb-3 text-[13px] text-[var(--muted)]">数据库里的表</div>
        {tables.length === 0 ? (
          <p className="text-[13px] text-[var(--muted)]">还没有表。</p>
        ) : (
          <ul className="space-y-1">
            {tables.map((item) => (
              <li key={item.name}>
                <button
                  type="button"
                  className={`w-full px-2 py-1.5 text-left text-[13px] ${
                    item.name === tableName ? "bg-[var(--paper)]" : "text-[var(--muted)] hover:text-[var(--text)]"
                  }`}
                  onClick={() => {
                    setQuery("");
                    setTableName(item.name);
                  }}
                >
                  <div>{item.label}</div>
                  <div className="text-[12px] text-[var(--muted)]">{item.name}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </aside>

      <section className="min-w-0 flex-1 overflow-auto">
        {notice ? <p className="mb-3 text-[13px] text-[var(--err)]">{notice}</p> : null}
        {!current ? (
          <p className="text-[13px] text-[var(--muted)]">先选左边一张表。</p>
        ) : (
          <>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-[15px] font-medium">{current.label}</div>
                <div className="mt-1 text-[13px] text-[var(--muted)]">共 {total} 条。删除只去记录，磁盘文件还在。</div>
              </div>
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => void openCreate()}>
                添加
              </button>
            </div>

            <form className="mb-4 flex gap-2" onSubmit={onSearch}>
              <input
                className={inputClass}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索"
              />
              <button type="submit" className="shrink-0 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5">
                查找
              </button>
            </form>

            {rows.length === 0 ? (
              <p className="text-[13px] text-[var(--muted)]">这张表还没有行。</p>
            ) : (
              <div className="overflow-auto">
                <table className="w-full min-w-[40rem] border-collapse text-left text-[13px]">
                  <thead>
                    <tr className="text-[var(--muted)]">
                      {previewCols.map((col) => (
                        <th key={col.name} className="border-b border-[var(--line)] px-2 py-2 font-normal">
                          {col.name}
                        </th>
                      ))}
                      <th className="border-b border-[var(--line)] px-2 py-2 font-normal">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const id = rowId(row, current.columns);
                      return (
                        <tr key={id || JSON.stringify(row)}>
                          {previewCols.map((col) => (
                            <td key={col.name} className="border-b border-[var(--line)] px-2 py-2 align-top">
                              {cellText(row[col.name]) || "—"}
                            </td>
                          ))}
                          <td className="border-b border-[var(--line)] px-2 py-2 whitespace-nowrap text-[var(--muted)]">
                            <button type="button" className="mr-3" onClick={() => void openEdit(id)}>
                              编辑
                            </button>
                            <button type="button" onClick={() => setDeleteId(id)}>
                              删除
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {pageCount > 1 ? (
              <div className="mt-4 flex gap-3 text-[13px] text-[var(--muted)]">
                <button type="button" disabled={page <= 1} onClick={() => void reloadRows(tableName, page - 1, query)}>
                  上一页
                </button>
                <span>
                  {page} / {pageCount}
                </span>
                <button
                  type="button"
                  disabled={page >= pageCount}
                  onClick={() => void reloadRows(tableName, page + 1, query)}
                >
                  下一页
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>

      {form && current ? (
        <Modal title={editingId ? "编辑记录" : "添加记录"} wide onClose={() => setForm(null)}>
          {formError ? <p className="mb-3 text-[13px] text-[var(--err)]">{formError}</p> : null}
          <form className="space-y-3" onSubmit={onSubmit}>
            {current.columns.map((col) => {
              const locked = col.readonly;
              const long = col.type === "text" && cellText(form[col.name]).length > 40;
              return (
                <label key={col.name} className="block">
                  <span className="mb-1 block text-[var(--muted)]">
                    {col.name}
                    {locked ? "（只能看）" : ""}
                  </span>
                  {long ? (
                    <textarea
                      className={areaClass}
                      value={cellText(form[col.name])}
                      disabled={locked}
                      onChange={(e) => setForm({ ...form, [col.name]: e.target.value })}
                    />
                  ) : (
                    <input
                      className={inputClass}
                      value={cellText(form[col.name])}
                      disabled={locked}
                      onChange={(e) => setForm({ ...form, [col.name]: e.target.value })}
                    />
                  )}
                </label>
              );
            })}
            <div className="flex gap-3 pt-1">
              <button type="submit" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" disabled={busy}>
                保存
              </button>
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setForm(null)}>
                取消
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {deleteId ? (
        <ConfirmModal
          title="删除这条记录"
          message="只删除数据库里的这一行，磁盘上的文件还在。确定删除？"
          busy={busy}
          onConfirm={() => void onDelete()}
          onClose={() => setDeleteId(null)}
        />
      ) : null}
    </div>
  );
}
