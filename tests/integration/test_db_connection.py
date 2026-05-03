from pathlib import Path

from app.infrastructure.db.session import build_engine, check_database_connection


def test_sqlite_connection_health_check_passes(tmp_path):
    db_file = tmp_path / "integration.db"
    database_url = f"sqlite:///{db_file}"

    engine = build_engine(database_url, log_level="INFO")
    check_database_connection(engine)

    assert db_file.parent.exists()
