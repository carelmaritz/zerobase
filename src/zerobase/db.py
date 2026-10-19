from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool  # one shared in-memory database
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)
