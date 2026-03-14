"""SQLAlchemy model for the repos table."""
from sqlalchemy import String, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    github_repo_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    repo_name: Mapped[str] = mapped_column(String(255), nullable=False)
