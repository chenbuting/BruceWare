"""知识库会话：留下的对话，不参与检索证据。"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kb.models import KbSession, KbSessionTurn


def session_dict(row: KbSession) -> dict:
    return {
        "id": row.id,
        "library_id": row.library_id,
        "title": row.title or "新对话",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def title_from_question(question: str) -> str:
    text = " ".join((question or "").split())
    return (text[:40] or "新对话").strip()


def list_sessions(db: Session, library_id: int) -> list[KbSession]:
    return list(
        db.scalars(select(KbSession).where(KbSession.library_id == library_id).order_by(KbSession.updated_at.desc())).all()
    )


def get_session(db: Session, session_id: int, library_id: int | None = None) -> KbSession | None:
    row = db.get(KbSession, session_id)
    if row is None:
        return None
    if library_id is not None and row.library_id != library_id:
        return None
    return row


def create_session(db: Session, library_id: int, title: str = "") -> KbSession:
    now = datetime.utcnow()
    row = KbSession(library_id=library_id, title=(title or "").strip() or "新对话", created_at=now, updated_at=now)
    db.add(row)
    db.flush()
    return row


def ensure_session(db: Session, library_id: int, session_id: int | None, question: str) -> KbSession:
    """有会话就用，没有就按这句问新建。"""

    if session_id:
        row = get_session(db, session_id, library_id)
        if row is not None:
            return row
    return create_session(db, library_id, title_from_question(question))


def save_turn(db: Session, session: KbSession, question: str, result: dict) -> KbSession:
    now = datetime.utcnow()
    db.add(
        KbSessionTurn(
            session_id=session.id,
            question=question,
            answer=str(result.get("answer") or ""),
            result_json=json.dumps(result, ensure_ascii=False),
            created_at=now,
        )
    )
    session.updated_at = now
    if not session.title or session.title == "新对话":
        session.title = title_from_question(question)
    db.commit()
    db.refresh(session)
    return session


def load_turns(db: Session, session_id: int) -> list[dict]:
    rows = db.scalars(select(KbSessionTurn).where(KbSessionTurn.session_id == session_id).order_by(KbSessionTurn.id.asc())).all()
    turns: list[dict] = []
    for row in rows:
        try:
            result = json.loads(row.result_json or "")
        except json.JSONDecodeError:
            result = {}
        if not isinstance(result, dict):
            result = {}
        result.setdefault("answer", row.answer)
        result.setdefault("citations", [])
        result.setdefault("used_llm", True)
        turns.append({"question": row.question, "result": result})
    return turns


def delete_session(db: Session, row: KbSession) -> None:
    db.execute(KbSessionTurn.__table__.delete().where(KbSessionTurn.session_id == row.id))
    db.delete(row)
    db.commit()


def delete_library_sessions(db: Session, library_id: int) -> None:
    ids = list(db.scalars(select(KbSession.id).where(KbSession.library_id == library_id)).all())
    if not ids:
        return
    db.execute(KbSessionTurn.__table__.delete().where(KbSessionTurn.session_id.in_(ids)))
    db.execute(KbSession.__table__.delete().where(KbSession.library_id == library_id))
