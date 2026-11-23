"""Preview or apply the three Medisoft v4 registry tables.

Default: preview SQL only, no database connection.
--apply-test: apply only to medisoft_v4_test.
--apply-cloud: apply only to central_monitoring.

No clinic schema, replication channel, or existing table is altered.
MySQL DDL is nontransactional: confirm backups before applying.
"""
import argparse

from sqlalchemy import inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.database import Base, engine
from app.models.health_center import HealthCenter, MonitoredDatabase
from app.models.settings import Setting

TABLES = [HealthCenter.__table__, MonitoredDatabase.__table__, Setting.__table__]
TEST_DATABASE = "medisoft_v4_test"
CLOUD_DATABASE = "central_monitoring"


def preview():
    dialect = mysql.dialect()
    print("-- PREVIEW ONLY: no database connection, no DDL executed")
    for table in TABLES:
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    print("-- Settings row id=1 will disable retention cleanup.")


def apply(target_database):
    if engine.dialect.name != "mysql":
        raise SystemExit("Refusing schema changes: MySQL is required.")
    configured = engine.url.database
    if configured != target_database:
        raise SystemExit(
            f"Refusing schema changes: configured database {configured!r} "
            f"does not match required database {target_database!r}."
        )

    with engine.connect() as connection:
        selected = connection.execute(text("SELECT DATABASE()")).scalar()
        if selected != target_database:
            raise SystemExit(f"Refusing schema changes: active database {selected!r}.")
        existing = set(inspect(connection).get_table_names())
        conflicts = sorted(existing.intersection(table.name for table in TABLES))
        if conflicts:
            raise SystemExit(
                "Refusing to modify existing registry tables: " + ", ".join(conflicts)
            )

    # Only these three registry tables; never Base.metadata.create_all() globally.
    # MySQL DDL may persist after an error; check schema before retrying.
    Base.metadata.create_all(bind=engine, tables=TABLES, checkfirst=True)
    with engine.begin() as connection:
        selected = connection.execute(text("SELECT DATABASE()")).scalar()
        if selected != target_database:
            raise RuntimeError("Database changed before settings initialization")
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
    print(f"Created three registry tables in {target_database}.")
    print("Initialized settings id=1 with retention cleanup disabled.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply-test", action="store_true")
    modes.add_argument("--apply-cloud", action="store_true")
    args = parser.parse_args()
    if args.apply_test:
        apply(TEST_DATABASE)
    elif args.apply_cloud:
        apply(CLOUD_DATABASE)
    else:
        preview()
