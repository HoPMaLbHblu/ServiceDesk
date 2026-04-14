"""Database-level guards used by migrations."""

from django.db import migrations

_FUNCTION = """
CREATE OR REPLACE FUNCTION servicedesk_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Table % is append-only', TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""


def append_only(table: str) -> migrations.RunSQL:
    """Block UPDATE and DELETE on ``table``. Cascading deletes of a whole business
    use ``TRUNCATE``-free paths only in tests, which drop the database instead."""
    trigger = f"{table}_append_only"
    return migrations.RunSQL(
        sql=_FUNCTION
        + f"""
        DROP TRIGGER IF EXISTS {trigger} ON {table};
        CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON {table}
        FOR EACH ROW EXECUTE FUNCTION servicedesk_append_only();
        """,
        reverse_sql=f"DROP TRIGGER IF EXISTS {trigger} ON {table};",
    )
