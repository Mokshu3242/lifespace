"""Catalog tests: the data is sane and the shortlist picks sensible items."""
from fastapi.testclient import TestClient

from app import catalog
from app.main import app


def test_catalogs_load_and_are_sane():
    for pack in catalog.PACKS:
        items = catalog.load(pack)
        assert len(items) >= 40
        assert len({i.id for i in items}) == len(items)            # unique ids
        for i in items:
            assert i.w_in > 0 and i.price_usd > 0 and i.rooms and i.uses
            assert i.w_in <= 130 and i.d_in <= 130                  # nothing bigger than a real item


def test_shortlist_by_size_and_room():
    beds = catalog.shortlist("home", 60, 82, "Master Bedroom")
    assert beds[0].id == "bed-queen"
    assert all(i.fits_room("master bedroom") for i in beds)
    # the same size in a kitchen is not a bed
    assert not any(i.category == "bed" for i in catalog.shortlist("home", 60, 82, "Kitchen"))
    # rotation doesn't matter
    assert catalog.shortlist("home", 82, 60, "Bedroom")[0].id == "bed-queen"
    # a meeting table in an office meeting room
    assert catalog.shortlist("office", 95, 44, "Meeting Room")[0].id == "meet-8"
    # tiny shapes match nothing big
    assert all(i.category != "bed" for i in catalog.shortlist("home", 15, 15))


def test_catalog_api():
    c = TestClient(app)
    r = c.get("/api/catalog/office")
    assert r.status_code == 200 and len(r.json()["items"]) >= 40
    assert c.get("/api/catalog/castle").status_code == 404
