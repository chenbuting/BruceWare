import { useEffect, useState, type FormEvent } from "react";

import {
  analyzeResumeDoc,
  createResumeDoc,
  deleteResumeDoc,
  fetchInterview,
  fetchResumeDocs,
  replyInterview,
  startInterview,
  updateResumeDoc,
} from "@/api/client";
import type { InterviewMessage, ResumeDoc } from "@/api/types";
import { Card } from "@/components/Card";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";
const areaClass = `${inputClass} min-h-[180px]`;

/** 简历：保存、分析、打字模拟面试 */
export function ResumePage() {
  const [items, setItems] = useState<ResumeDoc[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [title, setTitle] = useState("我的简历");
  const [targetJob, setTargetJob] = useState("");
  const [content, setContent] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);

  async function reloadList(selectId?: number) {
    const data = await fetchResumeDocs();
    setItems(data.items);
    const nextId = selectId ?? currentId ?? data.items[0]?.id ?? null;
    setCurrentId(nextId);
    const doc = data.items.find((item) => item.id === nextId) || null;
    applyDoc(doc);
    if (doc) {
      const interview = await fetchInterview(doc.id);
      setMessages(interview.messages);
    } else {
      setMessages([]);
    }
  }

  function applyDoc(doc: ResumeDoc | null) {
    setTitle(doc?.title || "我的简历");
    setTargetJob(doc?.target_job || "");
    setContent(doc?.content || "");
    setAnalysis(doc?.analysis || "");
  }

  useEffect(() => {
    reloadList().catch((err: Error) => setError(err.message));
  }, []);

  async function onSelect(id: number) {
    setError("");
    setHint("");
    setCurrentId(id);
    const doc = items.find((item) => item.id === id) || null;
    applyDoc(doc);
    if (doc) {
      const interview = await fetchInterview(doc.id);
      setMessages(interview.messages);
    }
  }

  async function onSave(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setHint("");
    const payload = { title, target_job: targetJob, content };
    try {
      if (currentId === null) {
        const created = await createResumeDoc(payload);
        await reloadList(created.id);
      } else {
        const saved = await updateResumeDoc(currentId, payload);
        setItems((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
        setAnalysis(saved.analysis);
      }
      setHint("已保存");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function onCreate() {
    setCurrentId(null);
    applyDoc(null);
    setMessages([]);
    setHint("");
    setError("");
  }

  async function onDelete() {
    if (currentId === null || !window.confirm("删除这份简历？")) return;
    setError("");
    try {
      await deleteResumeDoc(currentId);
      setCurrentId(null);
      await reloadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  }

  async function onAnalyze() {
    if (currentId === null) {
      setError("请先保存简历");
      return;
    }
    setBusy(true);
    setError("");
    setHint("");
    try {
      await updateResumeDoc(currentId, { title, target_job: targetJob, content });
      const saved = await analyzeResumeDoc(currentId);
      setItems((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
      setAnalysis(saved.analysis);
      setHint("分析完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析失败");
    } finally {
      setBusy(false);
    }
  }

  async function onStartInterview() {
    if (currentId === null) {
      setError("请先保存简历");
      return;
    }
    setBusy(true);
    setError("");
    setHint("");
    try {
      await updateResumeDoc(currentId, { title, target_job: targetJob, content });
      const session = await startInterview(currentId);
      setMessages(session.messages);
    } catch (err) {
      setError(err instanceof Error ? err.message : "开始面试失败");
    } finally {
      setBusy(false);
    }
  }

  async function onReply(event: FormEvent) {
    event.preventDefault();
    if (currentId === null || !reply.trim()) return;
    setBusy(true);
    setError("");
    try {
      const session = await replyInterview(currentId, reply.trim());
      setMessages(session.messages);
      setReply("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)]">
        <Card title="简历列表" className="px-5 py-4">
          <button type="button" className="mb-3 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={onCreate}>
            新建
          </button>
          {items.length === 0 ? (
            <p className="text-[13px] text-[var(--muted)]">还没有简历。</p>
          ) : (
            <ul className="space-y-1 text-[13px]">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`w-full rounded-md px-2 py-1.5 text-left ${
                      item.id === currentId ? "bg-[var(--bg)]" : "hover:bg-[var(--hover)]"
                    }`}
                    onClick={() => void onSelect(item.id)}
                  >
                    {item.title}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="grid gap-4">
          <Card title={currentId === null ? "新建简历" : "编辑简历"} className="px-5 py-4">
            <form className="space-y-3" onSubmit={onSave}>
              <label className="block">
                <span className="mb-1 block text-[var(--muted)]">名称</span>
                <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <label className="block">
                <span className="mb-1 block text-[var(--muted)]">目标岗位（可选）</span>
                <input className={inputClass} value={targetJob} onChange={(e) => setTargetJob(e.target.value)} />
              </label>
              <label className="block">
                <span className="mb-1 block text-[var(--muted)]">简历正文</span>
                <textarea className={areaClass} value={content} onChange={(e) => setContent(e.target.value)} />
              </label>
              <div className="flex gap-3">
                <button type="submit" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy}>
                  保存
                </button>
                {currentId !== null ? (
                  <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => void onDelete()}>
                    删除
                  </button>
                ) : null}
              </div>
            </form>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="AI 分析" className="px-5 py-4">
              <button
                type="button"
                className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
                disabled={busy}
                onClick={() => void onAnalyze()}
              >
                开始分析
              </button>
              {analysis ? (
                <pre className="mt-3 whitespace-pre-wrap text-[13px] leading-6 text-[var(--muted)]">{analysis}</pre>
              ) : (
                <p className="mt-3 text-[13px] text-[var(--muted)]">还没有分析。先保存简历，并在设置里配好 AI。</p>
              )}
            </Card>

            <Card title="模拟面试" className="px-5 py-4">
              <button
                type="button"
                className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
                disabled={busy}
                onClick={() => void onStartInterview()}
              >
                {messages.length > 0 ? "重新开始" : "开始面试"}
              </button>
              <div className="mt-3 max-h-[320px] space-y-3 overflow-auto text-[13px] leading-6">
                {messages.length === 0 ? (
                  <p className="text-[var(--muted)]">点开始后，面试官会先提问。</p>
                ) : (
                  messages.map((item) => (
                    <div key={item.id}>
                      <div className="text-[var(--text)]">{item.role === "user" ? "我" : "面试官"}</div>
                      <div className="whitespace-pre-wrap text-[var(--muted)]">{item.content}</div>
                    </div>
                  ))
                )}
              </div>
              <form className="mt-3 flex gap-2" onSubmit={onReply}>
                <input
                  className={inputClass}
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  placeholder="输入你的回答"
                  disabled={busy || messages.length === 0}
                />
                <button
                  type="submit"
                  className="shrink-0 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
                  disabled={busy || messages.length === 0}
                >
                  发送
                </button>
              </form>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}
