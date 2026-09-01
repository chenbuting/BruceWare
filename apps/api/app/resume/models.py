"""简历与模拟面试表。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.db.session import Base


class ResumeDoc(Base):
    """一份简历。"""

    __tablename__ = "resume_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, default="我的简历")
    target_job = Column(String(200), nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    analysis = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ResumeInterview(Base):
    """一次模拟面试。"""

    __tablename__ = "resume_interviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resume_docs.id"), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ResumeInterviewMessage(Base):
    """模拟面试的一句对话。"""

    __tablename__ = "resume_interview_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    interview_id = Column(Integer, ForeignKey("resume_interviews.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
