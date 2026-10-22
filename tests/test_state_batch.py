import copy
import json

import pytest

from bord_food_api.platform import Platform
from bord_food_api.state_batch import (
    MODEL,
    Client,
    import_results,
    prepare,
    validate_results,
    write_plan,
)


def setup(tmp_path):
    p = Platform(tmp_path)
    p.sync(
        "fixture",
        "IA",
        "r1",
        [
            {
                "kind": "store",
                "source_key": "one",
                "payload": {
                    "name": "Fixture Market",
                    "country": "US",
                    "address": {
                        "street": "1 Main St",
                        "city": "Ames",
                        "region": "IA",
                        "postal_code": "50010",
                    },
                },
            }
        ],
    )
    s = p.records("store")[0]
    doc = {
        "store_id": s["id"],
        "text": "Main phone: 515-555-1234. Hours Mo-Sa 08:00-21:00; Su off.",
        "source_id": "retailer_page",
        "record_id": "one",
        "source_url": "https://fixture.test/one",
        "retrieved_at": 100,
        "authority": "official",
        "lineage": "retailer:fixture.test",
        "branch_match": "exact_address",
        "can_send_to_model": True,
    }
    plan = prepare([s], [doc], state="IA", pass_id="test", generation=p.current()["generation"])
    return p, s, plan


def output(plan, s, **values):
    proposal = {
        "store_id": s["id"],
        "document_id": next(iter(plan["documents"])),
        "field": "phone",
        "value": "5155551234",
        "quote": "515-555-1234",
        "reason": "quoted branch contact",
        **values,
    }
    return {
        "custom_id": plan["requests"][0]["custom_id"],
        "response": {
            "status_code": 200,
            "body": {
                "status": "completed",
                "model": MODEL,
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"proposals": [proposal]})}
                        ],
                    }
                ],
            },
        },
        "error": None,
    }


def test_quoted_source_import_never_counts_model_as_independent_verification(tmp_path):
    p, s, plan = setup(tmp_path)
    r = import_results(p, plan, [output(plan, s)], now=101)
    assert r["changed"] == 1
    row = p.get("store", s["id"])
    assert row["phone"] == "+15155551234"
    assert row["field_provenance"]["phone"]["status"] == "source_reported"
    assert row["field_provenance"]["phone"]["verified_at"] is None
    assert row["field_evidence"][0]["machine_extraction"]["independent_verification"] is False


def test_made_up_value_cross_branch_quotes_coordinates_and_stale_store_are_held(tmp_path):
    p, s, plan = setup(tmp_path)
    for changes in [
        {"value": "2125559999"},
        {"quote": "not in source"},
        {"field": "latitude", "value": "42"},
        {"store_id": "other"},
    ]:
        r = validate_results(plan, [output(plan, s, **changes)], p)
        assert not r["accepted"] and r["held"]
    p.sync(
        "fixture",
        "IA",
        "r2",
        [{"kind": "store", "source_key": "one", "payload": {**s, "name": "Renamed Fixture"}}],
    )
    assert (
        validate_results(plan, [output(plan, s)], p)["held"][0]["reason"]
        == "store_changed_since_request"
    )


def test_result_order_idempotence_and_failure_accounting(tmp_path):
    p, s, plan = setup(tmp_path)
    line = output(plan, s)
    with pytest.raises(ValueError, match="duplicate"):
        validate_results(plan, [line, line], p)
    assert validate_results(plan, [], p)["held"][0]["reason"] == "result_missing"
    r = validate_results(plan, [{**line, "error": {"code": "expired"}, "response": None}], p)
    assert not r["accepted"] and r["held"]


def test_nine_inference_request_bound_and_deferred_stores_are_explicit(tmp_path):
    _p, s, base = setup(tmp_path)
    doc = next(iter(base["documents"].values()))
    stores = []
    documents = []
    for i in range(200):
        sid = "store" + str(i)
        stores.append({**s, "id": sid})
        documents.append({**doc, "store_id": sid, "text": "x" * 9000})
    plan = prepare(stores, documents, state="IA", pass_id="large", generation="fixture")
    assert len(plan["requests"]) == 9 and plan["deferred"]
    assert plan["reservation_nanousd"] < 2_000_000_000


def test_submission_reserves_before_transport_and_never_retries_unknown_outcome(tmp_path):
    _p, _s, plan = setup(tmp_path)
    directory = tmp_path / "pilot"
    write_plan(directory, plan)

    class Mock(Client):
        def request(self, *a, **kw):
            raise ValueError("mock transport")

    client = Mock("fixture-key")
    with pytest.raises(ValueError, match="mock transport"):
        client.submit(directory)
    assert json.loads((directory / "status.json").read_text())["state"] == "submission_intent"
    with pytest.raises(ValueError, match="already_reserved"):
        client.submit(directory)
    changed = copy.deepcopy(plan)
    changed["requests"][0]["body"]["tools"] = [{"type": "web_search"}]
    write_plan(tmp_path / "bad", changed)
    with pytest.raises(ValueError, match="policy_changed"):
        client.submit(tmp_path / "bad")


def test_post_pass_hook_requires_completion_and_prepares_once_without_network(tmp_path):
    from bord_food_api.state_batch import prepare_after_pass

    p, _s, _plan = setup(tmp_path)
    with pytest.raises(ValueError, match="not_complete"):
        prepare_after_pass(
            p, {"state": "running"}, state="IA", pass_id="one", directory=tmp_path / "hook"
        )
    first = prepare_after_pass(
        p, {"state": "finished_with_holds"}, state="IA", pass_id="one", directory=tmp_path / "hook"
    )
    assert (
        prepare_after_pass(
            p, {"state": "finished"}, state="IA", pass_id="one", directory=tmp_path / "hook"
        )
        == first
    )
    assert not (tmp_path / "hook/status.json").exists()
