import { useEffect, useState } from "react";

import { fetchSettings, saveDatabase, saveLlm, testDatabase, testLlm } from "@/api/client";
import type { DatabaseWrite, SettingsInfo } from "@/api/types";
import { Card } from "@/components/Card";
import { PageFrame } from "@/components/PageFrame";
import {
  loadLayout,
  newCategory,
  saveLayout,
  SETTING_ITEMS,
  type SettingItemId,
  type SettingsLayout,
} from "@/pages/settingsSections";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";

/** 设置页：左边是分类文件夹，设置内容可以自己归类 */
export function SettingsPage() {
  const [layout, setLayout] = useState<SettingsLayout>(() => loadLayout());
  const [categoryId, setCategoryId] = useState(() => loadLayout().categories[0]?.id || "");
  const [managing, setManaging] = useState(false);
  const [info, setInfo] = useState<SettingsInfo | null>(null);
  const [mode, setMode] = useState<DatabaseWrite["mode"]>("local");
  const [sqlitePath, setSqlitePath] = useState("./data/bruceware.db");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("3306");
  const [name, setName] = useState("bruceware");
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [hasPassword, setHasPassword] = useState(false);
  const [llmBase, setLlmBase] = useState("https://api.openai.com/v1");
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [llmKey, setLlmKey] = useState("");
  const [hasLlmKey, setHasLlmKey] = useState(false);
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchSettings()
      .then((data) => {
        setInfo(data);
        applyForm(data);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  function applyForm(data: SettingsInfo) {
    const form = data.database.form;
    setMode(form.mode);
    setSqlitePath(form.sqlite_path);
    setHost(form.host);
    setPort(String(form.port || (form.mode === "postgres" ? 5432 : 3306)));
    setName(form.name);
    setUser(form.user);
    setHasPassword(form.has_password);
    setPassword("");
    if (data.llm) {
      setLlmBase(data.llm.base_url || "https://api.openai.com/v1");
      setLlmModel(data.llm.model || "gpt-4o-mini");
      setHasLlmKey(data.llm.has_key);
      setLlmKey("");
    }
  }

  function payload(): DatabaseWrite {
    return {
      mode,
      sqlite_path: sqlitePath,
      host,
      port: port ? Number(port) : null,
      name,
      user,
      password,
    };
  }

  async function onTest() {
    setBusy(true);
    setError("");
    setHint("");
    try {
      await testDatabase(payload());
      setHint("能连上");
    } catch (err) {
      setError(err instanceof Error ? err.message : "测试失败");
    } finally {
      setBusy(false);
    }
  }

  async function onSave() {
    setBusy(true);
    setError("");
    setHint("");
    try {
      const data = await saveDatabase(payload());
      setInfo(data);
      applyForm(data);
      setHint("已保存并切换");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  const rows = info
    ? [
        { label: "应用", value: info.app_name },
        { label: "后端", value: `${info.api_host}:${info.api_port}` },
        { label: "当前", value: `${info.database.label} · ${info.database.connected ? "正常" : "失败"}` },
        { label: "位置", value: info.database.target },
      ]
    : [];

  function persist(next: SettingsLayout) {
    setLayout(next);
    saveLayout(next);
  }

  function renameCategory(id: string, label: string, trim = false) {
    persist({
      ...layout,
      categories: layout.categories.map((item) => {
        if (item.id !== id) return item;
        const next = trim ? label.trim() : label;
        return { ...item, label: next || item.label };
      }),
    });
  }

  function moveCategory(id: string, offset: number) {
    const from = layout.categories.findIndex((item) => item.id === id);
    const to = from + offset;
    if (from < 0 || to < 0 || to >= layout.categories.length) return;
    const categories = [...layout.categories];
    const [item] = categories.splice(from, 1);
    categories.splice(to, 0, item);
    persist({ ...layout, categories });
  }

  function addCategory() {
    const created = newCategory();
    persist({ ...layout, categories: [...layout.categories, created] });
    setCategoryId(created.id);
  }

  function removeCategory(id: string) {
    if (layout.categories.length <= 1) return;
    const fallback = layout.categories.find((item) => item.id !== id)?.id;
    if (!fallback) return;
    persist({
      categories: layout.categories.filter((item) => item.id !== id),
      items: layout.items.map((item) => (item.categoryId === id ? { ...item, categoryId: fallback } : item)),
    });
    if (categoryId === id) setCategoryId(fallback);
  }

  function moveItem(id: SettingItemId, nextCategoryId: string) {
    persist({
      ...layout,
      items: layout.items.map((item) => (item.id === id ? { ...item, categoryId: nextCategoryId } : item)),
    });
  }

  const currentId = layout.categories.some((item) => item.id === categoryId)
    ? categoryId
    : layout.categories[0]?.id || "";
  const visibleIds = layout.items.filter((item) => item.categoryId === currentId).map((item) => item.id);

  return (
    <PageFrame hideHeader wide>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <div className="flex flex-col gap-4 md:flex-row md:items-start">
        <nav className="flex shrink-0 flex-col gap-1 md:w-44">
          {layout.categories.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`rounded-md px-3 py-2 text-left text-[13px] ${
                currentId === item.id ? "bg-[var(--paper)] font-medium" : "text-[var(--muted)] hover:bg-[var(--hover)]"
              }`}
              onClick={() => {
                setCategoryId(item.id);
                setError("");
                setHint("");
              }}
            >
              {item.label || "未命名"}
            </button>
          ))}
          <button
            type="button"
            className="mt-2 px-3 py-2 text-left text-[13px] text-[var(--muted)] hover:text-[var(--text)]"
            onClick={() => setManaging((prev) => !prev)}
          >
            {managing ? "完成" : "编辑归类"}
          </button>
        </nav>

        <div className="min-w-0 flex-1 space-y-4">
          {managing ? (
            <Card title="编辑归类" className="px-5 py-4">
              <div className="text-[13px] font-medium">分类</div>
              <div className="mt-2 divide-y divide-[var(--line)]">
                {layout.categories.map((item, index) => (
                  <div key={item.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
                    <input
                      className={`${inputClass} sm:flex-1`}
                      value={item.label}
                      onChange={(e) => renameCategory(item.id, e.target.value)}
                      onBlur={(e) => renameCategory(item.id, e.target.value, true)}
                    />
                    <div className="flex shrink-0 gap-3 text-[13px]">
                      <button
                        type="button"
                        className="text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40"
                        disabled={index === 0}
                        onClick={() => moveCategory(item.id, -1)}
                      >
                        上移
                      </button>
                      <button
                        type="button"
                        className="text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40"
                        disabled={index === layout.categories.length - 1}
                        onClick={() => moveCategory(item.id, 1)}
                      >
                        下移
                      </button>
                      <button
                        type="button"
                        className="text-[var(--err)] disabled:opacity-40"
                        disabled={layout.categories.length <= 1}
                        onClick={() => removeCategory(item.id)}
                      >
                        删除
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <button type="button" className="mt-1 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={addCategory}>
                新增分类
              </button>

              <div className="mt-6 border-t border-[var(--line)] pt-4 text-[13px] font-medium">设置项放到哪</div>
              <p className="mt-1 text-[13px] leading-6 text-[var(--muted)]">选好分类后点左边「完成」，再点分类就能看到。</p>
              <div className="mt-2 divide-y divide-[var(--line)]">
                {SETTING_ITEMS.map((item) => {
                  const place = layout.items.find((row) => row.id === item.id);
                  return (
                    <div key={item.id} className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-center gap-4 py-3 first:pt-0 last:pb-0">
                      <span className="text-[13px]">{item.label}</span>
                      <select
                        className={inputClass}
                        value={place?.categoryId || currentId}
                        onChange={(e) => moveItem(item.id, e.target.value)}
                      >
                        {layout.categories.map((cat) => (
                          <option key={cat.id} value={cat.id}>
                            {cat.label || "未命名"}
                          </option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : null}

          {!managing && visibleIds.includes("overview") ? (
            <Card title="当前" className="px-5 py-4">
              {info ? (
                <dl>
                  {rows.map((row, index) => (
                    <div key={row.label} className={`flex gap-6 py-2.5 ${index === 0 ? "pt-0" : "border-t border-[var(--line)]"}`}>
                      <dt className="w-12 shrink-0">{row.label}</dt>
                      <dd className="break-all text-[var(--muted)]">{row.value}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-[13px] text-[var(--muted)]">正在读取…</p>
              )}
            </Card>
          ) : null}

          {!managing && visibleIds.includes("database") ? (
            <Card title="数据源" className="px-5 py-4">
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-1.5">
                  <input type="radio" name="mode" checked={mode === "local"} onChange={() => setMode("local")} />
                  本地 SQLite
                </label>
                <label className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="mode"
                    checked={mode === "mysql"}
                    onChange={() => {
                      setMode("mysql");
                      if (!port || port === "5432") setPort("3306");
                    }}
                  />
                  远程 MySQL
                </label>
                <label className="flex items-center gap-1.5">
                  <input
                    type="radio"
                    name="mode"
                    checked={mode === "postgres"}
                    onChange={() => {
                      setMode("postgres");
                      if (!port || port === "3306") setPort("5432");
                    }}
                  />
                  远程 PostgreSQL
                </label>
              </div>

              {mode === "local" ? (
                <label className="mt-4 block">
                  <span className="mb-1 block text-[var(--muted)]">库文件路径</span>
                  <input className={inputClass} value={sqlitePath} onChange={(e) => setSqlitePath(e.target.value)} />
                </label>
              ) : (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <label>
                    <span className="mb-1 block text-[var(--muted)]">主机</span>
                    <input className={inputClass} value={host} onChange={(e) => setHost(e.target.value)} />
                  </label>
                  <label>
                    <span className="mb-1 block text-[var(--muted)]">端口</span>
                    <input className={inputClass} value={port} onChange={(e) => setPort(e.target.value)} />
                  </label>
                  <label>
                    <span className="mb-1 block text-[var(--muted)]">库名</span>
                    <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
                  </label>
                  <label>
                    <span className="mb-1 block text-[var(--muted)]">用户名</span>
                    <input className={inputClass} value={user} onChange={(e) => setUser(e.target.value)} />
                  </label>
                  <label className="sm:col-span-2">
                    <span className="mb-1 block text-[var(--muted)]">密码{hasPassword ? "（已保存，不改请留空）" : ""}</span>
                    <input
                      className={inputClass}
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </label>
                </div>
              )}

              <div className="mt-5 flex gap-3">
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={onTest}>
                  测试连接
                </button>
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={onSave}>
                  保存并切换
                </button>
              </div>
            </Card>
          ) : null}

          {!managing && visibleIds.includes("ai") ? (
            <Card title="AI" className="px-5 py-4">
              <p className="text-[13px] leading-6 text-[var(--muted)]">
                兼容 OpenAI 的接口。简历分析和模拟面试会用这里。Key 不回显，不改请留空。
              </p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="sm:col-span-2">
                  <span className="mb-1 block text-[var(--muted)]">接口地址</span>
                  <input className={inputClass} value={llmBase} onChange={(e) => setLlmBase(e.target.value)} />
                </label>
                <label>
                  <span className="mb-1 block text-[var(--muted)]">模型</span>
                  <input className={inputClass} value={llmModel} onChange={(e) => setLlmModel(e.target.value)} />
                </label>
                <label>
                  <span className="mb-1 block text-[var(--muted)]">Key{hasLlmKey ? "（已保存，不改请留空）" : ""}</span>
                  <input className={inputClass} type="password" value={llmKey} onChange={(e) => setLlmKey(e.target.value)} />
                </label>
              </div>
              <div className="mt-5 flex gap-3">
                <button
                  type="button"
                  className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    setError("");
                    setHint("");
                    saveLlm({ base_url: llmBase, model: llmModel, api_key: llmKey })
                      .then((data) => {
                        setInfo(data);
                        applyForm(data);
                        setHint("AI 已保存");
                      })
                      .catch((err: Error) => setError(err.message))
                      .finally(() => setBusy(false));
                  }}
                >
                  保存 AI
                </button>
                <button
                  type="button"
                  className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    setError("");
                    setHint("");
                    testLlm()
                      .then((data) => setHint(`测试通过：${data.reply}`))
                      .catch((err: Error) => setError(err.message))
                      .finally(() => setBusy(false));
                  }}
                >
                  测试 AI
                </button>
              </div>
            </Card>
          ) : null}

          {!managing && visibleIds.length === 0 ? (
            <Card className="px-5 py-4">
              <p className="text-[13px] leading-6 text-[var(--muted)]">这个分类还没有设置。点「编辑归类」，把内容移过来。</p>
            </Card>
          ) : null}
        </div>
      </div>
    </PageFrame>
  );
}
