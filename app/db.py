from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str) -> None:
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if ":memory:" in url:
                kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, pool_pre_ping=True, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._sqlite_connect)
            event.listen(self.engine, "begin", self._sqlite_begin)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _sqlite_connect(connection: object, _: object) -> None:
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")

    @staticmethod
    def _sqlite_begin(connection: object) -> None:
        # SQLite development fallback serializes transactions; PostgreSQL uses row locks.
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self.sessions() as session, session.begin():
            yield session
