"""Bootstrap the first development administrator in central_monitoring only.

Run: python -m scripts.create_admin --username admin
Prompts for a password without echoing it. Does not touch clinic schemas.
"""
import argparse
import getpass
import re
import uuid

from passlib.context import CryptContext
from sqlalchemy import inspect, text

from app.core.database import engine
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
EXPECTED_DB = "central_monitoring"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    username = args.username.strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{2,49}", username):
        parser.error("Username must be 3-50 characters, beginning with a letter.")

    if engine.dialect.name != "mysql" or engine.url.database != EXPECTED_DB:
        raise SystemExit("Refusing: requires MySQL central_monitoring.")
    with engine.connect() as conn:
        if conn.execute(text("SELECT DATABASE()")).scalar() != EXPECTED_DB:
            raise SystemExit("Refusing: active database is not central_monitoring.")
        if inspect(conn).has_table("users"):
            columns = {col["name"] for col in inspect(conn).get_columns("users")}
            expected = {"id", "username", "password_hash", "role", "email", "created_at"}
            if not expected.issubset(columns):
                raise SystemExit("Existing users table has an unexpected schema; refusing.")
            count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            if count:
                raise SystemExit("Users already exist; refusing bootstrap. Use account management instead.")
        else:
            print("The users table is missing; creating only central_monitoring.users.")
            User.__table__.create(bind=engine, checkfirst=False)

    password = getpass.getpass("New admin password (hidden): ")
    confirmation = getpass.getpass("Confirm password (hidden): ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no account created.")
    if len(password) < 8 or len(password.encode("utf-8")) > 72:
        raise SystemExit("Password must be at least 8 characters and at most 72 UTF-8 bytes.")
    if password.strip() != password or not password.strip():
        raise SystemExit("Password cannot start or end with spaces.")

    with engine.begin() as conn:
        if conn.execute(text("SELECT DATABASE()")).scalar() != EXPECTED_DB:
            raise RuntimeError("Unexpected database")
        if conn.execute(text("SELECT COUNT(*) FROM users")).scalar():
            raise SystemExit("User exists; refusing to create another.")
        conn.execute(text("""
            INSERT INTO users (id, username, password_hash, role)
            VALUES (:id, :username, :password_hash, 'admin')
        """), {
            "id": str(uuid.uuid4()),
            "username": username,
            "password_hash": pwd_context.hash(password),
        })
    print(f"Created administrator {username!r} in {EXPECTED_DB}.")
    print("IMPORTANT: current login endpoint returns a fixed dev-token; do not expose it publicly.")


if __name__ == "__main__":
    main()
