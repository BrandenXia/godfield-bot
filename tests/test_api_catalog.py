from godfield import ItemCatalog

from godfield_bot.api_account import PYGODFIELD_REVISION
from godfield_bot.api_catalog import (
    ApiCatalogError,
    ApiCatalogSnapshot,
    api_catalog_digest,
    fetch_api_catalog_snapshot,
)


def test_fetch_catalog_records_ordered_raw_items(monkeypatch) -> None:
    catalog = ItemCatalog(
        [
            {"name": "Club", "category": "weapons", "atk": 5},
            {"name": "Shield", "category": "armor", "def": 5},
        ]
    )
    monkeypatch.setattr(
        ItemCatalog,
        "fetch",
        classmethod(lambda cls, **kwargs: catalog),
    )

    snapshot = fetch_api_catalog_snapshot(language="en", timeout_seconds=1)

    assert snapshot.total_items == 2
    assert [item.model_id for item in snapshot.items] == [1, 2]
    assert snapshot.items[0].raw["name"] == "Club"
    assert snapshot.upstream_revision == PYGODFIELD_REVISION
    assert snapshot.content_sha256 == api_catalog_digest(snapshot.items)


def test_catalog_snapshot_rejects_checksum_drift(monkeypatch) -> None:
    catalog = ItemCatalog([{"name": "Club", "category": "weapons", "atk": 5}])
    monkeypatch.setattr(
        ItemCatalog,
        "fetch",
        classmethod(lambda cls, **kwargs: catalog),
    )
    snapshot = fetch_api_catalog_snapshot()
    payload = snapshot.model_dump()
    payload["items"][0]["raw"]["atk"] = 6

    try:
        ApiCatalogSnapshot.model_validate(payload)
    except ValueError as error:
        assert "checksum" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("checksum drift was accepted")


def test_catalog_rejects_unknown_language() -> None:
    try:
        fetch_api_catalog_snapshot(language="xx")
    except ApiCatalogError as error:
        assert "unsupported" in str(error)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("unknown language was accepted")
