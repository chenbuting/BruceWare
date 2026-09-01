"""简历：保存、AI 分析、打字模拟面试。"""

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ai import chat_complete
from app.core.response import fail, ok
from app.db.session import get_db
from app.resume.docx_io import build_docx, parse_docx
from app.resume.models import ResumeDoc, ResumeInterview, ResumeInterviewMessage
from app.resume.text import flatten_resume

router = APIRouter()


class ResumeIn(BaseModel):
    title: str = Field(default="我的简历", max_length=200)
    target_job: str = Field(default="", max_length=200)
    content: str = Field(default="")


class InterviewReplyIn(BaseModel):
    content: str = Field(min_length=1)


class IntroIn(BaseModel):
    style: str = Field(default="formal", max_length=20)


INTRO_STYLES = {
    "formal": "风格：稳重正式。大约1分钟，语气沉稳，适合常规面试。",
    "concise": "风格：简洁干练。大约30秒，少铺垫，尽快点明能力和求职意向。",
    "warm": "风格：亲和自然。像聊天一样说，不要太书面，但仍要专业。",
    "project": "风格：项目亮点。多用一两个具体项目说明你做了什么、结果如何。",
    "result": "风格：成果导向。尽量带出可感知的结果、效率或落地情况，少讲空话。",
    "funny": "风格：轻松搞笑。口语、有一点幽默，但内容仍要真实、能用在面试里，不要段子和冒犯。",
}


def _doc_dict(row: ResumeDoc) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "target_job": row.target_job or "",
        "content": row.content or "",
        "analysis": row.analysis or "",
        "intro": getattr(row, "intro", "") or "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _msg_dict(row: ResumeInterviewMessage) -> dict:
    return {"id": row.id, "role": row.role, "content": row.content or ""}


@router.get("/resume/docs")
def list_docs(db: Session = Depends(get_db)):
    rows = db.scalars(select(ResumeDoc).order_by(ResumeDoc.updated_at.desc())).all()
    return ok({"items": [_doc_dict(row) for row in rows]})


@router.post("/resume/docs")
def create_doc(body: ResumeIn, db: Session = Depends(get_db)):
    title = body.title.strip() or "我的简历"
    row = ResumeDoc(
        title=title,
        target_job=body.target_job.strip(),
        content=body.content.strip(),
        analysis="",
        intro="",
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


@router.put("/resume/docs/{doc_id}")
def update_doc(doc_id: int, body: ResumeIn, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    row.title = body.title.strip() or "我的简历"
    row.target_job = body.target_job.strip()
    row.content = body.content.strip()
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


@router.get("/resume/docs/{doc_id}/export")
def export_doc(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    data = build_docx(row.title, row.content or "")
    filename = f"{(row.title or '简历').strip() or '简历'}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=\"resume.docx\"; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.post("/resume/docs/import")
async def import_doc(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = (file.filename or "").strip()
    if name.startswith("~$") or not name.lower().endswith(".docx"):
        return fail("请上传 Word（.docx）")
    raw = await file.read()
    if not raw:
        return fail("文件是空的")
    try:
        form = parse_docx(raw)
    except Exception:
        return fail("这个 Word 读不出来，请用充实版这类 .docx")
    title = str(form.get("basic", {}).get("name") or Path(name).stem or "导入的简历").strip()
    target = str(form.get("basic", {}).get("target_job") or "").strip()
    row = ResumeDoc(
        title=title[:200] or "导入的简历",
        target_job=target[:200],
        content=json.dumps(form, ensure_ascii=False),
        analysis="",
        intro="",
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


@router.delete("/resume/docs/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    interviews = db.scalars(select(ResumeInterview).where(ResumeInterview.resume_id == doc_id)).all()
    for item in interviews:
        db.query(ResumeInterviewMessage).filter(ResumeInterviewMessage.interview_id == item.id).delete()
        db.delete(item)
    db.delete(row)
    db.commit()
    return ok(True)


@router.post("/resume/docs/{doc_id}/analyze")
def analyze_doc(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    body_text = flatten_resume(row.content or "")
    if not body_text.strip():
        return fail("请先填写简历内容")
    job = row.target_job.strip() or "未指定"
    prompt = (
        "你是资深招聘顾问。根据简历给出中文分析，分三块：优点、风险/不足、可改的具体建议。"
        "每块用短句条目，不要空话。\n"
        f"目标岗位：{job}\n\n简历：\n{body_text}"
    )
    try:
        text = chat_complete(
            [
                {"role": "system", "content": "用简洁中文回答，方便求职者改简历。"},
                {"role": "user", "content": prompt},
            ]
        )
    except ValueError as exc:
        return fail(str(exc))
    row.analysis = text
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


@router.post("/resume/docs/{doc_id}/intro")
def generate_intro(doc_id: int, body: IntroIn = IntroIn(), db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    body_text = flatten_resume(row.content or "")
    if not body_text.strip():
        return fail("请先填写简历内容")
    job = row.target_job.strip() or "未指定岗位"
    style_key = (body.style or "formal").strip()
    style_hint = INTRO_STYLES.get(style_key) or INTRO_STYLES["formal"]
    prompt = (
        "根据简历写一段中文口头自我介绍，像面试开场时说出来。"
        "用第一人称，连贯成段，不要条目、不要标题、不要括号提示。"
        "先讲身份和求职意向，再挑能证明能力的经历，最后收一句为什么适合这个岗位。\n"
        f"{style_hint}\n"
        f"目标岗位：{job}\n\n简历：\n{body_text}"
    )
    try:
        text = chat_complete(
            [
                {"role": "system", "content": "你是面试教练，写出能直接开口说的自我介绍。"},
                {"role": "user", "content": prompt},
            ]
        )
    except ValueError as exc:
        return fail(str(exc))
    row.intro = text
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return ok(_doc_dict(row))


def _latest_interview(db: Session, resume_id: int) -> ResumeInterview | None:
    return db.scalars(
        select(ResumeInterview)
        .where(ResumeInterview.resume_id == resume_id)
        .order_by(ResumeInterview.id.desc())
    ).first()


def _interview_payload(db: Session, interview: ResumeInterview) -> dict:
    messages = db.scalars(
        select(ResumeInterviewMessage)
        .where(ResumeInterviewMessage.interview_id == interview.id)
        .order_by(ResumeInterviewMessage.id.asc())
    ).all()
    return {
        "id": interview.id,
        "resume_id": interview.resume_id,
        "messages": [_msg_dict(item) for item in messages if item.role != "system"],
    }


@router.get("/resume/docs/{doc_id}/interview")
def get_interview(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    interview = _latest_interview(db, doc_id)
    if interview is None:
        return ok({"id": None, "resume_id": doc_id, "messages": []})
    return ok(_interview_payload(db, interview))


@router.post("/resume/docs/{doc_id}/interview/start")
def start_interview(doc_id: int, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    body_text = flatten_resume(row.content or "")
    if not body_text.strip():
        return fail("请先填写简历内容")
    job = row.target_job.strip() or "未指定岗位"
    system = (
        "你是面试官，用中文进行一轮打字模拟面试。"
        "每次只问一个问题，根据简历和对方回答追问。"
        "对方说结束或你认为问得差不多时，给简短总评。"
        f"目标岗位：{job}\n简历：\n{body_text}"
    )
    try:
        first = chat_complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": "请开始面试，先做简短开场并问第一个问题。"},
            ]
        )
    except ValueError as exc:
        return fail(str(exc))

    interview = ResumeInterview(resume_id=doc_id)
    db.add(interview)
    db.flush()
    db.add(ResumeInterviewMessage(interview_id=interview.id, role="system", content=system))
    db.add(ResumeInterviewMessage(interview_id=interview.id, role="assistant", content=first))
    db.commit()
    db.refresh(interview)
    return ok(_interview_payload(db, interview))


@router.post("/resume/docs/{doc_id}/interview/reply")
def reply_interview(doc_id: int, body: InterviewReplyIn, db: Session = Depends(get_db)):
    row = db.get(ResumeDoc, doc_id)
    if row is None:
        return fail("没有这份简历")
    interview = _latest_interview(db, doc_id)
    if interview is None:
        return fail("请先开始面试")
    text = body.content.strip()
    if not text:
        return fail("请先写回答")

    history = db.scalars(
        select(ResumeInterviewMessage)
        .where(ResumeInterviewMessage.interview_id == interview.id)
        .order_by(ResumeInterviewMessage.id.asc())
    ).all()
    messages = [{"role": item.role, "content": item.content} for item in history]
    messages.append({"role": "user", "content": text})
    try:
        answer = chat_complete(messages)
    except ValueError as exc:
        return fail(str(exc))

    db.add(ResumeInterviewMessage(interview_id=interview.id, role="user", content=text))
    db.add(ResumeInterviewMessage(interview_id=interview.id, role="assistant", content=answer))
    db.commit()
    return ok(_interview_payload(db, interview))
