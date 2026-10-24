"""Batch 5: the API's canonical country names (for the country alias table, design Q7 D7.3)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctg import OUT, call  # noqa: E402

NAME = "b5_location_country_values"
raw = os.path.join(OUT, "raw", f"{NAME}.json")
if not os.path.exists(raw):
    call(NAME, "/stats/field/values", {"fields": "LocationCountry"})
with open(raw) as f:
    stats = json.load(f)[0]
assert len(stats["topValues"]) == stats["uniqueValuesCount"], "list is capped"
values = sorted(v["value"] for v in stats["topValues"])
path = os.path.join(OUT, "..", "reference", "location-countries.json")
with open(path, "w") as f:
    json.dump({"source": "GET /api/v2/stats/field/values?fields=LocationCountry",
               "count": len(values), "values": values}, f, indent=1)
print(len(values), "countries;", [v for v in values if "Korea" in v or "Turk" in v or "United" in v])
