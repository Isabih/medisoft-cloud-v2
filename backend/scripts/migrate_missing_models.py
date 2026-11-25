"""Preview or create the approved missing ORM tables in central_monitoring."""
import argparse
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable, CreateIndex
from app.core.config import settings
from app.core.database import Base, engine

APPROVED = {
    "alerts", "backups", "database_metrics", "heartbeat_logs",
    "hybrid_diagnoses", "local_status_reports", "replica_emergency_states",
    "replication_guardian_events", "replication_status",
    "source_agent_reports", "user_roles",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-cloud", action="store_true")
    args = parser.parse_args()
    if any((settings.auto_create_tables, settings.enable_background_collectors,
            settings.allow_runtime_schema_migrations)):
        raise SystemExit("All three startup safety flags must be false.")
    if engine.dialect.name != "mysql" or engine.url.database != "central_monitoring":
        raise SystemExit("Refusing: expected MySQL central_monitoring.")
    import app.main
    with engine.connect() as conn:
        if conn.execute(text("SELECT DATABASE()")).scalar() != "central_monitoring":
            raise SystemExit("Unexpected active database.")
        existing = set(inspect(conn).get_table_names())
        if not APPROVED.issubset(Base.metadata.tables):
            raise SystemExit("Approved models missing from metadata.")
        tables = [t for t in Base.metadata.sorted_tables
                  if t.name in APPROVED and t.name not in existing]
        for table in tables:
            if table.schema not in (None, "central_monitoring"):
                raise SystemExit("Unexpected table schema.")
            for fk in table.foreign_keys:
                if fk.column.table.schema not in (None, "central_monitoring"):
                    raise SystemExit("Unexpected foreign key schema.")
                if fk.column.table.name not in existing | APPROVED:
                    raise SystemExit("Unexpected foreign key dependency.")
            print(str(CreateTable(table).compile(dialect=engine.dialect)) + ";")
            for index in table.indexes:
                print(str(CreateIndex(index).compile(dialect=engine.dialect)) + ";")
        print("Missing approved tables:", len(tables))
        if not args.apply_cloud:
            print("Preview only; no DDL executed.")
            return
        for table in tables:
            table.create(bind=conn, checkfirst=True)
            print("Created:", table.name)
        conn.commit()
        remaining = APPROVED - set(inspect(conn).get_table_names())
        if remaining:
            raise SystemExit("Still missing: " + ", ".join(sorted(remaining)))
        print("All 11 approved tables present. Existing tables were not altered.")


if __name__ == "__main__":
    main()
