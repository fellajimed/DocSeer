import enum
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SAEnum,
    Integer,
    Text,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class PaperStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"
    metadata_only = "metadata_only"


class Paper(Base):
    __tablename__ = "papers"

    # ----------------------------------------------------------------- identity
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ------------------------------------------------------------------ source
    # file path, URL, or None when added from bibtex without a local file
    source_path = Column(Text, nullable=True, unique=True)

    # --------------------------------------------------------- bibliographic
    title = Column(Text, nullable=True)
    authors = Column(ARRAY(Text), nullable=True)
    abstract = Column(Text, nullable=True)
    year = Column(Integer, nullable=True)
    journal = Column(Text, nullable=True)
    publisher = Column(Text, nullable=True)
    doi = Column(Text, nullable=True, index=True)
    arxiv_id = Column(Text, nullable=True, index=True)
    url = Column(Text, nullable=True)
    isbn = Column(Text, nullable=True)

    # -------------------------------------------------------- zotero / bibtex
    bibtex_key = Column(Text, nullable=True, index=True)
    bibtex_raw = Column(Text, nullable=True)
    zotero_key = Column(Text, nullable=True)
    collection = Column(Text, nullable=True)
    tags = Column(ARRAY(Text), nullable=True)

    # --------------------------------------------------------- ingestion state
    status = Column(
        SAEnum(PaperStatus, name="paperstatus"),
        nullable=False,
        default=PaperStatus.pending,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    celery_task_id = Column(Text, nullable=True)

    # ------------------------------------------------------------------ times
    date_added = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    date_processed = Column(DateTime(timezone=True), nullable=True)

    # ------------------------------------------------------------ flexible bag
    extra_metadata = Column(JSON, nullable=True)
