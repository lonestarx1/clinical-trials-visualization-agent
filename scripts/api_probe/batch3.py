import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ctg import call, OUT
ids = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_ids.json")))
os.makedirs(f"{OUT}/samples", exist_ok=True)
# full single-study records
for label, nct in ids.items():
    if label == "pembro_only_in_title": continue
    s, d, rec = call(f"study_{label}_{nct}", f"/studies/{nct}")
    json.dump(d, open(f"{OUT}/samples/{label}_{nct}.json", "w"), indent=1)
    print(f"{label:16} {nct} {s} {rec['seconds']}s {rec['bytes']}B")
# page timing on a broad condition, minimal vs with locations vs with mesh
for label, f in [("bc_min", "NCTId|Phase|StartDate|LeadSponsorClass"),
                 ("bc_with_countries", "NCTId|Phase|StartDate|LeadSponsorClass|LocationCountry"),
                 ("bc_with_mesh", "NCTId|ConditionMeshTerm|InterventionMeshTerm|InterventionName")]:
    s, d, rec = call(label, "/studies", {"query.cond": "breast cancer", "pageSize": 1000, "fields": f})
    print(f"{label:18} {s} {rec['seconds']}s {rec['bytes']}B n={len(d.get('studies',[]))}")
d = json.load(open(f"{OUT}/raw/bc_with_mesh.json"))
print(json.dumps(d["studies"][:2])[:700])
# alias redirect / not found
s, d, rec = call("study_notfound", "/studies/NCT99999999"); print("notfound", s, str(d)[:120])
