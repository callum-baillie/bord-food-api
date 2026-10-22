"""Executed explicit live ranking acquisition; not a routine offline fixture.

Five public requests, no retailer downloads/model calls. Existing output is never overwritten.
"""

import json
import time
from pathlib import Path
from urllib.parse import urlencode

from bord_food_api.nationwide import STATES
from bord_food_api.platform import atomic_json
from bord_food_api.store_discovery import SNAP_ITEM, SNAP_LAYER, PublicJSON

root = Path("/data/operator-imports/small-states-20261020/ranking")
assert not (root / "snap-groups.json").exists()
f = PublicJSON(root / "artifacts", "hello@foldlab.app")
item = f(SNAP_ITEM + "?f=json")
assert item["owner"] == "FNS_SNAP_RPMD" and item["url"].rstrip("/") == SNAP_LAYER.rsplit("/", 1)[0]
before = f(SNAP_LAYER + "?f=json")
stamp = before["editingInfo"]["dataLastEditDate"]
assert {"State", "Store_Type", "ObjectId"} <= {x["name"] for x in before["fields"]}
where = "State IN (" + ",".join("'" + s + "'" for s in STATES) + ")"
params = {
    "f": "json",
    "where": where,
    "groupByFieldsForStatistics": "State,Store_Type",
    "outStatistics": json.dumps(
        [
            {
                "statisticType": "count",
                "onStatisticField": "ObjectId",
                "outStatisticFieldName": "store_count",
            }
        ]
    ),
    "returnGeometry": "false",
}
g = f(SNAP_LAYER + "/query?" + urlencode(params))
assert not g.get("exceededTransferLimit") and not g.get("error")
rows = [x["attributes"] for x in g["features"]]
assert len({(x["State"], x["Store_Type"]) for x in rows}) == len(rows)
count = f(
    SNAP_LAYER + "/query?" + urlencode({"f": "json", "where": where, "returnCountOnly": "true"})
)["count"]
assert sum(x["store_count"] for x in rows) == count and {x["State"] for x in rows} == set(STATES)
after = f(SNAP_LAYER + "?f=json")
assert stamp == after["editingInfo"]["dataLastEditDate"]
result = {
    "source_url": SNAP_LAYER,
    "source_clock": stamp,
    "acquired_at": time.time(),
    "reference_rows_all_formats": count,
    "groups": rows,
    "group_total_matches_reference": True,
    "state_count": 50,
    "census_complete": False,
    "retailer_requests": 0,
    "paid_calls": 0,
}
atomic_json(root / "snap-groups.json", result)
print(json.dumps(result))
