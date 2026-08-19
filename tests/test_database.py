from sqlalchemy import create_engine, event

from app.db.session import enable_sqlite_foreign_keys


def test_sqlite_foreign_keys_are_enabled() -> None:
    engine = create_engine("sqlite://")
    event.listen(engine, "connect", enable_sqlite_foreign_keys)

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1

    engine.dispose()
