"""知识库表：库、文件夹、文档。后期字段先占位。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.session import Base


class KbLibrary(Base):
    """一个知识库。"""

    __tablename__ = "kb_libraries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    description = Column(String(500), nullable=False, default="")
    policy_json = Column(Text, nullable=False, default="")
    extra = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class KbFolder(Base):
    """库内文件夹。parent_id 空表示库根下。"""

    __tablename__ = "kb_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    library_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, nullable=True)
    name = Column(String(200), nullable=False)


class KbDocument(Base):
    """库内一份资料。"""

    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    library_id = Column(Integer, nullable=False, index=True)
    folder_id = Column(Integer, nullable=True, index=True)
    title = Column(String(255), nullable=False, default="")
    file_name = Column(String(255), nullable=False, default="")
    rel_path = Column(String(500), nullable=False, default="")
    source = Column(String(20), nullable=False, default="upload")
    tags = Column(String(500), nullable=False, default="")
    file_hash = Column(String(64), nullable=False, default="")
    parse_status = Column(String(20), nullable=False, default="ready")
    kind = Column(String(20), nullable=False, default="other")
    evidence_level = Column(String(20), nullable=False, default="须出处")
    files_ref = Column(Text, nullable=False, default="")
    wiki_json = Column(Text, nullable=False, default="")
    embedding_profile = Column(String(150), nullable=False, default="")
    extra = Column(Text, nullable=False, default="")
    search_text = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class KbChunk(Base):
    """一份资料切出来的一段，用来做向量检索。"""

    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    library_id = Column(Integer, nullable=False, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    text = Column(Text, nullable=False, default="")
    embedding = Column(Text, nullable=False, default="")
    profile = Column(String(150), nullable=False, default="")
