from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


class Base(DeclarativeBase):
    pass


class FeedbackBase(DeclarativeBase):
    """RM ratings of suggestions. A separate set of tables on purpose: ingest rebuilds every table in `Base` from the CSV files,
    and a rating is the RM's own input, which a data reload must not erase."""


def make_engine(url: str | None = None):
    url = url or config.DATABASE_URL
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    return create_engine(url, **kwargs)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    with SessionLocal() as session:
        yield session
