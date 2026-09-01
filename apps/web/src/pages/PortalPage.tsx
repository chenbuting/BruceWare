import { useEffect, useState, type FormEvent } from "react";

import { createPortalLink, deletePortalLink, fetchPortalLinks, updatePortalLink } from "@/api/client";
import type { PortalLink } from "@/api/types";
import { Card } from "@/components/Card";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";

const emptyForm = { title: "", url: "", remark: "" };

/** 网站入口：收藏常用网站 */
export function PortalPage() {
  const [items, setItems] = useState<PortalLink[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function reload() {
    const data = await fetchPortalLinks();
    setItems(data.items);
  }

  useEffect(() => {
    reload().catch((err: Error) => setError(err.message));
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (editingId === null) {
        await createPortalLink(form);
      } else {
        await updatePortalLink(editingId, form);
      }
      setForm(emptyForm);
      setEditingId(null);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: number) {
    if (!window.confirm("删除这条收藏？")) return;
    setError("");
    try {
      await deletePortalLink(id);
      if (editingId === id) {
        setEditingId(null);
        setForm(emptyForm);
      }
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  function startEdit(item: PortalLink) {
    setEditingId(item.id);
    setForm({ title: item.title, url: item.url, remark: item.remark });
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(emptyForm);
  }

  return (
    <>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(240px,320px)_minmax(0,1fr)]">
        <Card title={editingId === null ? "添加" : "编辑"} className="px-5 py-4">
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
              <span className="mb-1 block text-[var(--muted)]">备注</span>
              <input
                className={inputClass}
                value={form.remark}
                onChange={(e) => setForm({ ...form, remark: e.target.value })}
              />
            </label>
            <div className="flex gap-3">
              <button type="submit" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy}>
                {editingId === null ? "添加" : "保存修改"}
              </button>
              {editingId !== null ? (
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={cancelEdit}>
                  取消
                </button>
              ) : null}
            </div>
          </form>
        </Card>

        {items.length === 0 ? (
          <Card className="px-5 py-4">
            <p className="text-[13px] leading-6 text-[var(--muted)]">还没有收藏。</p>
          </Card>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {items.map((item) => (
              <li key={item.id}>
                <Card className="px-5 py-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-3">
                    <a href={item.url} target="_blank" rel="noreferrer" className="underline">
                      {item.title}
                    </a>
                    <div className="flex gap-3 text-[13px] text-[var(--muted)]">
                      <button type="button" onClick={() => startEdit(item)}>
                        编辑
                      </button>
                      <button type="button" onClick={() => onDelete(item.id)}>
                        删除
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 break-all text-[13px] text-[var(--muted)]">{item.url}</div>
                  {item.remark ? <div className="mt-1 text-[13px] text-[var(--muted)]">{item.remark}</div> : null}
                </Card>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
