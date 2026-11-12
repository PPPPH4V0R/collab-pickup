# Applies the numbered .sql files in migrations/ in order, exactly once each.
# The schema_version table remembers which versions are already applied,
# so running this script again is safe: every database ends up with the
# same schema by the same path.
# Run: python migrate.py
from pathlib import Path
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url)

with engine.begin() as conn:
    conn.execute(text("CREATE TABLE IF NOT EXISTS schema_version ("
                      " version INTEGER PRIMARY KEY,"
                      " applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"))
    applied = set(conn.execute(text("SELECT version FROM schema_version")).scalars())

for path in sorted(Path(__file__).parent.glob("migrations/*.sql")):
    version = int(path.name.split("_")[0])
    if version in applied:
        print(f"  {path.name}: already applied, skipping")
        continue
    # PostgreSQL can run DDL inside a transaction, so a migration and its
    # schema_version row are committed together or not at all.
    with engine.begin() as conn:
        conn.exec_driver_sql(path.read_text(encoding="utf-8"))
        conn.execute(text("INSERT INTO schema_version (version) VALUES (:v)"),
                     {"v": version})
    print(f"  {path.name}: applied")
