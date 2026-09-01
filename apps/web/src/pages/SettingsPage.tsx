import { useEffect, useState } from "react";

import { fetchSettings, saveDatabase, saveLlm, testDatabase, testLlm } from "@/api/client";
import type { DatabaseWrite, SettingsInfo } from "@/api/types";
import { Card } from "@/components/Card";
import { PageFrame } from "@/components/PageFrame";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";

/** 设置页：可切换本地 / 远程库 */
export function SettingsPage() {
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

  return (
    <PageFrame title="设置" desc="这里改数据源和 AI。模块开关去公共里的「模块」。" wide>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <div className="grid gap-4 lg:grid-cols-2">
      {info ? (
        <Card title="当前" className="px-5 py-4">
          <dl>
            {rows.map((row, index) => (
              <div key={row.label} className={`flex gap-6 py-2.5 ${index === 0 ? "pt-0" : "border-t border-[var(--line)]"}`}>
                <dt className="w-12 shrink-0">{row.label}</dt>
                <dd className="break-all text-[var(--muted)]">{row.value}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : (
        <div />
      )}

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
      </div>

      <Card title="AI" className="mt-4 px-5 py-4">
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
    </PageFrame>
  );
}
