import sys, os, json, collections; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctg import call
s, d, rec = call("pembro_mesh_p0", "/studies", {"query.intr": "pembrolizumab", "pageSize": 1000, "fields": "NCTId|InterventionName|InterventionType|InterventionMeshTerm|ConditionMeshTerm|Condition"})
print(s, rec["seconds"], rec["bytes"])
st = d["studies"]
C = collections.Counter
im = C(m["term"] for x in st for m in x.get("derivedSection", {}).get("interventionBrowseModule", {}).get("meshes", []))
print("studies w/o intervention mesh:", sum(1 for x in st if not x.get("derivedSection", {}).get("interventionBrowseModule", {}).get("meshes")), "/", len(st))
print("top intervention mesh:", im.most_common(15))
print("placebo-like mesh:", [t for t in im if "placebo" in t.lower()])
cm = C(m["term"] for x in st for m in x.get("derivedSection", {}).get("conditionBrowseModule", {}).get("meshes", []))
print("top condition mesh:", cm.most_common(10))
raw = C(c for x in st for c in x["protocolSection"].get("conditionsModule", {}).get("conditions", []))
print("distinct raw conditions:", len(raw), "distinct condition mesh:", len(cm))
