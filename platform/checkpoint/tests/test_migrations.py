from tests.conftest import migrate


def test_migrations_round_trip(pg_uri, schema):
    migrate(pg_uri, schema, "base", down=True)
    migrate(pg_uri, schema, "head")
