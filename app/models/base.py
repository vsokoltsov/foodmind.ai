"""SQLAlchemy declarative base for application persistence models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class shared by all application database models."""

