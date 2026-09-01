"""把栏目简历拼成一段文字，给分析和面试用。"""

from __future__ import annotations

import json
from typing import Any


def flatten_resume(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except Exception:
        return text
    if not isinstance(data, dict) or data.get("version") != 1:
        return text

    basic = data.get("basic") if isinstance(data.get("basic"), dict) else {}
    parts: list[str] = []
    name = str(basic.get("name") or "").strip()
    if name:
        parts.append(name)
    info = [
        _kv("毕业院校", basic.get("school")),
        _kv("毕业时间", basic.get("grad_year")),
        _kv("学历", basic.get("education")),
        _kv("年龄", basic.get("age")),
        _kv("专业", basic.get("major")),
        _kv("籍贯", basic.get("hometown")),
        _kv("性别", basic.get("gender")),
        _kv("电话", basic.get("phone")),
        _kv("邮箱", basic.get("email")),
        _kv("求职意向", basic.get("target_job")),
    ]
    info = [item for item in info if item]
    if info:
        parts.append("  ".join(info))

    summary = str(data.get("summary") or "").strip()
    if summary:
        parts.extend(["自我评价", summary])

    jobs = data.get("jobs") if isinstance(data.get("jobs"), list) else []
    if any(_job_has(item) for item in jobs):
        parts.append("工作经历")
        for job in jobs:
            if not isinstance(job, dict) or not _job_has(job):
                continue
            head = "  ".join(
                item for item in (str(job.get("period") or "").strip(), str(job.get("company") or "").strip(), str(job.get("role") or "").strip()) if item
            )
            if head:
                parts.append(head)
            intro = str(job.get("intro") or "").strip()
            if intro:
                parts.append(intro)
            parts.extend(_bullets(job.get("bullets")))

    skills = data.get("skills") if isinstance(data.get("skills"), list) else []
    if any(_skill_has(item) for item in skills):
        parts.append("个人技能")
        for skill in skills:
            if not isinstance(skill, dict) or not _skill_has(skill):
                continue
            title = str(skill.get("title") or "").strip()
            if title:
                parts.append(title)
            parts.extend(_bullets(skill.get("bullets")))

    projects = data.get("projects") if isinstance(data.get("projects"), list) else []
    if any(_project_has(item) for item in projects):
        parts.append("项目经历")
        for project in projects:
            if not isinstance(project, dict) or not _project_has(project):
                continue
            name = str(project.get("name") or "").strip()
            if name:
                parts.append(name)
            stack = str(project.get("stack") or "").strip()
            if stack:
                parts.append(f"技术栈：{stack}")
            goal = str(project.get("goal") or "").strip()
            if goal:
                parts.append(f"项目介绍：{goal}")
            duties = _bullets(project.get("duties"))
            if duties:
                parts.append("个人职责")
                parts.extend(duties)
            result = str(project.get("result") or "").strip()
            if result:
                parts.append(f"项目成果：{result}")

    return "\n".join(parts)


def _kv(label: str, value: Any) -> str:
    text = str(value or "").strip()
    return f"{label}：{text}" if text else ""


def _bullets(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    items = [str(item).strip() for item in raw if str(item).strip()]
    return [f"{index + 1}、{item}" for index, item in enumerate(items)]


def _job_has(job: Any) -> bool:
    if not isinstance(job, dict):
        return False
    return any(str(job.get(key) or "").strip() for key in ("period", "company", "role", "intro")) or bool(_bullets(job.get("bullets")))


def _skill_has(skill: Any) -> bool:
    if not isinstance(skill, dict):
        return False
    return bool(str(skill.get("title") or "").strip()) or bool(_bullets(skill.get("bullets")))


def _project_has(project: Any) -> bool:
    if not isinstance(project, dict):
        return False
    return any(str(project.get(key) or "").strip() for key in ("name", "stack", "goal", "result")) or bool(_bullets(project.get("duties")))
