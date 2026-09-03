import { useEffect, useState, type FormEvent } from "react";

import { createPortalLink, deletePortalLink, fetchPortalLinks, updatePortalLink } from "@/api/client";
import type { PortalLink } from "@/api/types";
import { Modal } from "@/components/Modal";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";

const emptyForm = { title: "", url: "", remark: "", category: "" };

function categoryLabel(value: string) {
  return (value || "").trim() || "未分类";
}

function hostOf(url: string) {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return "";
  }
}

/** 网站入口：先看站点，新增编辑用弹框 */
export function PortalPage() {
  const [items, setItems] = useState<PortalLink[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");

  const showForm = adding || editingId !== null;

  async function reload() {
    const data = await fetchPortalLinks();
    setItems(data.items);
  }

  useEffect(() => {
    reload().catch((err: Error) => setNotice(err.message));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFormError("");
    try {
      if (editingId === null) {
        await createPortalLink(form);
      } else {
        await updatePortalLink(editingId, form);
      }
      setForm(emptyForm);
      setEditingId(null);
      setAdding(false);
      await reload();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (deleteId === null) return;
    setBusy(true);
    try {
      await deletePortalLink(deleteId);
      if (editingId === deleteId) {
        setEditingId(null);
        setForm(emptyForm);
        setAdding(false);
      }
      setDeleteId(null);
      await reload();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "删除失败");
      setDeleteId(null);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(item: PortalLink) {
    setFormError("");
    setAdding(false);
    setEditingId(item.id);
    setForm({ title: item.title, url: item.url, remark: item.remark, category: item.category || "" });
  }

  function startAdd() {
    setFormError("");
    setEditingId(null);
    setForm(emptyForm);
    setAdding(true);
  }

  function cancelForm() {
    setEditingId(null);
    setAdding(false);
    setForm(emptyForm);
    setFormError("");
  }

  const categories = Array.from(new Set(items.map((item) => categoryLabel(item.category)))).sort((a, b) => a.localeCompare(b, "zh"));
  const keyword = query.trim().toLowerCase();
  const shown = items.filter((item) => {
    if (category && categoryLabel(item.category) !== category) return false;
    if (!keyword) return true;
    const hay = [item.title, item.url, item.remark, item.category, hostOf(item.url)].join(" ").toLowerCase();
    return hay.includes(keyword);
  });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <input
          className={`${inputClass} max-w-xs`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索名称、网址、分类"
        />
        <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 text-[13px]" onClick={startAdd}>
          添加
        </button>
      </div>

      {items.length > 0 ? (
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            className={`border px-3 py-1.5 text-[13px] ${category === "" ? "border-[var(--text)]" : "border-[var(--line)] text-[var(--muted)]"}`}
            onClick={() => setCategory("")}
          >
            全部
          </button>
          {categories.map((name) => (
            <button
              key={name}
              type="button"
              className={`border px-3 py-1.5 text-[13px] ${category === name ? "border-[var(--text)]" : "border-[var(--line)] text-[var(--muted)]"}`}
              onClick={() => setCategory(name)}
            >
              {name}
            </button>
          ))}
        </div>
      ) : null}

      {items.length === 0 ? (
        <p className="text-[13px] leading-6 text-[var(--muted)]">还没有网站。点右上角添加。</p>
      ) : shown.length === 0 ? (
        <p className="text-[13px] leading-6 text-[var(--muted)]">没有符合的收藏。</p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((item) => {
            const host = hostOf(item.url);
            return (
              <li key={item.id}>
                <div className="group card relative px-5 py-5">
                  <a href={item.url} target="_blank" rel="noreferrer" className="block pr-16">
                    <div className="text-[15px] font-medium">{item.title}</div>
                    <div className="mt-1 text-[12px] text-[var(--muted)]">{categoryLabel(item.category)}</div>
                    <div className="mt-1.5 text-[13px] leading-6 text-[var(--muted)]">{item.remark || host || item.url}</div>
                  </a>
                  <div className="absolute right-4 top-5 flex gap-3 text-[13px] text-[var(--muted)] opacity-50 group-hover:opacity-100">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.preventDefault();
                        startEdit(item);
                      }}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.preventDefault();
                        setDeleteId(item.id);
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {showForm ? (
        <Modal title={editingId === null ? "添加网站" : "编辑网站"} onClose={cancelForm}>
          {formError ? <p className="mb-3 text-[13px] text-[var(--err)]">{formError}</p> : null}
          <form className="space-y-3" onSubmit={onSubmit}>
            <label className="block">
              <span className="mb-1 block text-[var(--muted)]">名称</span>
              <input
                className={inputClass}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                required
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[var(--muted)]">网址</span>
              <input
                className={inputClass}
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://"
                required
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[var(--muted)]">分类（可选）</span>
              <input
                className={inputClass}
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
                placeholder="比如 工作、常用"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[var(--muted)]">备注（可选）</span>
              <input
                className={inputClass}
                value={form.remark}
                onChange={(e) => setForm({ ...form, remark: e.target.value })}
              />
            </label>
            <div className="flex gap-3 pt-1">
              <button type="submit" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy}>
                {editingId === null ? "添加" : "保存"}
              </button>
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={cancelForm}>
                取消
              </button>
            </div>
          </form>
        </Modal>
      ) : null}

      {deleteId !== null ? (
        <Modal title="删除收藏" onClose={() => setDeleteId(null)}>
          <p className="text-[13px] leading-6 text-[var(--muted)]">删掉后不能恢复。确定删除？</p>
          <div className="mt-4 flex gap-3">
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void confirmDelete()}>
              删除
            </button>
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setDeleteId(null)}>
              取消
            </button>
          </div>
        </Modal>
      ) : null}

      {notice ? (
        <Modal title="提示" onClose={() => setNotice("")}>
          <p className="text-[13px] leading-6 text-[var(--muted)]">{notice}</p>
          <button type="button" className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setNotice("")}>
            知道了
          </button>
        </Modal>
      ) : null}
    </>
  );
}
