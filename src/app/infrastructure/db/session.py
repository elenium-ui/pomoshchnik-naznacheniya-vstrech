import logging
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        return

    if not url.database or url.database == ":memory:":
        return

    db_path = Path(url.database)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)


def build_engine(database_url: str, log_level: str = "INFO") -> Engine:
    _ensure_sqlite_parent_dir(database_url)
    connect_args = {}

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    echo = log_level.upper() == "DEBUG"
    engine = create_engine(database_url, connect_args=connect_args, echo=echo)
    logger.info("Database engine initialized.")
    return engine


def build_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def check_database_connection(engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection check passed.")
    except Exception:
        logger.exception("Database connection check failed.")
        raise
