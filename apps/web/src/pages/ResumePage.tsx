import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  analyzeResumeDoc,
  createResumeDoc,
  deleteResumeDoc,
  downloadResumeDoc,
  fetchInterview,
  fetchResumeDocs,
  generateResumeIntro,
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
const areaClass = `${inputClass} min-h-[96px]`;
const lineClass = `${inputClass} min-h-[72px]`;

type ResumeSection = "basic" | "summary" | "jobs" | "skills" | "projects" | "intro" | "analyze" | "interview";

const SECTIONS: { id: ResumeSection; label: string }[] = [
  { id: "basic", label: "基本信息" },
  { id: "summary", label: "自我评价" },
  { id: "jobs", label: "工作经历" },
  { id: "skills", label: "个人技能" },
  { id: "projects", label: "项目经历" },
  { id: "intro", label: "自我介绍" },
  { id: "analyze", label: "AI 分析" },
  { id: "interview", label: "模拟面试" },
];

/** 简历：左边选简历，右边按栏目切换，避免整页拉很长 */
export function ResumePage() {
  const [items, setItems] = useState<ResumeDoc[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [title, setTitle] = useState("我的简历");
  const [draft, setDraft] = useState<ResumeForm>(emptyResume);
  const [analysis, setAnalysis] = useState("");
  const [intro, setIntro] = useState("");
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [reply, setReply] = useState("");
  const [error, setError] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [section, setSection] = useState<ResumeSection>("basic");
  const [jobIndex, setJobIndex] = useState(0);
  const [skillIndex, setSkillIndex] = useState(0);
  const [projectIndex, setProjectIndex] = useState(0);
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
    setIntro(doc?.intro || "");
    setJobIndex(0);
    setSkillIndex(0);
    setProjectIndex(0);
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
        setIntro(saved.intro || "");
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
    setSection("basic");
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
      setSection("basic");
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

  async function onIntro() {
    await persistThen(async (id) => {
      const saved = await generateResumeIntro(id);
      setItems((prev) => prev.map((item) => (item.id === saved.id ? saved : item)));
      setIntro(saved.intro || "");
      setHint("自我介绍已生成");
    });
  }

  async function onCopyIntro() {
    if (!intro.trim()) return;
    try {
      await navigator.clipboard.writeText(intro);
      setHint("已复制");
    } catch {
      setError("复制失败，请自己选中文字复制");
    }
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
  const job = draft.jobs[jobIndex];
  const skill = draft.skills[skillIndex];
  const project = draft.projects[projectIndex];
  const sectionLabel = SECTIONS.find((item) => item.id === section)?.label || "";

  function sectionCount(id: ResumeSection) {
    if (id === "jobs") return draft.jobs.length;
    if (id === "skills") return draft.skills.length;
    if (id === "projects") return draft.projects.length;
    return 0;
  }

  return (
    <>
      <div className="grid gap-4 xl:grid-cols-[200px_minmax(0,1fr)]">
        <Card title="简历列表" className="h-fit px-5 py-4 xl:sticky xl:top-0">
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

        <div className="min-w-0 space-y-3">
          {error ? <p className="text-[var(--err)]">{error}</p> : null}
          {hint ? <p className="text-[var(--ok)]">{hint}</p> : null}

          <Card className="px-5 py-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
              <label className="block min-w-0 flex-1">
                <span className="mb-1 block text-[var(--muted)]">这份简历叫什么</span>
                <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
              </label>
              <div className="flex shrink-0 flex-wrap gap-2">
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
            </div>
            <div className="mt-4 flex flex-wrap gap-1 border-t border-[var(--line)] pt-3">
              {SECTIONS.map((item) => {
                const count = sectionCount(item.id);
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`rounded-md px-2.5 py-1.5 text-[13px] ${
                      section === item.id ? "bg-[var(--bg)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"
                    }`}
                    onClick={() => setSection(item.id)}
                  >
                    {item.label}
                    {count > 0 ? ` ${count}` : ""}
                  </button>
                );
              })}
            </div>
          </Card>

          <Card title={sectionLabel} className="px-5 py-4">
            {section === "basic" ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
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
            ) : null}

            {section === "summary" ? (
              <textarea className={`${areaClass} min-h-[220px]`} value={draft.summary} onChange={(e) => setDraft({ ...draft, summary: e.target.value })} />
            ) : null}

            {section === "jobs" ? (
              <div>
                <EntryTabs
                  labels={draft.jobs.map((item, index) => item.company || item.role || item.period || `经历 ${index + 1}`)}
                  current={jobIndex}
                  onSelect={setJobIndex}
                />
                {job ? (
                  <div>
                    <div className="mb-3 flex justify-end">
                      <button
                        type="button"
                        className="text-[13px] text-[var(--muted)]"
                        onClick={() => {
                          const next = draft.jobs.filter((_, i) => i !== jobIndex);
                          setDraft({ ...draft, jobs: next });
                          setJobIndex(Math.max(0, Math.min(jobIndex, next.length - 1)));
                        }}
                      >
                        删除这段
                      </button>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <Field label="时间" value={job.period} onChange={(value) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === jobIndex ? { ...item, period: value } : item)) })} />
                      <Field label="公司" value={job.company} onChange={(value) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === jobIndex ? { ...item, company: value } : item)) })} />
                      <Field label="职位" value={job.role} onChange={(value) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === jobIndex ? { ...item, role: value } : item)) })} />
                    </div>
                    <label className="mt-3 block">
                      <span className="mb-1 block text-[var(--muted)]">公司 / 岗位说明</span>
                      <textarea
                        className={lineClass}
                        value={job.intro}
                        onChange={(e) => setDraft({ ...draft, jobs: draft.jobs.map((item, i) => (i === jobIndex ? { ...item, intro: e.target.value } : item)) })}
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
                            jobs: draft.jobs.map((item, i) => (i === jobIndex ? { ...item, bullets: linesToList(e.target.value) } : item)),
                          })
                        }
                      />
                    </label>
                  </div>
                ) : (
                  <p className="text-[13px] text-[var(--muted)]">还没有工作经历。</p>
                )}
                <button
                  type="button"
                  className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5"
                  onClick={() => {
                    setDraft({ ...draft, jobs: [...draft.jobs, emptyJob()] });
                    setJobIndex(draft.jobs.length);
                  }}
                >
                  添加一段经历
                </button>
              </div>
            ) : null}

            {section === "skills" ? (
              <div>
                <EntryTabs
                  labels={draft.skills.map((item, index) => item.title || `技能 ${index + 1}`)}
                  current={skillIndex}
                  onSelect={setSkillIndex}
                />
                {skill ? (
                  <div>
                    <div className="mb-3 flex justify-end">
                      <button
                        type="button"
                        className="text-[13px] text-[var(--muted)]"
                        onClick={() => {
                          const next = draft.skills.filter((_, i) => i !== skillIndex);
                          setDraft({ ...draft, skills: next });
                          setSkillIndex(Math.max(0, Math.min(skillIndex, next.length - 1)));
                        }}
                      >
                        删除这组
                      </button>
                    </div>
                    <Field
                      label="分组名称，如 AI 应用、全栈开发"
                      value={skill.title}
                      onChange={(value) => setDraft({ ...draft, skills: draft.skills.map((item, i) => (i === skillIndex ? { ...item, title: value } : item)) })}
                    />
                    <label className="mt-3 block">
                      <span className="mb-1 block text-[var(--muted)]">技能条目（一行一条）</span>
                      <textarea
                        className={areaClass}
                        value={listToLines(skill.bullets)}
                        onChange={(e) =>
                          setDraft({
                            ...draft,
                            skills: draft.skills.map((item, i) => (i === skillIndex ? { ...item, bullets: linesToList(e.target.value) } : item)),
                          })
                        }
                      />
                    </label>
                  </div>
                ) : (
                  <p className="text-[13px] text-[var(--muted)]">还没有技能分组。</p>
                )}
                <button
                  type="button"
                  className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5"
                  onClick={() => {
                    setDraft({ ...draft, skills: [...draft.skills, emptySkill()] });
                    setSkillIndex(draft.skills.length);
                  }}
                >
                  添加一组技能
                </button>
              </div>
            ) : null}

            {section === "projects" ? (
              <div>
                <EntryTabs
                  labels={draft.projects.map((item, index) => item.name || `项目 ${index + 1}`)}
                  current={projectIndex}
                  onSelect={setProjectIndex}
                />
                {project ? (
                  <div>
                    <div className="mb-3 flex justify-end">
                      <button
                        type="button"
                        className="text-[13px] text-[var(--muted)]"
                        onClick={() => {
                          const next = draft.projects.filter((_, i) => i !== projectIndex);
                          setDraft({ ...draft, projects: next });
                          setProjectIndex(Math.max(0, Math.min(projectIndex, next.length - 1)));
                        }}
                      >
                        删除这个项目
                      </button>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field
                        label="项目名称"
                        value={project.name}
                        onChange={(value) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === projectIndex ? { ...item, name: value } : item)) })}
                      />
                      <Field
                        label="技术栈"
                        value={project.stack}
                        onChange={(value) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === projectIndex ? { ...item, stack: value } : item)) })}
                      />
                    </div>
                    <label className="mt-3 block">
                      <span className="mb-1 block text-[var(--muted)]">项目介绍</span>
                      <textarea
                        className={lineClass}
                        value={project.goal}
                        onChange={(e) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === projectIndex ? { ...item, goal: e.target.value } : item)) })}
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
                            projects: draft.projects.map((item, i) => (i === projectIndex ? { ...item, duties: linesToList(e.target.value) } : item)),
                          })
                        }
                      />
                    </label>
                    <label className="mt-3 block">
                      <span className="mb-1 block text-[var(--muted)]">项目成果</span>
                      <textarea
                        className={lineClass}
                        value={project.result}
                        onChange={(e) => setDraft({ ...draft, projects: draft.projects.map((item, i) => (i === projectIndex ? { ...item, result: e.target.value } : item)) })}
                      />
                    </label>
                  </div>
                ) : (
                  <p className="text-[13px] text-[var(--muted)]">还没有项目。</p>
                )}
                <button
                  type="button"
                  className="mt-4 border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5"
                  onClick={() => {
                    setDraft({ ...draft, projects: [...draft.projects, emptyProject()] });
                    setProjectIndex(draft.projects.length);
                  }}
                >
                  添加一个项目
                </button>
              </div>
            ) : null}

            {section === "intro" ? (
              <div>
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onIntro()}>
                    {intro ? "再生成" : "生成自我介绍"}
                  </button>
                  {intro ? (
                    <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5" onClick={() => void onCopyIntro()}>
                      复制
                    </button>
                  ) : null}
                </div>
                {intro ? (
                  <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap text-[13px] leading-6 text-[var(--muted)]">{intro}</pre>
                ) : (
                  <p className="mt-3 text-[13px] text-[var(--muted)]">按简历生成一段大约1分钟的面试开场自我介绍。先保存简历，并在设置里配好 AI。</p>
                )}
              </div>
            ) : null}

            {section === "analyze" ? (
              <div>
                <button type="button" className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50" disabled={busy} onClick={() => void onAnalyze()}>
                  开始分析
                </button>
                {analysis ? (
                  <pre className="mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap text-[13px] leading-6 text-[var(--muted)]">{analysis}</pre>
                ) : (
                  <p className="mt-3 text-[13px] text-[var(--muted)]">还没有分析。先保存简历，并在设置里配好 AI。</p>
                )}
              </div>
            ) : null}

            {section === "interview" ? (
              <div>
                <button
                  type="button"
                  className="border border-[var(--line)] bg-[var(--paper)] px-3 py-1.5 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void onStartInterview()}
                >
                  {messages.length > 0 ? "重新开始" : "开始面试"}
                </button>
                <div className="mt-3 max-h-[360px] space-y-3 overflow-auto text-[13px] leading-6">
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
              </div>
            ) : null}
          </Card>
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

/** 多段经历 / 技能 / 项目时，一次只展开一段 */
function EntryTabs({ labels, current, onSelect }: { labels: string[]; current: number; onSelect: (index: number) => void }) {
  if (labels.length <= 1) return null;
  return (
    <div className="mb-4 flex flex-wrap gap-1">
      {labels.map((label, index) => (
        <button
          key={`${label}-${index}`}
          type="button"
          className={`max-w-[12rem] truncate rounded-md px-2 py-1 text-[13px] ${
            index === current ? "bg-[var(--bg)]" : "text-[var(--muted)] hover:bg-[var(--hover)]"
          }`}
          onClick={() => onSelect(index)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
