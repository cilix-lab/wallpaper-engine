from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    sha256: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    # "unsplash" or "local"
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    author: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    unsplash_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # JSON-encoded list of tag strings
    tags: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
