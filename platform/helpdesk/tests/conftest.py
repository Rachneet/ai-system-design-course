import tempfile

import pgserver
import psycopg
import pytest

import tests.platform  # noqa: F401  (Switchboard, Atlas and Checkpoint on sys.path, before any test imports)


@pytest.fixture(scope="session")
def pg_uri():
    srv = pgserver.get_server(tempfile.mkdtemp(), cleanup_mode="stop")
    uri = srv.get_uri()
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute("CREATE ROLE helpdesk_app LOGIN")  # the app's role: no superuser, no BYPASSRLS
    yield uri
    srv.cleanup()


@pytest.fixture
async def platform(pg_uri):
    from tests.harness import Platform

    async with Platform(pg_uri) as p:
        yield p
