import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  analyzeResumeDoc,
  createResumeDoc,
  deleteResumeDoc,
  downloadResumeDoc,
  fetchInterview,
  fetchResumeDocs,
  importResumeDoc,
  replyInterview,
  startInterview,
  updateResumeDoc,
} from "@/api/client";
import type { InterviewMessage, ResumeDoc } from "@/api/types";
import { Card } from "@/components/Card";
import { ConfirmModal } from "@/components/Modal";
import {
  emptyJob,
  emptyProject,
  emptyResume,
  emptySkill,
  flattenResume,
  linesToList,
  listToLines,
  parseResume,
  type ResumeForm,
} from "@/pages/resumeForm";

const inputClass = "w-full border border-[var(--line)] bg-[var(--paper)] px-2 py-1.5";
const areaClass = `${inputClass} min-h-[120px]`;
const lineClass = `${inputClass} min-h-[88px]`;

/** 简历：按栏目填写，分析和面试用拼好的正文 */
export function ResumePage() {
  const [items, setItems] = useState<ResumeDoc[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [title, setTitle] = useState("我的简历");
  const [draft, setDraft] = useState<ResumeForm>(emptyResume);
  const [analysis, setAnalysis] = useState("");
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function payload() {
    return {
      title,
      target_job: draft.basic.target_job,
      content: JSON.stringify(draft),
    };
  }

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
    const next = parseResume(doc?.content || "");
    if (doc?.target_job && !next.basic.target_job) next.basic.target_job = doc.target_job;
    setDraft(next);
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

  async function onSave() {
    setBusy(true);
    setError("");
    setHint("");
    try {
      if (currentId === null) {
        const created = await createResumeDoc(payload());
        await reloadList(created.id);
      } else {
        const saved = await updateResumeDoc(currentId, payload());
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
    if (currentId === null) return;
    setError("");
    try {
      await deleteResumeDoc(currentId);
      setAskDelete(false);
      setCurrentId(null);
      await reloadList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
      setAskDelete(false);
    }
  }

  async function persistThen(run: (id: number) => Promise<void>) {
    if (!flattenResume(draft).trim()) {
      setError("请先填写简历内容");
      return;
    }
    setBusy(true);
    setError("");
    setHint("");
    try {
      let id = currentId;
      if (id === null) {
        const created = await createResumeDoc(payload());
        id = created.id;
        await reloadList(created.id);
      } else {
        await updateResumeDoc(id, payload());
      }
      await run(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function onImport(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError("");
    setHint("");
    try {
      const created = await importResumeDoc(file);
      await reloadList(created.id);
      setHint("已导入");
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onExport() {
    await persistThen(async (id) => {
      await downloadResumeDoc(id, title || "简历");
      setHint("已导出 Word");
    });
  }

  async function onAnalyze() {
    await persistThen(async (id) => {
      const saved = await analyzeResumeDoc(id);
      setItems((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
      setAnalysis(saved.analysis);
      setHint("分析完成");
    });
  }

  async function onStartInterview() {
    await persistThen(async (id) => {
      const session = await startInterview(id);
      setMessages(session.messages);
    });
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

  const basic = draft.basic;

  return (
    <>
      {error ? <p className="mb-4 text-[var(--err)]">{error}</p> : null}
      {hint ? <p className="mb-4 text-[var(--ok)]">{hint}</p> : null}

      <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)]">
        <Card title="简历列表" className="px-5 py-4">
          <div className="mb-3 flex flex-wrap gap-2">
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={onCreate}>
              新建
            </button>
            <button
              type="button"
              className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              导入 Word
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => void onImport(e.target.files?.[0])}
            />
          </div>
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
            <label className="block">
              <span className="mb-1 block text-[var(--muted)]">这份简历叫什么</span>
              <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
          </Card>

          <Card title="基本信息" className="px-5 py-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="姓名" value={basic.name} onChange={(value) => setDraft({ ...draft, basic: { ...basic, name: value } })} />
              <Field label="求职意向" value={basic.target_job} onChange={(value) => setDraft({ ...draft, basic: { ...basic, target_job: value } })} />
              <Field label="毕业院校" value={basic.school} onChange={(value) => setDraft({ ...draft, basic: { ...basic, school: value } })} />
              <Field label="毕业时间" value={basic.grad_year} onChange={(value) => setDraft({ ...draft, basic: { ...basic, grad_year: value } })} />
              <Field label="学历" value={basic.education} onChange={(value) => setDraft({ ...draft, basic: { ...basic, education: value } })} />
              <Field label="专业" value={basic.major} onChange={(value) => setDraft({ ...draft, basic: { ...basic, major: value } })} />
              <Field label="年龄" value={basic.age} onChange={(value) => setDraft({ ...draft, basic: { ...basic, age: value } })} />
              <Field label="性别" value={basic.gender} onChange={(value) => setDraft({ ...draft, basic: { ...basic, gender: value } })} />
              <Field label="籍贯" value={basic.hometown} onChange={(value) => setDraft({ ...draft, basic: { ...basic, hometown: value } })} />
              <Field label="电话" value={basic.phone} onChange={(value) => setDraft({ ...draft, basic: { ...basic, phone: value } })} />
              <Field label="邮箱" value={basic.email} onChange={(value) => setDraft({ ...draft, basic: { ...basic, email: value } })} />
            </div>
          </Card>

          <Card title="自我评价" className="px-5 py-4">
            <textarea className={areaClass} value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} />
          </Card>

          <Card title="工作经历" className="px-5 py-4">
            <div className="space-y-5">
              {draft.jobs.map((job, index) => (
                <div key={index} className="border-t border-[var(--line)] pt-4 first:border-t-0 first:pt-0">
                  <div className="mb-3 flex justify-end">
                    <button type="button" className="text-[13px] text-[var(--muted)]" onClick={() => setDraft({ ...draft, jobs: draft.jobs.filter((_, i) => i !== index) })}>
                      删除这段
                    </button>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label="时间" value={job.period} onChange={(value) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === index ? { ...item, period: value } : item)) })} />
                    <Field label="公司" value={job.company} onChange={(value) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === index ? { ...item, company: value } : item)) })} />
                    <Field label="职位" value={job.role} onChange={(value) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === index ? { ...item, role: value } : item)) })} />
                  </div>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-[var(--muted)]">公司 / 岗位说明</span>
                    <textarea
                      className={lineClass}
                      value={job.intro}
                      onChange={(e) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === index ? { ...item, intro: e.target.value } : item)) })}
                    />
                  </label>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-[var(--muted)]">工作内容（一行一条）</span>
                    <textarea
                      className={areaClass}
                      value={listToLines(job.bullets)}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          jobs: draft.jobs.map((item, i) => (i === index ? { ...item, bullets: linesToList(e.target.value) } : item)),
                        })
                      }
                    />
                  </label>
                </div>
              ))}
            </div>
            <button type="button" className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setDraft({ ...draft, jobs: [...draft.jobs, emptyJob()] })}>
              添加一段经历
            </button>
          </Card>

          <Card title="个人技能" className="px-5 py-4">
            <div className="space-y-5">
              {draft.skills.map((skill, index) => (
                <div key={index} className="border-t border-[var(--line)] pt-4 first:border-t-0 first:pt-0">
                  <div className="mb-3 flex justify-end">
                    <button type="button" className="text-[13px] text-[var(--muted)]" onClick={() => setDraft({ ...draft, skills: draft.skills.filter((_, i) => i !== index) })}>
                      删除这组
                    </button>
                  </div>
                  <Field
                    label="分组名称，如 AI 应用、全栈开发"
                    value={skill.title}
                    onChange={(value) => setDraft({ ...draft, skills: draft.skills.map((item, i) => (i === index ? { ...item, title: value } : item)) })}
                  />
                  <label className="mt-3 block">
                    <span className="mb-1 block text-[var(--muted)]">技能条目（一行一条）</span>
                    <textarea
                      className={areaClass}
                      value={listToLines(skill.bullets)}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          skills: draft.skills.map((item, i) => (i === index ? { ...item, bullets: linesToList(e.target.value) } : item)),
                        })
                      }
                    />
                  </label>
                </div>
              ))}
            </div>
            <button type="button" className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setDraft({ ...draft, skills: [...draft.skills, emptySkill()] })}>
              添加一组技能
            </button>
          </Card>

          <Card title="项目经历" className="px-5 py-4">
            <div className="space-y-5">
              {draft.projects.map((project, index) => (
                <div key={index} className="border-t border-[var(--line)] pt-4 first:border-t-0 first:pt-0">
                  <div className="mb-3 flex justify-end">
                    <button
                      type="button"
                      className="text-[13px] text-[var(--muted)]"
                      onClick={() => setDraft({ ...draft, projects: draft.projects.filter((_, i) => i !== index) })}
                    >
                      删除这个项目
                    </button>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field
                      label="项目名称"
                      value={project.name}
                      onChange={(value) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === index ? { ...item, name: value } : item)) })}
                    />
                    <Field
                      label="技术栈"
                      value={project.stack}
                      onChange={(value) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === index ? { ...item, stack: value } : item)) })}
                    />
                  </div>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-[var(--muted)]">项目介绍</span>
                    <textarea
                      className={lineClass}
                      value={project.goal}
                      onChange={(e) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === index ? { ...item, goal: e.target.value } : item)) })}
                    />
                  </label>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-[var(--muted)]">个人职责（一行一条）</span>
                    <textarea
                      className={areaClass}
                      value={listToLines(project.duties)}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          projects: draft.projects.map((item, i) => (i === index ? { ...item, duties: linesToList(e.target.value) } : item)),
                        })
                      }
                    />
                  </label>
                  <label className="mt-3 block">
                    <span className="mb-1 block text-[var(--muted)]">项目成果</span>
                    <textarea
                      className={lineClass}
                      value={project.result}
                      onChange={(e) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === index ? { ...item, result: e.target.value } : item)) })}
                    />
                  </label>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5"
              onClick={() => setDraft({ ...draft, projects: [...draft.projects, emptyProject()] })}
            >
              添加一个项目
            </button>
          </Card>

          <div className="flex gap-3">
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onSave()}>
              保存
            </button>
            <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onExport()}>
              导出 Word
            </button>
            {currentId !== null ? (
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => setAskDelete(true)}>
                删除
              </button>
            ) : null}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="AI 分析" className="px-5 py-4">
              <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onAnalyze()}>
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

      {askDelete ? (
        <ConfirmModal title="删除简历" message="删掉后不能恢复。确定删除？" onConfirm={() => void onDelete()} onClose={() => setAskDelete(false)} />
      ) : null}
    </>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[var(--muted)]">{label}</span>
      <input className={inputClass} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
