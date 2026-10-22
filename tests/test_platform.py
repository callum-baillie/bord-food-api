"""Synthetic catalog, crash boundary, durable identity and lease regression tests."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from bord_food_api.control import Control
from bord_food_api.domain import normalize_gtin
from bord_food_api.importer import build_catalog
from bord_food_api.platform import Platform


def store(key="001", **values):
    return {
        "kind": "store",
        "source_key": key,
        "payload": {
            "name": "Synthetic market",
            "chain_key": "synthetic",
            "address": "1 Fixture Lane",
            **values,
        },
    }


def test_empty_identity_alias_and_migration(tmp_path):
    p = Platform(tmp_path)
    assert p.current() is None
    assert p.records("store") == []
    a = p.control.identity("fixture", "store", "001")
    assert p.control.identity("fixture", "store", "001") == a
    b = p.control.identity("fixture", "store", "002")
    p.control.alias("fixture", "store", "001", b, "reviewed synthetic correction")
    assert p.control.identity("fixture", "store", "001") == b
    p.control.undo_alias(1)
    assert p.control.identity("fixture", "store", "001") == a
    assert Platform(tmp_path).current() is None
    with p.control.connect() as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="Unsupported"):
        Control(tmp_path)


def test_snapshot_noop_hours_partial_relocation(tmp_path):
    p = Platform(tmp_path)
    result = p.sync("fixture", "stores", "r1", [store(hours="9-5"), store("002")])
    old = result["manifest"]
    original = p.records("store")
    assert p.sync("fixture", "stores", "r1", [])["no_change"]
    result = p.sync("fixture", "stores", "r2", [store(hours="9-6"), store("002"), store("003")])
    assert result["changed"] == 2
    assert result["unchanged"] == 1
    assert p.records("store", old["generation"]) == original
    assert len(p.records("chain")) == 1
    p.sync("fixture", "stores", "r3", [store(address="9 New Location")], complete=False)
    row = p.get(
        "store", next(x["id"] for x in original if x["source_refs"][0]["record_id"] == "001")
    )
    assert row["address"] == "1 Fixture Lane"
    assert row["identity_review"]["reason"] == "location_changed"
    assert len(p.records("store")) == 3


@pytest.mark.parametrize("point", ["before_switch", "after_switch"])
def test_actual_process_crash_recovery(tmp_path, point):
    p = Platform(tmp_path)
    first = p.sync("fixture", "stores", "r1", [store()])["manifest"]
    code = """
import os,sys
from bord_food_api.platform import Platform
p=Platform(sys.argv[1])
def hook(point):
 if point==sys.argv[2]: os._exit(71)
p.sync('fixture','stores','r2',[{'kind':'store','source_key':'001','payload':{'name':'Changed fixture'}}],cursor=123,hook=hook)
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path), point], check=False)
    assert result.returncode == 71
    p = Platform(tmp_path)
    with p.control.connect() as db:
        assert db.execute("SELECT release FROM source_state").fetchone()[0] == "r1"
    p.recover()
    p.recover()
    with p.control.connect() as db:
        row = db.execute("SELECT release,cursor FROM source_state").fetchone()
        assert row[0] == ("r1" if point == "before_switch" else "r2")
        assert len([e for e in p.changes() if e["kind"] == "store"]) == (
            1 if point == "before_switch" else 2
        )
    assert (p.current()["generation"] == first["generation"]) == (point == "before_switch")


def test_fence_and_dedupe(tmp_path):
    p = Platform(tmp_path)
    job_id = p.control.enqueue("fixture", "stores")
    assert p.control.enqueue("fixture", "stores") == job_id
    first = p.control.claim("old")
    with p.control.connect() as db:
        db.execute("UPDATE jobs SET expires=?", (time.time() - 1,))
    second = p.control.claim("new")
    assert second["token"] > first["token"]
    with pytest.raises(ValueError, match="fence"):
        p.sync("fixture", "stores", "r1", [store()], fence=first)
    assert p.current() is None
    p.sync("fixture", "stores", "r1", [store()], fence=second)
    p.control.finish(second)
    assert len(p.records("store")) == 1


def test_legacy_adoption_and_backup_restore_rollback(tmp_path):
    p = Platform(tmp_path / "data")
    original = Path(__file__).parent / "fixtures" / "foods.json"
    build_catalog([original], p.root / "foods.sqlite")
    before = (p.root / "foods.sqlite").read_bytes()
    first = p.adopt_legacy()
    assert (p.root / "foods.sqlite").read_bytes() == before
    assert p.legacy_path().exists()
    p.sync("fixture", "stores", "r1", [store()])
    p.backup(tmp_path / "backup")
    restored = Platform(tmp_path / "restored")
    restored.restore(tmp_path / "backup")
    assert restored.records("store") == p.records("store")
    assert restored.legacy_path().read_bytes() == p.legacy_path().read_bytes()
    p.rollback(first["generation"], apply=True)
    assert p.records("store") == []
    with p.control.connect() as db:
        assert [r[0] for r in db.execute("SELECT source FROM source_state")] == ["local_usda"]


def test_invalid_snapshot_does_not_switch_and_object_corruption(tmp_path):
    p = Platform(tmp_path)
    first = p.sync("fixture", "stores", "r1", [store()])["manifest"]
    with pytest.raises(ValueError, match="Duplicate"):
        p.sync("fixture", "stores", "r2", [store(), store()])
    assert p.current() == first
    with pytest.raises(ValueError, match="Empty"):
        p.sync("fixture", "stores", "r2", [])
    path = p.object_path(first["packs"]["stores"])
    path.chmod(0o644)
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        p.recover()


def test_no_content_change_acknowledges_new_release_without_rewriting_object(tmp_path):
    p = Platform(tmp_path)
    a = p.sync("fixture", "stores", "r1", [store()])["manifest"]
    b = p.sync("fixture", "stores", "r2", [store()])
    assert b["no_change"]
    assert a["generation"] != b["manifest"]["generation"]
    assert a["packs"] == b["manifest"]["packs"]
    assert len([e for e in p.changes() if e["kind"] == "store"]) == 1
    p.sync("fixture", "stores", "r2", [store()], parser_version="2")
    assert p.current()["sources"]["fixture:stores"]["parser_version"] == "2"


def test_absence_requires_distinct_complete_runs_never_closure(tmp_path, monkeypatch):
    p = Platform(tmp_path)
    p.sync("fixture", "stores", "r1", [store(), store("002")])
    start = time.time()
    for day, release in [(0, "r2"), (11, "r3"), (22, "r4")]:
        monkeypatch.setattr("bord_food_api.platform.time.time", lambda day=day: start + day * 86400)
        p.sync("fixture", "stores", release, [store("002")])
    missing = next(r for r in p.records("store") if r["source_refs"][0]["record_id"] == "001")
    assert missing["source_membership"]["status"] == "missing_from_source"
    assert missing.get("lifecycle") != "closed"
    p.sync("fixture", "stores", "r5", [store(), store("002")])
    assert all("source_membership" not in r for r in p.records("store"))


def test_gc_requires_quiescence_and_keeps_old_generations(tmp_path):
    p = Platform(tmp_path)
    first = p.sync("fixture", "stores", "r1", [store()])["manifest"]
    p.sync("fixture", "stores", "r2", [store(hours="changed")])
    with pytest.raises(ValueError, match="quiesced"):
        p.gc()
    p.gc(quiesced=True)
    assert p.records("store", first["generation"])


@pytest.mark.parametrize(
    "value,valid",
    [
        ("96385074", True),
        ("036000291452", True),
        ("4006381333931", True),
        ("10012345000017", True),
        ("036000291453", False),
        ("123456789", False),
    ],
)
def test_gtin(value, valid):
    assert (normalize_gtin(value) is not None) == valid


@pytest.mark.parametrize("point", ["before_switch", "after_switch"])
def test_rollback_process_crash_restores_matching_checkpoints(tmp_path, point):
    p = Platform(tmp_path)
    first = p.sync("fixture", "stores", "r1", [store()])["manifest"]
    p.sync("fixture", "stores", "r2", [store(hours="changed")], cursor=200)
    code = """
import os,sys
from bord_food_api.platform import Platform
p=Platform(sys.argv[1])
def hook(point):
 if point==sys.argv[3]: os._exit(71)
p.rollback(sys.argv[2],apply=True,hook=hook)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path), first["generation"], point], check=False
    )
    assert result.returncode == 71
    p = Platform(tmp_path)
    p.recover()
    p.recover()
    with p.control.connect() as db:
        release = db.execute("SELECT release FROM source_state").fetchone()[0]
    assert release == ("r2" if point == "before_switch" else "r1")
    assert ("hours" in p.records("store")[0]) == (point == "before_switch")


def test_reviewed_alias_chain_is_generation_bound_reversible_and_preserves_assertions(tmp_path):
    p = Platform(tmp_path)
    first = p.sync("fixture", "stores", "r1", [store("A"), store("B"), store("C")])["manifest"]
    ids = {r["source_refs"][0]["record_id"]: r["id"] for r in p.records("store")}
    p.control.alias("fixture", "store", "A", ids["B"], "reviewed fixture duplicate")
    p.sync("fixture", "stores", "r1", [store("A"), store("B"), store("C")])
    assert p.get("store", ids["A"])["id"] == ids["B"]
    assert len(p.records("store")) == 2
    assert p.get("store", ids["A"], first["generation"])["id"] == ids["A"]
    p.control.alias("fixture", "store", "B", ids["C"], "second reviewed fixture duplicate")
    p.sync("fixture", "stores", "r1", [store("A"), store("B"), store("C")])
    assert p.get("store", ids["A"])["id"] == ids["C"]
    assert len(p.records("store")) == 1
    target = p.get("store", ids["C"])
    assert {r["record_id"] for r in target["source_alternatives"]} == {"A", "B"}
    p.control.undo_alias(2)
    p.sync("fixture", "stores", "r1", [store("A"), store("B"), store("C")])
    assert p.get("store", ids["A"])["id"] == ids["B"]
    assert len(p.records("store")) == 2
    assert "source_alternatives" not in p.get("store", ids["C"])


def test_revocation_hides_alias_alternatives_and_rejects_rollback_restore_export(tmp_path):
    p = Platform(tmp_path / "data")
    p.sync("allowed", "stores", "r1", [store("B")])
    first = p.sync("restricted", "stores", "r1", [store("A", name="Restricted source fact")])[
        "manifest"
    ]
    target = p.control.identity("allowed", "store", "B")
    alias = p.control.identity("restricted", "store", "A")
    p.control.alias("restricted", "store", "A", target, "reviewed match across sources")
    p.sync("restricted", "stores", "r1", [store("A", name="Restricted source fact")])
    assert p.get("store", target)["source_alternatives"]
    p.backup(tmp_path / "before-revocation")
    p.control.restrict_source("restricted")
    assert not p.get("store", target)["source_alternatives"]
    assert "Restricted source fact" not in str(p.records("store"))
    assert "Restricted source fact" not in str(list(p.iter_records("store")))
    with pytest.raises(ValueError, match="rights-restricted"):
        p.rollback(first["generation"], apply=True)
    with pytest.raises(ValueError, match="rights-restricted"):
        p.backup(tmp_path / "unsafe-export")
    p.purge_revoked(quiesced=True)
    assert p.get("store", alias) is None
    p.backup(tmp_path / "safe-export")
    restored = Platform(tmp_path / "restored")
    restored.restore(tmp_path / "safe-export")
    assert "Restricted source fact" not in str(restored.records("store"))
    fresh = Platform(tmp_path / "fresh")
    fresh.control.restrict_source("restricted")
    with pytest.raises(ValueError, match="rights-restricted"):
        fresh.restore(tmp_path / "before-revocation")


def test_off_semantic_noop_preserves_newest_source_clock(tmp_path):
    p = Platform(tmp_path)

    def product(clock, name="Fixture product"):
        return {
            "kind": "product",
            "source_key": "036000291452",
            "payload": {
                "name": name,
                "last_modified_t": clock,
                "revision": clock,
                "source_record": {"code": "036000291452", "last_modified_t": clock, "name": name},
            },
        }

    p.sync("open_food_facts", "products", "r1", [product(10)])
    original = p.records("product")[0]
    result = p.sync("open_food_facts", "products", "r2", [product(20)], complete=False, cursor=20)
    assert result["changed"] == 0
    assert p.records("product")[0]["content_revision"] == original["content_revision"]
    p.sync(
        "open_food_facts",
        "products",
        "r3",
        [product(15, "Older correction")],
        complete=False,
        cursor=21,
    )
    assert p.records("product")[0]["name"] == "Fixture product"
    with pytest.raises(ValueError, match="conflicting"):
        p.sync(
            "open_food_facts",
            "products",
            "r4",
            [product(20, "Conflicting correction")],
            complete=False,
            cursor=22,
        )
    before = p.current()
    p.sync("open_food_facts", "products", "r5", [], complete=False, cursor=23)
    assert p.current()["generation"] != before["generation"]
    assert p.current()["sources"]["open_food_facts:products"]["cursor"] == 23


def test_partial_snapshot_and_timestamp_only_changes_do_not_rewrite_facts(tmp_path):
    p = Platform(tmp_path)
    a = p.sync("fixture", "stores", "r1", [store(source_properties={"session": "a"})])["manifest"]
    b = p.sync("fixture", "stores", "r2", [store(source_properties={"session": "b"})])
    assert b["changed"] == 0
    assert b["manifest"]["packs"] == a["packs"]
    p.sync("all_the_places", "stores", "new", [store()], cursor={"source_run": "2026-10-10"})
    with pytest.raises(ValueError, match="regression"):
        p.sync("all_the_places", "stores", "old", [store()], cursor={"source_run": "2025-10-10"})


def test_paused_running_job_cannot_reclaim_or_publish(tmp_path):
    p = Platform(tmp_path)
    p.control.enqueue("fixture", "stores")
    job = p.control.claim("worker")
    p.control.set_source("fixture", False)
    assert p.control.claim("other") is None
    with pytest.raises(ValueError, match="fence"):
        p.control.check_fence(job)


def test_store_group_normalization_missing_values_and_due_audits(tmp_path, monkeypatch):
    p = Platform(tmp_path)
    original = store(phone="(319) 555-0100", latitude=42, longitude=-91, hours="9-5")
    p.sync("fixture", "stores", "r1", [original])
    before = p.records("store")[0]
    equivalent = store(phone="3195550100", latitude=42.0, longitude=-91.0, hours="9-5")
    result = p.sync("fixture", "stores", "r2", [equivalent])
    assert result["changed"] == 0
    assert p.records("store")[0]["content_revision"] == before["content_revision"]
    incomplete = store(phone=None, latitude=None, longitude=None, hours="9-6")
    report = p.sync("fixture", "stores", "r3", [incomplete])
    row = p.records("store")[0]
    assert row["latitude"] == 42 and row["longitude"] == -91
    assert row["phone"] == "(319) 555-0100"
    assert report["field_refresh"]["changed_groups"] == {"hours": 1}
    assert report["field_refresh"]["detail_jobs_queued"] == 0
    now = time.time()
    monkeypatch.setattr("bord_food_api.platform.time.time", lambda: now + 181 * 86400)
    report = p.sync("fixture", "stores", "r4", [incomplete])
    assert report["changed"] == 0
    assert "location" in report["field_refresh"]["detail_candidates"]
    assert report["field_refresh"]["detail_jobs_queued"] == 0


def test_native_reader_closes_query_connections(tmp_path, monkeypatch):
    p = Platform(tmp_path)
    p.sync("fixture", "stores", "r1", [store()])
    import sqlite3

    from bord_food_api import platform as module

    captured = []
    real = sqlite3.connect

    def connect(*args, **kwargs):
        db = real(*args, **kwargs)
        captured.append(db)
        return db

    monkeypatch.setattr(module.sqlite3, "connect", connect)
    for _ in range(5):
        assert list(p.iter_records("store"))
        assert p.get("store", p.records("store")[0]["id"])
    for db in captured:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            db.execute("SELECT 1")


def test_installation_identity_initializes_once_across_starters(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    def starter(_):
        control = Control(tmp_path)
        with control.connect() as db:
            return db.execute("SELECT id FROM installation").fetchone()[0]

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(starter, range(12)))
    assert len(set(ids)) == 1
    with Control(tmp_path).connect() as db:
        assert db.execute("SELECT count(*) FROM installation").fetchone()[0] == 1


def test_restore_rejects_future_control_before_copying_payloads(tmp_path):
    import sqlite3

    original = Platform(tmp_path / "original")
    original.sync("fixture", "stores", "r1", [store()])
    original.backup(tmp_path / "backup")
    with sqlite3.connect(tmp_path / "backup/control.sqlite") as db:
        db.execute("PRAGMA user_version=999")
    target = Platform(tmp_path / "target")
    with pytest.raises(ValueError, match="Unsupported backup"):
        target.restore(tmp_path / "backup")
    assert target.current() is None
    assert list((target.root / "objects/catalogs").iterdir()) == []


def test_batch_identity_reservations_reuse_aliases_and_rollback_limits(tmp_path):
    control = Control(tmp_path)
    first = control.identity_batch(
        "fixture", [("product", "1"), ("product", "1"), ("product", "2")]
    )
    assert len(first) == 2
    control.alias("fixture", "product", "1", first["product", "2"], "reviewed duplicate")
    again = control.identity_batch("fixture", [("product", "1"), ("product", "3")])
    assert again["product", "1"] == first["product", "2"]
    assert again["product", "3"] == control.identity("fixture", "product", "3")
    with pytest.raises(ValueError, match="bounded"):
        control.identity_batch("fixture", [("product", str(i)) for i in range(1025)])


def test_complete_product_snapshot_does_not_materialize_all_payloads(tmp_path, monkeypatch):
    import sqlite3

    from bord_food_api import platform as module

    real_connect = sqlite3.connect

    class Cursor(sqlite3.Cursor):
        def fetchall(self):
            if self.description and [r[0] for r in self.description] == [
                "kind",
                "id",
                "source_key",
                "payload",
            ]:
                raise AssertionError("Bulk snapshot payload materialized")
            return super().fetchall()

    class Connection(sqlite3.Connection):
        def execute(self, *args, **kwargs):
            return self.cursor(factory=Cursor).execute(*args, **kwargs)

    monkeypatch.setattr(
        module.sqlite3,
        "connect",
        lambda *args, **kwargs: real_connect(*args, factory=Connection, **kwargs),
    )
    platform = Platform(tmp_path)

    def products(count):
        for i in range(count):
            yield {
                "kind": "product",
                "source_key": str(i),
                "payload": {"name": f"Fixture {i}", "source_record": {"text": "x" * 1024}},
            }

    first = platform.sync("fixture", "products", "r1", products(100))
    assert first["changed"] == 100
    second = platform.sync("fixture", "products", "r2", products(99))
    assert second["changed"] == 1
    missing = next(r for r in platform.records("product") if r["name"] == "Fixture 99")
    assert missing["source_membership"]["status"] == "withdrawn_from_complete_snapshot"


def test_immutable_pack_validation_cache_rechecks_changed_objects(tmp_path, monkeypatch):
    from bord_food_api import platform as module

    p = Platform(tmp_path)
    manifest = p.sync("fixture", "stores", "r1", [store()])["manifest"]
    real = module.hashlib.file_digest
    calls = []

    def digest(handle, algorithm):
        calls.append(handle.name)
        return real(handle, algorithm)

    monkeypatch.setattr(module.hashlib, "file_digest", digest)
    Platform(tmp_path).recover()
    assert calls == []  # Same process, exact same immutable inode/stat signature.
    p.validate_manifest(manifest, force=True)
    assert len(calls) == 1
    path = p.object_path(manifest["packs"]["stores"])
    original = path.read_bytes()
    path.chmod(0o644)
    path.write_bytes(original)
    p.recover()
    assert len(calls) == 2  # Same bytes still trigger full validation after a write.
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        p.recover()
