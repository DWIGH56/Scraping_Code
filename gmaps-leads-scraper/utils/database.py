"""
Database pipeline for storing scraped leads.

Supports:
- SQLite (local, default)
- PostgreSQL (remote)

Uses SQLAlchemy ORM for easy switching.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    Boolean,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DB_ENGINE, SQLITE_DB_PATH, POSTGRES_DSN

logger = logging.getLogger(__name__)

Base = declarative_base()


# ---------------------------------------------------------------------------
# ORM Model
# ---------------------------------------------------------------------------
class Lead(Base):
    """Represents a single scraped Google Maps lead."""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(500), nullable=True)
    instagram = Column(String(500), nullable=True)
    facebook = Column(String(500), nullable=True)
    tiktok = Column(String(500), nullable=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, nullable=True)
    address = Column(Text, nullable=True)
    plus_code = Column(String(100), nullable=True)
    hours = Column(String(255), nullable=True)
    keyword = Column(String(255), nullable=True, index=True)
    location = Column(String(255), nullable=True, index=True)
    has_google_ads = Column(Boolean, nullable=True, default=None)
    has_facebook_pixel = Column(Boolean, nullable=True, default=None)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "website": self.website,
            "instagram": self.instagram,
            "facebook": self.facebook,
            "tiktok": self.tiktok,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
            "address": self.address,
            "plus_code": self.plus_code,
            "hours": self.hours,
            "keyword": self.keyword,
            "location": self.location,
            "has_google_ads": self.has_google_ads,
            "has_facebook_pixel": self.has_facebook_pixel,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
        }


# ---------------------------------------------------------------------------
# Engine & Session
# ---------------------------------------------------------------------------
def _get_database_url() -> str:
    if DB_ENGINE == "postgresql":
        return POSTGRES_DSN
    # Default: SQLite
    return f"sqlite:///{SQLITE_DB_PATH}"


engine = create_engine(_get_database_url(), echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialised.")


def save_leads(leads: list[dict]) -> int:
    """
    Bulk-insert leads into the database.

    Parameters
    ----------
    leads : list[dict]

    Returns
    -------
    int – number of records inserted.
    """
    if not leads:
        return 0

    session = SessionLocal()
    count = 0
    try:
        for entry in leads:
            lead = Lead(
                name=entry.get("name"),
                phone=entry.get("phone"),
                website=entry.get("website"),
                instagram=entry.get("instagram"),
                facebook=entry.get("facebook"),
                tiktok=entry.get("tiktok"),
                rating=entry.get("rating"),
                reviews_count=entry.get("reviews_count"),
                address=entry.get("address"),
                plus_code=entry.get("plus_code"),
                hours=entry.get("hours"),
                keyword=entry.get("keyword"),
                location=entry.get("location"),
                has_google_ads=entry.get("has_google_ads"),
                has_facebook_pixel=entry.get("has_facebook_pixel"),
            )
            session.add(lead)
            count += 1

        session.commit()
        logger.info(f"Inserted {count} leads into the database.")
    except Exception as e:
        session.rollback()
        logger.error(f"Database insert error: {e}")
        raise
    finally:
        session.close()

    return count