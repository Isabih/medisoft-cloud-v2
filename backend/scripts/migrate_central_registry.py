"""Prepare and test the Medisoft v4 central registry schema.

Preview (no database connection or writes):
    python -m scripts.migrate_central_registry

Apply only to a disposable, isolated MySQL test database:
    DATABASE_URL=mysql+pymysql://.../medisoft_v4_test python -m scripts.migrate_central_registry --apply-test

Cloud development application is supported only with --apply-cloud and an exact\ncentral_monitoring database match. No other schemas are targeted.
"""
import argparse

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import mysql

from app.core.database import Base, engine
from app.models.health_center import HealthCenter, MonitoredDatabase
from app.models.settings import Setting

TABLES = [HealthCenter.__table__, MonitoredDatabase.__table__, Setting.__table__]
TEST_DATABASE = "medisoft_v4_test"\nCLOUD_DATABASE = "central_monitoring"


def preview():
    dialect = mysql.dialect()
    print("-- PREVIEW ONLY: no database connection, no DDL executed")
    print("-- Target tables: health_centers, monitored_databases, settings")
    for table in TABLES:
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    print("-- Test initialization: INSERT settings id=1 with retention cleanup disabled")


def apply_test():
    database = engine.url.database
    if database != TEST_DATABASE:
        raise SystemExit(
            "Refusing schema changes: --apply-test requires database name "
            f"{TEST_DATABASE!r}; configured database is {database!r}."
        )
    if engine.dialect.name != "mysql":
        raise SystemExit("This migration requires MySQL.")

    with engine.connect() as connection:
        selected = connection.execute(text("SELECT DATABASE()")).scalar()
        if selected != target_database:
            raise SystemExit(f"Unexpected active database: {selected!r}")
        existing = set(inspect(connection).get_table_names())
        conflicts = existing.intersection(t.name for t in TABLES)
        if conflicts:
            raise SystemExit(
                "Refusing to modify existing registry tables: "
                + ", ".join(sorted(conflicts))
            )

    # Deliberately limited to these three tables, not Base.metadata.create_all().
    # MySQL DDL is not transactional; verify backups and target before applying.
    Base.metadata.create_all(bind=engine, tables=TABLES, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO settings (
                id, day_close_time, auto_generate_reports, polling_interval,
                heartbeat_timeout_seconds, backup_check_time,
                detailed_retention_days, incident_history_retention_days,
                retention_run_hour_utc, enable_retention_cleanup
            ) VALUES (
                1, '00:00:00', 1, 30, 120, '07:00:00', 7, 365, 2, 0
            )
        """))
    print("Created three registry tables in database:", target_database)
    print("Seeded settings id=1; retention cleanup is disabled.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply-test", action="store_true",
        help="Create tables only in the isolated medisoft_v4_test database",
    )
    args = parser.parse_args()
    if args.apply_test:
        apply_test()
    else:
        preview()
