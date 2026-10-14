import psycopg

from tests.conftest import migrate


def test_migrations_round_trip(pg_uri, schema):
    migrate(pg_uri, schema, "base", down=True)
    with psycopg.connect(pg_uri) as c:
        tables = c.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = %s AND table_name <> 'alembic_version'",
            (schema,),
        ).fetchone()[0]
    assert tables == 0
    migrate(pg_uri, schema)
