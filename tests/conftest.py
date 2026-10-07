import pytest

from trgtmrkt import db, ingest, synthetic


@pytest.fixture(scope="session")
def raw_exports():
    return synthetic.generate(n_per_lot=300, seed=7)


@pytest.fixture()
def conn(raw_exports):
    c = db.connect(":memory:")
    for lot, raw in raw_exports.items():
        ingest.ingest_frazer(c, raw, lot, salt="test-salt")
    return c


@pytest.fixture()
def deals(conn):
    return ingest.load_deals(conn)
