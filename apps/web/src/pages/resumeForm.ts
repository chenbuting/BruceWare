/** 按栏目存简历，和 Word 充实版栏目对齐。 */

export type ResumeJob = {
  period: string;
  company: string;
  role: string;
  intro: string;
  bullets: string[];
};

export type ResumeSkill = {
  title: string;
  bullets: string[];
};

export type ResumeProject = {
  name: string;
  stack: string;
  goal: string;
  duties: string[];
  result: string;
};

export type ResumeForm = {
  version: 1;
  basic: {
    name: string;
    school: string;
    grad_year: string;
    education: string;
    age: string;
    major: string;
    hometown: string;
    gender: string;
    phone: string;
    email: string;
    target_job: string;
  };
  summary: string;
  jobs: ResumeJob[];
  skills: ResumeSkill[];
  projects: ResumeProject[];
};

export function emptyResume(): ResumeForm {
  return {
    version: 1,
    basic: {
      name: "",
      school: "",
      grad_year: "",
      education: "",
      age: "",
      major: "",
      hometown: "",
      gender: "",
      phone: "",
      email: "",
      target_job: "",
    },
    summary: "",
    jobs: [],
    skills: [],
    projects: [],
  };
}

export function emptyJob(): ResumeJob {
  return { period: "", company: "", role: "", intro: "", bullets: [""] };
}

export function emptySkill(): ResumeSkill {
  return { title: "", bullets: [""] };
}

export function emptyProject(): ResumeProject {
  return { name: "", stack: "", goal: "", duties: [""], result: "" };
}

export function parseResume(raw: string): ResumeForm {
  const text = (raw || "").trim();
  if (!text) return emptyResume();
  try {
    const data = JSON.parse(text) as ResumeForm;
    if (data && data.version === 1 && data.basic) {
      const base = emptyResume();
      return {
        ...base,
        ...data,
        version: 1,
        basic: { ...base.basic, ...data.basic },
        jobs: data.jobs || [],
        skills: data.skills || [],
        projects: data.projects || [],
      };
    }
  } catch {
    /* 旧版纯文本 */
  }
  const draft = emptyResume();
  draft.summary = text;
  return draft;
}

export function linesToList(text: string): string[] {
  const items = text.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  return items.length > 0 ? items : [""];
}

export function listToLines(items: string[]): string {
  return items.filter((item) => item.trim()).join("\n");
}

export function flattenResume(form: ResumeForm): string {
  const b = form.basic;
  const parts: string[] = [];
  if (b.name) parts.push(b.name);
  const info = [
    b.school && `毕业院校：${b.school}`,
    b.grad_year && `毕业时间：${b.grad_year}`,
    b.education && `学历：${b.education}`,
    b.age && `年龄：${b.age}`,
    b.major && `专业：${b.major}`,
    b.hometown && `籍贯：${b.hometown}`,
    b.gender && `性别：${b.gender}`,
    b.phone && `电话：${b.phone}`,
    b.email && `邮箱：${b.email}`,
    b.target_job && `求职意向：${b.target_job}`,
  ].filter(Boolean);
  if (info.length) parts.push(info.join("  "));
  if (form.summary.trim()) parts.push("自我评价", form.summary.trim());
  if (form.jobs.some((item) => item.company || item.role || item.period)) {
    parts.push("工作经历");
    for (const job of form.jobs) {
      const head = [job.period, job.company, job.role].filter(Boolean).join("  ");
      if (head) parts.push(head);
      if (job.intro.trim()) parts.push(job.intro.trim());
      job.bullets.filter((item) => item.trim()).forEach((item, index) => parts.push(`${index + 1}、${item.trim()}`));
    }
  }
  if (form.skills.some((item) => item.title || item.bullets.some((line) => line.trim()))) {
    parts.push("个人技能");
    for (const skill of form.skills) {
      if (skill.title.trim()) parts.push(skill.title.trim());
      skill.bullets.filter((item) => item.trim()).forEach((item, index) => parts.push(`${index + 1}、${item.trim()}`));
    }
  }
  if (form.projects.some((item) => item.name || item.goal)) {
    parts.push("项目经历");
    for (const project of form.projects) {
      if (project.name.trim()) parts.push(project.name.trim());
      if (project.stack.trim()) parts.push(`技术栈：${project.stack.trim()}`);
      if (project.goal.trim()) parts.push(`项目介绍：${project.goal.trim()}`);
      if (project.duties.some((item) => item.trim())) {
        parts.push("个人职责");
        project.duties.filter((item) => item.trim()).forEach((item, index) => parts.push(`${index + 1}、${item.trim()}`));
      }
      if (project.result.trim()) parts.push(`项目成果：${project.result.trim()}`);
    }
  }
  return parts.join("\n");
}
